"""PPO training script for ChainEnv.

Usage:
    cd chainenv
    python scripts/train.py [--timesteps 3000000] [--envs 8] [--name run_v2]

    # Curriculum training (recommended — bear/neutral/bull + real market data):
    python scripts/train.py --timesteps 3000000 --envs 8 --curriculum --name bear_robust_v1

Outputs:
    models/best_model.zip         — best checkpoint (by eval reward)
    models/<name>_final.zip       — final checkpoint
    tensorboard_logs/<name>/      — TensorBoard event files
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
# Curriculum wrapper
# ─────────────────────────────────────────────────────────────

class MarketCurriculumEnv(gym.Env):
    """Gymnasium env that randomly samples a SimConfig on every episode reset.

    Trains the agent across diverse market regimes simultaneously — bear,
    neutral, bull, realistic multi-phase, and real historical sequences.
    Each parallel env independently samples its regime at each reset,
    so the model always sees all market types within one training run.
    """

    metadata = {"render_modes": []}

    def __init__(self, configs: list[SimConfig], seed: int = 0):
        super().__init__()
        self._configs    = configs
        self._rng        = np.random.default_rng(seed)
        # Bootstrap with first config so spaces are defined immediately
        self._env        = PaytknEnv(configs[0])
        self.observation_space = self._env.observation_space
        self.action_space      = self._env.action_space

    def reset(self, *, seed=None, options=None):
        # Pick a new random regime for this episode
        idx = int(self._rng.integers(len(self._configs)))
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

def _phase(days: int, phases: list[tuple]) -> list:
    """Helper: list of (start, end, target_sentiment, drift) phase tuples."""
    return phases


def build_curriculum(
    episode_days: int = 1825,
    data_dir: str = "data",
) -> list[SimConfig]:
    """Build a list of SimConfigs covering bear / neutral / bull / realistic / real.

    Regime distribution (approximate, by weight in list):
      40%  Bear-heavy  (deep crash, slow grind, bear+recovery, altcoin death)
      25%  Mixed/neutral (choppy, volatile, sideways)
      20%  Bull (breakout, steady climb, parabolic + correction)
      15%  Realistic multi-phase (launch -> bull -> crash -> recovery -> mature)

    If real market data JSON files exist in data_dir, those are appended as
    extra configs (CELO, MATIC, ALGO, BTC individual + composite).
    """
    D = episode_days

    # ── Base population (realistic launch scale) ──────────────────────
    BASE = dict(
        initial_users=1_000,
        initial_merchants=100,
        max_daily_signups=500,
        episode_days=D,
    )

    configs: list[SimConfig] = []

    # ══ BEAR REGIMES (40%) ══════════════════════════════════════════════

    # 1. Deep prolonged bear — like CELO/ALGO 2022-2025
    configs.append(SimConfig(**BASE, initial_sentiment=0.28, market_phase_schedule=[
        (0,         D//5,     0.22, 0.05),   # hard crash opening
        (D//5,      2*D//5,   0.24, 0.04),   # still falling
        (2*D//5,    3*D//5,   0.28, 0.03),   # bottoming
        (3*D//5,    4*D//5,   0.32, 0.03),   # tentative recovery
        (4*D//5,    D,        0.38, 0.03),   # slow climb out
    ]))

    # 2. Bear with mid-winter relief rally (realistic — one fake-out then down again)
    configs.append(SimConfig(**BASE, initial_sentiment=0.30, market_phase_schedule=[
        (0,         D//4,     0.25, 0.04),   # initial crash
        (D//4,      D*3//8,   0.50, 0.05),   # relief rally
        (D*3//8,    D*3//4,   0.25, 0.04),   # sell the rally, lower low
        (D*3//4,    D,        0.38, 0.03),   # eventual base
    ]))

    # 3. Slow grind bear — sentiment stays 0.30-0.40, no sharp crashes
    configs.append(SimConfig(**BASE, initial_sentiment=0.38, market_phase_schedule=[
        (0,         D//3,     0.38, 0.02),
        (D//3,      2*D//3,   0.34, 0.02),
        (2*D//3,    D,        0.36, 0.02),
    ]))

    # 4. Altcoin death spiral — never recovers (worst case, small weight)
    configs.append(SimConfig(**BASE, initial_sentiment=0.25, market_phase_schedule=[
        (0,         D,        0.23, 0.02),   # persistent bear throughout
    ]))

    # 5. Crash then real recovery (V-shape — tests adaptability under stress)
    configs.append(SimConfig(**BASE, initial_sentiment=0.45, market_phase_schedule=[
        (0,         D//6,     0.60, 0.04),   # honeymoon bull
        (D//6,      D//2,     0.20, 0.05),   # sharp crash
        (D//2,      D,        0.60, 0.04),   # full recovery
    ]))

    # 6. Bear with LOW treasury stress (tests treasury-floor defense)
    configs.append(SimConfig(**BASE,
        initial_treasury_stable=700_000,     # below comfortable level
        initial_sentiment=0.28,
        market_phase_schedule=[
            (0,     D//2,   0.25, 0.04),
            (D//2,  D,      0.40, 0.03),
        ],
    ))

    # ══ NEUTRAL / CHOPPY (25%) ═══════════════════════════════════════════

    # 7. Classic sideways — mean-reverting around 0.5
    configs.append(SimConfig(**BASE, initial_sentiment=0.50))

    # 8. Highly volatile / whipsaw — sentiment swings every quarter
    configs.append(SimConfig(**BASE, initial_sentiment=0.50, market_phase_schedule=[
        (0,         D//4,   0.65, 0.06),
        (D//4,      D//2,   0.30, 0.06),
        (D//2,      3*D//4, 0.65, 0.06),
        (3*D//4,    D,      0.35, 0.06),
    ]))

    # 9. Muted neutral — low drift, very stable (tests patience)
    configs.append(SimConfig(**BASE, initial_sentiment=0.50,
        sentiment_drift=0.005,
        market_phase_schedule=[(0, D, 0.48, 0.01)],
    ))

    # 10. MATIC-style — mixed start, sharp 2022-style crash, mild recovery
    configs.append(SimConfig(**BASE, initial_sentiment=0.55, market_phase_schedule=[
        (0,         D//3,   0.65, 0.04),   # bull run
        (D//3,      D*5//8, 0.30, 0.05),   # 2022 crash
        (D*5//8,    D,      0.45, 0.03),   # slow grind back
    ]))

    # ══ BULL REGIMES (20%) ═══════════════════════════════════════════════

    # 11. Steady bull — gradual appreciation with noise
    configs.append(SimConfig(**BASE, initial_sentiment=0.65, market_phase_schedule=[
        (0,         D//3,   0.60, 0.03),
        (D//3,      2*D//3, 0.68, 0.03),
        (2*D//3,    D,      0.72, 0.03),
    ]))

    # 12. BTC-style — bear start, monster bull in second half
    configs.append(SimConfig(**BASE, initial_sentiment=0.45, market_phase_schedule=[
        (0,         D//3,   0.40, 0.03),   # consolidation / mild bear
        (D//3,      D*2//3, 0.70, 0.05),   # breakout
        (D*2//3,    D,      0.75, 0.04),   # continued bull
    ]))

    # 13. Parabolic + correction (classic 2021 pattern)
    configs.append(SimConfig(**BASE, initial_sentiment=0.60, market_phase_schedule=[
        (0,         D//4,   0.70, 0.05),   # initial pump
        (D//4,      D//2,   0.80, 0.05),   # parabolic top
        (D//2,      3*D//4, 0.35, 0.05),   # correction
        (3*D//4,    D,      0.55, 0.03),   # new floor
    ]))

    # ══ REALISTIC MULTI-PHASE (15%) ═══════════════════════════════════════

    # 14. 5-phase realistic cycle (same as evaluate.py "realistic" scenario)
    configs.append(SimConfig(**BASE, initial_sentiment=0.55, market_phase_schedule=[
        (0,         D//5,         0.60, 0.03),  # launch enthusiasm
        (D//5,      2*D//5,       0.75, 0.04),  # bull run
        (2*D//5,    int(D*0.55),  0.20, 0.06),  # crash
        (int(D*0.55), int(D*0.75), 0.45, 0.04), # recovery
        (int(D*0.75), D,          0.55, 0.02),  # mature market
    ]))

    # 15. Late-start bull (tests delayed gratification)
    configs.append(SimConfig(**BASE, initial_sentiment=0.35, market_phase_schedule=[
        (0,         D//2,   0.32, 0.02),   # long bear accumulation
        (D//2,      3*D//4, 0.65, 0.05),   # breakout
        (3*D//4,    D,      0.70, 0.03),   # sustained bull
    ]))

    # 16. Standard baseline (keep some purely simulated neutral episodes)
    configs.append(SimConfig(**BASE, initial_sentiment=0.55))

    # ══ REAL MARKET DATA (if available) ═══════════════════════════════════

    real_tokens = ["celo", "matic", "algo", "btc"]
    real_configs_added = 0
    for token in real_tokens:
        path = Path(data_dir) / f"{token}_daily.json"
        if not path.exists():
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            prices = data["close_prices"]

            # Build sentiment sequence (import here to avoid top-level dep at module load)
            from chainenv.real_sentiment import prices_to_sentiment
            if len(prices) >= episode_days:
                p_slice = prices[-episode_days:]
            else:
                p_slice = prices + [prices[-1]] * (episode_days - len(prices))

            seq = prices_to_sentiment(p_slice, rng_seed=42)
            configs.append(SimConfig(**BASE, sentiment_override_sequence=seq))
            real_configs_added += 1
        except Exception:
            pass  # silently skip if data is malformed

    # ── Print summary ─────────────────────────────────────────────────
    bear_n    = 6
    neutral_n = 4
    bull_n    = 3
    real_n    = real_configs_added
    sim_n     = len(configs) - real_n
    print(f"  Curriculum: {len(configs)} configs  "
          f"(bear={bear_n}, neutral={neutral_n}, bull={bull_n}, "
          f"realistic=2, real={real_n})")

    return configs


# ─────────────────────────────────────────────────────────────
# Env factories
# ─────────────────────────────────────────────────────────────

def make_env(cfg: SimConfig, seed: int = 0):
    """Single-config env factory (original behaviour)."""
    def _init():
        env = PaytknEnv(cfg)
        env = Monitor(env)
        env.reset(seed=seed)
        return env
    return _init


def make_curriculum_env(configs: list[SimConfig], seed: int = 0):
    """Curriculum env factory — random regime per episode."""
    def _init():
        env = MarketCurriculumEnv(configs, seed=seed)
        env = Monitor(env)
        return env
    return _init


# ─────────────────────────────────────────────────────────────
# Training entry point
# ─────────────────────────────────────────────────────────────

def train(
    timesteps:    int  = 3_000_000,
    n_envs:       int  = 8,
    name:         str  = "paytkn_ppo",
    episode_days: int  = 1825,
    curriculum:   bool = False,
    data_dir:     str  = "data",
    cfg:          SimConfig | None = None,
) -> PPO:

    os.makedirs("models", exist_ok=True)
    os.makedirs("tensorboard_logs", exist_ok=True)

    # ── Build environment(s) ──────────────────────────────────────────
    if curriculum:
        configs   = build_curriculum(episode_days=episode_days, data_dir=data_dir)
        env_label = f"curriculum ({len(configs)} regimes)"
        vec_env   = make_vec_env(
            make_curriculum_env(configs, seed=0),
            n_envs=n_envs,
            vec_env_cls=SubprocVecEnv,
        )
        # Eval env: use the realistic 5-phase config (index 13) for stable comparison
        eval_cfg = configs[13]
        eval_env = Monitor(PaytknEnv(eval_cfg))
    else:
        if cfg is None:
            cfg = SimConfig(
                initial_users=1_000,
                initial_merchants=100,
                max_daily_signups=500,
                episode_days=episode_days,
            )
        env_label = f"single config  (sentiment={cfg.initial_sentiment})"
        vec_env   = make_vec_env(
            make_env(cfg, seed=0),
            n_envs=n_envs,
            vec_env_cls=SubprocVecEnv,
        )
        eval_env = Monitor(PaytknEnv(cfg))

    eval_env.reset(seed=99)

    est_hrs = timesteps / (170 * n_envs) / 3600
    print(f"\n{'='*60}")
    print(f"  ChainEnv v2 — PPO Training")
    print(f"  Run:         {name}")
    print(f"  Timesteps:   {timesteps:,}")
    print(f"  Envs:        {n_envs}  ({env_label})")
    print(f"  Episode:     {episode_days}d  ({episode_days/365:.1f} yr)")
    print(f"  Est. time:   ~{est_hrs:.1f} hrs")
    print(f"{'='*60}\n")

    # ── Callbacks ────────────────────────────────────────────────────
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path="models/",
        log_path="models/eval_logs/",
        eval_freq=max(1000, timesteps // 60),
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

    # ── Hyperparameters ───────────────────────────────────────────────
    # Long horizon (5yr episodes): large buffer, high gamma, low LR, low entropy
    n_steps_    = 4096
    batch_size_ = 512
    lr_         = 2e-4
    gamma_      = 0.999
    ent_coef_   = 0.005

    model = PPO(
        policy="MlpPolicy",
        env=vec_env,
        learning_rate=lr_,
        n_steps=n_steps_,
        batch_size=batch_size_,
        n_epochs=10,
        gamma=gamma_,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=ent_coef_,
        verbose=1,
        tensorboard_log="tensorboard_logs/",
        seed=42,
        device="cpu",
    )
    print(f"  Hyperparams: n_steps={n_steps_}, batch={batch_size_}, "
          f"lr={lr_}, gamma={gamma_}, ent_coef={ent_coef_}")

    model.learn(
        total_timesteps=timesteps,
        callback=[eval_callback, checkpoint_callback],
        tb_log_name=name,
        progress_bar=True,
    )

    save_path = f"models/{name}_final"
    model.save(save_path)
    print(f"\nModel saved -> {save_path}.zip")
    print(f"Best model  -> models/best_model.zip")
    print(f"TensorBoard -> tensorboard_logs/{name}")

    vec_env.close()
    return model


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train PPO on ChainEnv")
    parser.add_argument("--timesteps",    type=int,  default=3_000_000)
    parser.add_argument("--envs",         type=int,  default=8)
    parser.add_argument("--name",         type=str,  default="paytkn_ppo")
    parser.add_argument("--episode-days", type=int,  default=1825)
    parser.add_argument("--curriculum",   action="store_true",
                        help="Use diverse market curriculum (bear/neutral/bull/real)")
    parser.add_argument("--data-dir",     type=str,  default="data",
                        help="Directory containing *_daily.json files for real sentiment")
    args = parser.parse_args()

    train(
        timesteps=args.timesteps,
        n_envs=args.envs,
        name=args.name,
        episode_days=args.episode_days,
        curriculum=args.curriculum,
        data_dir=args.data_dir,
    )
