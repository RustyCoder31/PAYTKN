"""Evaluation script — RL agent vs static baseline, across 3 sentiment starts.

Usage:
    cd chainenv
    python scripts/evaluate.py --model models/paytkn_ppo_final.zip

Outputs:
    Printed table of RL vs baseline metrics across bear / neutral / bull starts.
    models/eval_results.json — full numeric results for downstream analysis.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from stable_baselines3 import PPO

from chainenv.env import PaytknEnv
from chainenv.config import SimConfig


# ─────────────────────────────────────────────────────────────
# Static baseline agent
# ─────────────────────────────────────────────────────────────

def static_action(obs: np.ndarray) -> np.ndarray:
    """Midpoint (zero-action) — equivalent to hardcoded mid-range parameters."""
    return np.zeros(5, dtype=np.float32)


# ─────────────────────────────────────────────────────────────
# Scenario definitions
# ─────────────────────────────────────────────────────────────

SCENARIOS = {
    "bear":    {"initial_sentiment": 0.25, "rng_seed": 10},
    "neutral": {"initial_sentiment": 0.50, "rng_seed": 20},
    "bull":    {"initial_sentiment": 0.75, "rng_seed": 30},
}


def make_scenario_cfg(scenario: dict) -> SimConfig:
    base = SimConfig()
    base.initial_sentiment = scenario["initial_sentiment"]
    base.rng_seed = scenario["rng_seed"]
    return base


# ─────────────────────────────────────────────────────────────
# Single episode runner
# ─────────────────────────────────────────────────────────────

def run_episode(env: PaytknEnv, policy, seed: int) -> dict:
    obs, _ = env.reset(seed=seed)
    total_reward = 0.0
    done = False
    metrics_log = []

    while not done:
        if policy == "static":
            action = static_action(obs)
        else:
            action, _ = policy.predict(obs, deterministic=True)

        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        done = terminated or truncated

    # Collect final-day snapshot
    m = env._episode_metrics
    last = m[-1] if m else {}

    return {
        "total_reward": total_reward,
        "final_price": last.get("price", 1.0),
        "final_treasury_stable": last.get("treasury_stable", 0.0),
        "final_treasury_paytkn": last.get("treasury_paytkn", 0.0),
        "final_users": last.get("active_users", 0),
        "final_supply": last.get("total_supply", 0.0),
        "avg_daily_fees": float(np.mean([d["daily_fees"] for d in m])) if m else 0.0,
        "avg_daily_rewards": float(np.mean([d["daily_rewards"] for d in m])) if m else 0.0,
        "avg_sentiment": float(np.mean([d["sentiment"] for d in m])) if m else 0.0,
        "avg_staked": float(np.mean([d["staked"] for d in m])) if m else 0.0,
    }


# ─────────────────────────────────────────────────────────────
# Main evaluation loop
# ─────────────────────────────────────────────────────────────

def evaluate(model_path: str, n_episodes: int = 3) -> dict:
    print(f"\n{'='*65}")
    print(f"  ChainEnv Evaluation  |  Model: {model_path}")
    print(f"  Scenarios: bear / neutral / bull  |  Episodes each: {n_episodes}")
    print(f"{'='*65}\n")

    model = PPO.load(model_path)
    all_results = {}

    header = f"{'Scenario':<10} {'Agent':<10} {'Reward':>10} {'Price':>8} {'Users':>8} {'Treasury$':>12} {'Fees/day':>10}"
    print(header)
    print("-" * len(header))

    for scenario_name, scenario_cfg in SCENARIOS.items():
        cfg = make_scenario_cfg(scenario_cfg)
        results = {"rl": [], "static": []}

        for ep in range(n_episodes):
            seed = scenario_cfg["rng_seed"] + ep * 100

            env_rl = PaytknEnv(cfg)
            rl_result = run_episode(env_rl, model, seed=seed)
            results["rl"].append(rl_result)

            env_static = PaytknEnv(cfg)
            static_result = run_episode(env_static, "static", seed=seed)
            results["static"].append(static_result)

        def avg(key, agent):
            return float(np.mean([r[key] for r in results[agent]]))

        for agent in ["rl", "static"]:
            print(
                f"{scenario_name:<10} {agent:<10} "
                f"{avg('total_reward', agent):>10.2f} "
                f"{avg('final_price', agent):>8.4f} "
                f"{avg('final_users', agent):>8.0f} "
                f"{avg('final_treasury_stable', agent):>12.0f} "
                f"{avg('avg_daily_fees', agent):>10.2f}"
            )

        all_results[scenario_name] = results
        print()

    # Save results
    os.makedirs("models", exist_ok=True)
    out_path = "models/eval_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"Full results saved → {out_path}")

    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate ChainEnv PPO agent")
    parser.add_argument("--model", type=str, default="models/best_model.zip")
    parser.add_argument("--episodes", type=int, default=3)
    args = parser.parse_args()
    evaluate(args.model, n_episodes=args.episodes)
