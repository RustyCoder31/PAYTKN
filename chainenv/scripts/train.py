"""PPO training script for ChainEnv.

Usage:
    cd chainenv
    python scripts/train.py [--timesteps 500000] [--envs 4] [--name run_001]

Outputs:
    models/<name>.zip         — trained policy checkpoint
    tensorboard_logs/<name>/  — TensorBoard event files
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import SubprocVecEnv
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
from stable_baselines3.common.monitor import Monitor

from chainenv.env import PaytknEnv
from chainenv.config import SimConfig


def make_env(cfg: SimConfig, seed: int = 0):
    def _init():
        env = PaytknEnv(cfg)
        env = Monitor(env)
        env.reset(seed=seed)
        return env
    return _init


def train(
    timesteps: int = 500_000,
    n_envs: int = 4,
    name: str = "paytkn_ppo",
    episode_days: int = 180,
    cfg: SimConfig | None = None,
) -> PPO:
    if cfg is None:
        # Lean training config — population capped to keep fps high.
        # Steady-state users = max_daily_signups / base_churn_rate (0.001).
        # For long episodes (5yr), uncapped = 100k users → fps crashes to 5.
        # Cap: max_daily_signups=15 → steady state ~15k users → fps ~100+.
        # Policy still transfers to full scale at eval time.
        max_signups = 15 if episode_days >= 365 else 100
        cfg = SimConfig(
            initial_users=200,
            initial_merchants=20,
            max_daily_signups=max_signups,
            episode_days=episode_days,
        )

    os.makedirs("models", exist_ok=True)
    os.makedirs("tensorboard_logs", exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  ChainEnv — PPO Training")
    print(f"  Run: {name}")
    print(f"  Timesteps: {timesteps:,}")
    print(f"  Parallel envs: {n_envs}")
    print(f"  Episode days: {cfg.episode_days}  ({cfg.episode_days/365:.1f} years)")
    est_hrs = timesteps / 170 / 3600   # ~170 env steps/sec on CPU with 4 envs
    print(f"  Est. duration: ~{est_hrs:.1f} hrs  (at ~170 steps/sec)")
    print(f"{'='*60}\n")

    # SubprocVecEnv: true parallel processes (one per CPU core)
    # Each env runs in its own process — eliminates Python GIL bottleneck
    vec_env = make_vec_env(
        make_env(cfg, seed=0),
        n_envs=n_envs,
        vec_env_cls=SubprocVecEnv,
    )

    # Separate eval env (single, seed=99)
    eval_env = Monitor(PaytknEnv(cfg))
    eval_env.reset(seed=99)

    # Callbacks
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=f"models/",
        log_path=f"models/eval_logs/",
        eval_freq=max(1000, timesteps // 50),
        n_eval_episodes=3,
        deterministic=True,
        verbose=1,
    )
    checkpoint_callback = CheckpointCallback(
        save_freq=max(1000, timesteps // 10),
        save_path="models/",
        name_prefix=name,
        verbose=0,
    )

    # Tune hyperparameters based on episode length
    # Long episodes (>365 days): larger rollout buffer, higher gamma, lower LR
    long_horizon = cfg.episode_days >= 365
    n_steps_    = 4096  if long_horizon else 2048   # capture more of each episode per update
    batch_size_ = 512   if long_horizon else 256
    lr_         = 2e-4  if long_horizon else 3e-4   # smaller LR for stable long-horizon learning
    gamma_      = 0.999 if long_horizon else 0.995  # discount further into the future
    ent_coef_   = 0.005 if long_horizon else 0.01   # less exploration needed — longer episodes

    model = PPO(
        policy="MlpPolicy",
        env=vec_env,
        learning_rate=lr_,
        n_steps=n_steps_,
        batch_size=batch_size_,
        n_epochs=10,
        gamma=gamma_,         # high discount — long-term treasury health matters
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=ent_coef_,
        verbose=1,
        tensorboard_log="tensorboard_logs/",
        seed=42,
        device="cpu",         # MlpPolicy trains faster on CPU (SB3 recommendation for non-CNN)
    )
    print(f"  Hyperparams: n_steps={n_steps_}, batch={batch_size_}, lr={lr_}, gamma={gamma_}")

    model.learn(
        total_timesteps=timesteps,
        callback=[eval_callback, checkpoint_callback],
        tb_log_name=name,
        progress_bar=True,
    )

    save_path = f"models/{name}_final"
    model.save(save_path)
    print(f"\nModel saved -> {save_path}.zip")
    print(f"TensorBoard -> tensorboard_logs/{name}")
    print(f"  Run: tensorboard --logdir tensorboard_logs/")

    vec_env.close()
    return model


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train PPO on ChainEnv")
    parser.add_argument("--timesteps",    type=int, default=500_000)
    parser.add_argument("--envs",         type=int, default=4)
    parser.add_argument("--name",         type=str, default="paytkn_ppo")
    parser.add_argument("--episode-days", type=int, default=180,
                        help="Episode length in days (180=6mo, 365=1yr, 1825=5yr)")
    args = parser.parse_args()

    train(timesteps=args.timesteps, n_envs=args.envs, name=args.name,
          episode_days=args.episode_days)
