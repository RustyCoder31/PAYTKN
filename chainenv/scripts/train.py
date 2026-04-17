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
    cfg: SimConfig | None = None,
) -> PPO:
    cfg = cfg or SimConfig()

    os.makedirs("models", exist_ok=True)
    os.makedirs("tensorboard_logs", exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  ChainEnv — PPO Training")
    print(f"  Run: {name}")
    print(f"  Timesteps: {timesteps:,}")
    print(f"  Parallel envs: {n_envs}")
    print(f"  Episode days: {cfg.episode_days}")
    print(f"{'='*60}\n")

    # Vectorised training envs
    vec_env = make_vec_env(
        make_env(cfg, seed=0),
        n_envs=n_envs,
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

    model = PPO(
        policy="MlpPolicy",
        env=vec_env,
        learning_rate=3e-4,
        n_steps=2048,
        batch_size=256,
        n_epochs=10,
        gamma=0.995,          # high discount — long-term treasury health matters
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.01,        # mild entropy bonus for exploration
        verbose=1,
        tensorboard_log="tensorboard_logs/",
        seed=42,
    )

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
    parser.add_argument("--timesteps", type=int, default=500_000)
    parser.add_argument("--envs", type=int, default=4)
    parser.add_argument("--name", type=str, default="paytkn_ppo")
    args = parser.parse_args()

    train(timesteps=args.timesteps, n_envs=args.envs, name=args.name)
