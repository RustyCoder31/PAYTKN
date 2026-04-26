"""PPO training script for ChainEnv — v3 (best-possible edition).

Fresh curriculum run (RECOMMENDED — ~6-8 hrs on Colab T4/CPU):
    python scripts/train.py --curriculum --large-net --envs 8 --timesteps 5000000 --name final_v1

Continue polishing an existing checkpoint (2-3 hrs):
    python scripts/train.py --curriculum --continue-from models/best_model.zip --envs 8 --timesteps 2000000 --name final_v1_finetune

Outputs:
    models/best_model.zip       — best checkpoint saved by EvalCallback
    models/<name>_final.zip     — checkpoint at end of training
    tensorboard_logs/<name>/    — TensorBoard logs
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import gymnasium as gym

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import SubprocVecEnv
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
from stable_baselines3.common.monitor import Monitor

from chainenv.env import PaytknEnv
from chainenv.config import SimConfig


# ─────────────────────────────────────────────────────────────
# Curriculum wrapper  (weighted random sampling)
# ─────────────────────────────────────────────────────────────

class MarketCurriculumEnv(gym.Env):
    """Samples a SimConfig according to weights on every episode reset.

    Bears get 3× weight so the agent sees them far more often than a uniform
    draw would provide — fixing the gap exposed by the historical evaluation.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        configs:  list[SimConfig],
        weights:  list[float] | None = None,
        seed:     int = 0,
    ):
        super().__init__()
        self._configs = configs
        # Normalise weights to probabilities
        w = np.array(weights if weights is not None else [1.0] * len(configs),
                     dtype=np.float64)
        self._probs = w / w.sum()
        self._rng   = np.random.default_rng(seed)
        self._env   = PaytknEnv(configs[0])
        self.observation_space = self._env.observation_space
        self.action_space      = self._env.action_space

    def reset(self, *, seed=None, options=None):
        idx = int(self._rng.choice(len(self._configs), p=self._probs))
        self._env.cfg = self._configs[idx]
        return self._env.reset(seed=seed, options=options)

    def step(self, action):
        return self._env.step(action)

    def render(self):
        return self._env.render()

    def close(self):
        self._env.close()


# ─────────────────────────────────────────────────────────────
# Curriculum builder
# ─────────────────────────────────────────────────────────────

def build_curriculum(
    episode_days: int = 1825,
    data_dir:     str = "data",
) -> tuple[list[SimConfig], list[float]]:
    """Return (configs, weights) for curriculum training.

    Regime weights:
      Bears / challenging  → weight 3.0   (~45% of draws)
      Realistic multi-phase→ weight 2.0   (~15%)
      Real token data      → weight 2.5   (~20%)
      Neutral / choppy     → weight 1.5   (~12%)
      Bull                 → weight 1.0   (~8%)

    The heavy bear weighting is deliberate: this is where the previous model
    underperformed and where real altcoin markets spend most of their time.
    """
    D = episode_days

    BASE = dict(
        initial_users=1_000,
        initial_merchants=100,
        max_daily_signups=500,
        episode_days=D,
    )

    configs: list[SimConfig] = []
    weights: list[float]     = []

    def add(cfg: SimConfig, w: float) -> None:
        configs.append(cfg)
        weights.append(w)

    # ══ BEAR / CHALLENGING  (weight 3.0) ════════════════════════════════

    # 1. Deep prolonged bear — CELO/ALGO style 2022-2025
    add(SimConfig(**BASE, initial_sentiment=0.28, market_phase_schedule=[
        (0,       D//5,   0.22, 0.05),
        (D//5,    2*D//5, 0.24, 0.04),
        (2*D//5,  3*D//5, 0.28, 0.03),
        (3*D//5,  4*D//5, 0.32, 0.03),
        (4*D//5,  D,      0.38, 0.03),
    ]), 3.0)

    # 2. Bear with mid-winter relief rally (fake-out then lower low)
    add(SimConfig(**BASE, initial_sentiment=0.30, market_phase_schedule=[
        (0,        D//4,    0.25, 0.04),
        (D//4,     D*3//8,  0.50, 0.05),
        (D*3//8,   D*3//4,  0.25, 0.04),
        (D*3//4,   D,       0.38, 0.03),
    ]), 3.0)

    # 3. Slow grind bear — no sharp crashes, just continuous erosion
    add(SimConfig(**BASE, initial_sentiment=0.38, market_phase_schedule=[
        (0,       D//3,    0.38, 0.02),
        (D//3,    2*D//3,  0.34, 0.02),
        (2*D//3,  D,       0.36, 0.02),
    ]), 3.0)

    # 4. Altcoin death spiral — never recovers (stress test)
    add(SimConfig(**BASE, initial_sentiment=0.25, market_phase_schedule=[
        (0, D, 0.23, 0.02),
    ]), 3.0)

    # 5. V-crash: brief bull → sharp crash → full recovery
    add(SimConfig(**BASE, initial_sentiment=0.45, market_phase_schedule=[
        (0,       D//6,   0.60, 0.04),
        (D//6,    D//2,   0.20, 0.05),
        (D//2,    D,      0.60, 0.04),
    ]), 3.0)

    # 6. Bear + LOW treasury (treasury-floor stress test)
    add(SimConfig(**BASE,
        initial_treasury_stable=700_000,
        initial_sentiment=0.28,
        market_phase_schedule=[
            (0,      D//2,  0.25, 0.04),
            (D//2,   D,     0.40, 0.03),
        ],
    ), 3.0)

    # 7. Double-dip bear (W-shape — two crashes, partial recovery between)
    add(SimConfig(**BASE, initial_sentiment=0.35, market_phase_schedule=[
        (0,       D//5,    0.55, 0.04),  # brief pump
        (D//5,    D*2//5,  0.22, 0.05),  # first crash
        (D*2//5,  D*3//5,  0.48, 0.04),  # dead-cat bounce
        (D*3//5,  D*4//5,  0.20, 0.05),  # second crash
        (D*4//5,  D,       0.40, 0.03),  # slow recovery
    ]), 3.0)

    # 8. MATIC-style: bull → 2022 crash → slow grind back
    add(SimConfig(**BASE, initial_sentiment=0.55, market_phase_schedule=[
        (0,       D//3,    0.65, 0.04),
        (D//3,    D*5//8,  0.28, 0.05),
        (D*5//8,  D,       0.45, 0.03),
    ]), 3.0)

    # ══ REALISTIC MULTI-PHASE (weight 2.0) ══════════════════════════════

    # 9. Full 5-phase realistic cycle (primary eval scenario)
    add(SimConfig(**BASE, initial_sentiment=0.55, market_phase_schedule=[
        (0,             D//5,          0.60, 0.03),
        (D//5,          2*D//5,        0.75, 0.04),
        (2*D//5,        int(D*0.55),   0.20, 0.06),
        (int(D*0.55),   int(D*0.75),   0.45, 0.04),
        (int(D*0.75),   D,             0.55, 0.02),
    ]), 2.0)

    # 10. Late-start bull: long bear accumulation → explosive breakout
    add(SimConfig(**BASE, initial_sentiment=0.35, market_phase_schedule=[
        (0,       D//2,    0.32, 0.02),
        (D//2,    3*D//4,  0.65, 0.05),
        (3*D//4,  D,       0.70, 0.03),
    ]), 2.0)

    # 11. Bear-then-mature: crashes hard, stabilises at lower equilibrium
    add(SimConfig(**BASE, initial_sentiment=0.40, market_phase_schedule=[
        (0,       D//4,    0.25, 0.05),
        (D//4,    D//2,    0.30, 0.03),
        (D//2,    D,       0.50, 0.02),
    ]), 2.0)

    # ══ NEUTRAL / CHOPPY (weight 1.5) ════════════════════════════════════

    # 12. Classic sideways
    add(SimConfig(**BASE, initial_sentiment=0.50), 1.5)

    # 13. Whipsaw — violent quarterly swings
    add(SimConfig(**BASE, initial_sentiment=0.50, market_phase_schedule=[
        (0,        D//4,    0.68, 0.06),
        (D//4,     D//2,    0.28, 0.06),
        (D//2,     3*D//4,  0.68, 0.06),
        (3*D//4,   D,       0.32, 0.06),
    ]), 1.5)

    # 14. Muted neutral — very low volatility
    add(SimConfig(**BASE, initial_sentiment=0.50,
        sentiment_drift=0.005,
        market_phase_schedule=[(0, D, 0.48, 0.01)],
    ), 1.5)

    # ══ BULL (weight 1.0) ════════════════════════════════════════════════

    # 15. Steady bull
    add(SimConfig(**BASE, initial_sentiment=0.65, market_phase_schedule=[
        (0,       D//3,    0.60, 0.03),
        (D//3,    2*D//3,  0.68, 0.03),
        (2*D//3,  D,       0.72, 0.03),
    ]), 1.0)

    # 16. BTC-style: bear start → monster bull
    add(SimConfig(**BASE, initial_sentiment=0.45, market_phase_schedule=[
        (0,       D//3,    0.40, 0.03),
        (D//3,    D*2//3,  0.70, 0.05),
        (D*2//3,  D,       0.75, 0.04),
    ]), 1.0)

    # 17. Parabolic + correction
    add(SimConfig(**BASE, initial_sentiment=0.60, market_phase_schedule=[
        (0,       D//4,    0.72, 0.05),
        (D//4,    D//2,    0.82, 0.05),
        (D//2,    3*D//4,  0.32, 0.05),
        (3*D//4,  D,       0.55, 0.03),
    ]), 1.0)

    # 18. Baseline neutral
    add(SimConfig(**BASE, initial_sentiment=0.55), 1.0)

    # ══ REAL MARKET DATA (weight 2.5 each) ════════════════════════════════

    real_tokens      = ["celo", "matic", "algo", "btc"]
    real_added       = 0
    for token in real_tokens:
        path = Path(data_dir) / f"{token}_daily.json"
        if not path.exists():
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            prices  = data["close_prices"]
            from chainenv.real_sentiment import prices_to_sentiment
            p_slice = (prices[-episode_days:] if len(prices) >= episode_days
                       else prices + [prices[-1]] * (episode_days - len(prices)))
            seq = prices_to_sentiment(p_slice, rng_seed=42)
            add(SimConfig(**BASE, sentiment_override_sequence=seq), 2.5)
            real_added += 1
        except Exception:
            pass

    # ── summary ──────────────────────────────────────────────────────────
    total_w = sum(weights)
    bear_pct  = sum(w for c, w in zip(configs, weights)
                    if c.market_phase_schedule and
                    (c.sentiment_override_sequence is None) and
                    c.initial_sentiment < 0.45) / total_w * 100
    real_pct  = real_added * 2.5 / total_w * 100
    print(f"  Curriculum: {len(configs)} configs  "
          f"(bear/stress~{bear_pct:.0f}%  real~{real_pct:.0f}%  "
          f"neutral+bull~{100-bear_pct-real_pct:.0f}%)")

    return configs, weights


# ─────────────────────────────────────────────────────────────
# Env factories
# ─────────────────────────────────────────────────────────────

def make_env_single(cfg: SimConfig, seed: int = 0):
    def _init():
        env = Monitor(PaytknEnv(cfg))
        env.reset(seed=seed)
        return env
    return _init


def make_env_curriculum(configs, weights, seed: int = 0):
    def _init():
        return Monitor(MarketCurriculumEnv(configs, weights=weights, seed=seed))
    return _init


# ─────────────────────────────────────────────────────────────
# LR schedule
# ─────────────────────────────────────────────────────────────

def linear_schedule(lr_start: float, lr_end: float):
    """Linearly anneal learning rate from lr_start to lr_end."""
    def func(progress_remaining: float) -> float:
        # progress_remaining: 1.0 at start → 0.0 at end
        return lr_end + (lr_start - lr_end) * progress_remaining
    return func


# ─────────────────────────────────────────────────────────────
# Training
# ─────────────────────────────────────────────────────────────

def train(
    timesteps:     int   = 5_000_000,
    n_envs:        int   = 8,
    name:          str   = "paytkn_ppo",
    episode_days:  int   = 1825,
    curriculum:    bool  = True,
    large_net:     bool  = True,
    anneal_lr:     bool  = True,
    continue_from: str | None = None,
    data_dir:      str   = "data",
) -> PPO:

    os.makedirs("models", exist_ok=True)
    os.makedirs("tensorboard_logs", exist_ok=True)

    # ── Environments ──────────────────────────────────────────────────
    if curriculum:
        configs, weights = build_curriculum(episode_days=episode_days,
                                            data_dir=data_dir)
        vec_env  = make_vec_env(
            make_env_curriculum(configs, weights, seed=0),
            n_envs=n_envs,
            vec_env_cls=SubprocVecEnv,
        )
        # Eval on the realistic 5-phase scenario (config index 8)
        eval_env = Monitor(PaytknEnv(configs[8]))
        env_label = f"curriculum ({len(configs)} regimes, weighted)"
    else:
        cfg = SimConfig(
            initial_users=1_000, initial_merchants=100,
            max_daily_signups=500, episode_days=episode_days,
        )
        vec_env  = make_vec_env(make_env_single(cfg, seed=0),
                                n_envs=n_envs, vec_env_cls=SubprocVecEnv)
        eval_env = Monitor(PaytknEnv(cfg))
        env_label = "single neutral config"

    eval_env.reset(seed=99)

    # ── Hyperparameters ────────────────────────────────────────────────
    lr_start    = 3e-4
    lr_end      = 5e-5
    learning_rate = linear_schedule(lr_start, lr_end) if anneal_lr else lr_start

    n_steps_    = 4096
    batch_size_ = 512
    gamma_      = 0.999
    ent_coef_   = 0.005

    # Network: [256, 256, 128] gives 10× more capacity than default [64, 64]
    # Needed for the agent to learn conditional policies (bear vs bull behaviour)
    policy_kwargs = dict(net_arch=[256, 256, 128]) if large_net else {}

    est_steps_sec = 170 * n_envs
    est_hrs = timesteps / est_steps_sec / 3600

    print(f"\n{'='*60}")
    print(f"  ChainEnv v3 — PPO Training  (best-possible mode)")
    print(f"  Run:          {name}")
    print(f"  Timesteps:    {timesteps:,}")
    print(f"  Envs:         {n_envs}   ({env_label})")
    print(f"  Episode:      {episode_days}d  ({episode_days/365:.1f} yr)")
    print(f"  Network:      {'[256,256,128]' if large_net else '[64,64] (default)'}")
    print(f"  LR:           {'annealing ' + str(lr_start) + ' -> ' + str(lr_end) if anneal_lr else lr_start}")
    print(f"  Est. time:    ~{est_hrs:.1f} hrs  (at ~{est_steps_sec} steps/s)")
    if continue_from:
        print(f"  Warmstart:    {continue_from}")
    print(f"{'='*60}\n")

    # ── Callbacks ─────────────────────────────────────────────────────
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path="models/",
        log_path="models/eval_logs/",
        eval_freq=max(1000, timesteps // 80),   # ~80 evaluations over training
        n_eval_episodes=5,
        deterministic=True,
        verbose=1,
    )
    checkpoint_callback = CheckpointCallback(
        save_freq=max(1000, timesteps // 10),
        save_path="models/",
        name_prefix=name,
        verbose=0,
    )

    # ── Build or load model ────────────────────────────────────────────
    if continue_from and os.path.exists(continue_from):
        print(f"  Loading checkpoint: {continue_from}")
        model = PPO.load(
            continue_from,
            env=vec_env,
            # Keep original architecture — cannot change net size on load
            device="cpu",
            verbose=1,
            tensorboard_log="tensorboard_logs/",
        )
        # Update LR and entropy if annealing
        if anneal_lr:
            model.learning_rate = learning_rate
            model._setup_lr_schedule()
        print(f"  Checkpoint loaded. Continuing from existing weights.\n")
        if large_net:
            print("  NOTE: --large-net ignored when --continue-from is set "
                  "(architecture must match checkpoint).")
    else:
        model = PPO(
            policy="MlpPolicy",
            env=vec_env,
            learning_rate=learning_rate,
            n_steps=n_steps_,
            batch_size=batch_size_,
            n_epochs=10,
            gamma=gamma_,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=ent_coef_,
            policy_kwargs=policy_kwargs if not continue_from else {},
            verbose=1,
            tensorboard_log="tensorboard_logs/",
            seed=42,
            device="cpu",
        )

    print(f"  n_steps={n_steps_}  batch={batch_size_}  "
          f"gamma={gamma_}  ent_coef={ent_coef_}\n")

    model.learn(
        total_timesteps=timesteps,
        callback=[eval_callback, checkpoint_callback],
        tb_log_name=name,
        progress_bar=True,
        reset_num_timesteps=not bool(continue_from),
    )

    save_path = f"models/{name}_final"
    model.save(save_path)
    print(f"\nFinal model  -> {save_path}.zip")
    print(f"Best model   -> models/best_model.zip   (saved by EvalCallback)")

    vec_env.close()
    return model


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--timesteps",     type=int,  default=5_000_000)
    parser.add_argument("--envs",          type=int,  default=8)
    parser.add_argument("--name",          type=str,  default="paytkn_ppo")
    parser.add_argument("--episode-days",  type=int,  default=1825)
    parser.add_argument("--curriculum",    action="store_true", default=True)
    parser.add_argument("--no-curriculum", action="store_false", dest="curriculum")
    parser.add_argument("--large-net",     action="store_true", default=True)
    parser.add_argument("--no-large-net",  action="store_false", dest="large_net")
    parser.add_argument("--anneal-lr",     action="store_true", default=True)
    parser.add_argument("--no-anneal-lr",  action="store_false", dest="anneal_lr")
    parser.add_argument("--continue-from", type=str,  default=None,
                        help="Path to existing .zip checkpoint to warmstart from")
    parser.add_argument("--data-dir",      type=str,  default="data")
    args = parser.parse_args()

    train(
        timesteps=args.timesteps,
        n_envs=args.envs,
        name=args.name,
        episode_days=args.episode_days,
        curriculum=args.curriculum,
        large_net=args.large_net,
        anneal_lr=args.anneal_lr,
        continue_from=args.continue_from,
        data_dir=args.data_dir,
    )
