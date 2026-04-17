"""Revenue projections — Full P&L using the trained RL agent.

Runs N episodes and computes percentile bands for:
  - Cumulative fees collected (revenue)
  - Cumulative rewards paid (cost)
  - Net treasury position (treasury_stable - rewards)
  - Token supply curve
  - Token price trajectory

Usage:
    cd chainenv
    python scripts/projections.py --model models/paytkn_ppo_final.zip [--episodes 20] [--save]

Outputs:
    plots/projections.png
    models/projections.json
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from stable_baselines3 import PPO

from chainenv.env import PaytknEnv
from chainenv.config import SimConfig

BG = "#F8F9FA"
PALETTE = {
    "fees":     "#2ECC71",
    "rewards":  "#E74C3C",
    "net":      "#3498DB",
    "supply":   "#9B59B6",
    "price":    "#F39C12",
    "users":    "#1ABC9C",
}


def run_projection_episode(model, cfg: SimConfig, seed: int) -> dict:
    env = PaytknEnv(cfg)
    obs, _ = env.reset(seed=seed)
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, _ = env.step(action)
        done = terminated or truncated

    metrics = env._episode_metrics
    days = [d["day"] for d in metrics]
    cum_fees = np.cumsum([d["daily_fees"] for d in metrics])
    cum_rewards = np.cumsum([d["daily_rewards"] for d in metrics])

    return {
        "days": days,
        "cumulative_fees": cum_fees.tolist(),
        "cumulative_rewards": cum_rewards.tolist(),
        "net_treasury": (cum_fees - cum_rewards).tolist(),
        "treasury_stable": [d["treasury_stable"] for d in metrics],
        "supply": [d["total_supply"] for d in metrics],
        "price": [d["price"] for d in metrics],
        "users": [d["active_users"] for d in metrics],
        "sentiment": [d["sentiment"] for d in metrics],
    }


def compute_bands(runs: list[dict], key: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (p10, p50, p90) percentile bands across runs."""
    arrays = np.array([r[key] for r in runs])
    return (
        np.percentile(arrays, 10, axis=0),
        np.percentile(arrays, 50, axis=0),
        np.percentile(arrays, 90, axis=0),
    )


def plot_projections(model_path: str, n_episodes: int = 20, save: bool = False) -> None:
    model = PPO.load(model_path)
    cfg = SimConfig()

    print(f"\nRunning {n_episodes} projection episodes...")
    runs = []
    for i in range(n_episodes):
        seed = 1000 + i * 7
        run = run_projection_episode(model, cfg, seed=seed)
        runs.append(run)
        if (i + 1) % 5 == 0:
            print(f"  {i+1}/{n_episodes} done")

    days = np.array(runs[0]["days"])

    panels = [
        ("cumulative_fees",    "Cumulative Fees Collected ($PAYTKN)",  "fees"),
        ("cumulative_rewards", "Cumulative Rewards Paid ($PAYTKN)",    "rewards"),
        ("net_treasury",       "Net Treasury Position (Fees − Rewards)", "net"),
        ("supply",             "Circulating Token Supply",             "supply"),
        ("price",              "Token Price (USD)",                    "price"),
        ("users",              "Active Users",                         "users"),
    ]

    fig = plt.figure(figsize=(16, 10), facecolor=BG)
    fig.suptitle(
        f"ChainEnv — Revenue & Token Projections  |  {n_episodes} Episodes  |  "
        f"Bands: P10 / P50 / P90",
        fontsize=13, fontweight="bold", y=0.98,
    )

    gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.3)
    axes = [fig.add_subplot(gs[r, c]) for r in range(3) for c in range(2)]

    for i, (key, title, ckey) in enumerate(panels):
        ax = axes[i]
        color = PALETTE[ckey]
        p10, p50, p90 = compute_bands(runs, key)

        ax.fill_between(days, p10, p90, alpha=0.2, color=color, label="P10–P90")
        ax.plot(days, p50, color=color, lw=2.0, label="Median")
        ax.plot(days, p10, color=color, lw=0.8, linestyle=":")
        ax.plot(days, p90, color=color, lw=0.8, linestyle=":")

        ax.set_title(title, fontsize=10, fontweight="bold")
        ax.set_xlabel("Day", fontsize=8)
        ax.set_facecolor(BG)
        ax.grid(True, alpha=0.3, linestyle=":")
        ax.tick_params(labelsize=7)
        ax.legend(fontsize=7, loc="upper left")

    # Print summary table
    print(f"\n{'='*65}")
    print(f"  Projection Summary (Day {days[-1]:.0f} — End of Episode)")
    print(f"{'='*65}")
    for key, title, _ in panels:
        p10, p50, p90 = compute_bands(runs, key)
        print(f"  {title[:40]:<40}  P50={p50[-1]:>12.2f}  [P10={p10[-1]:>12.2f}, P90={p90[-1]:>12.2f}]")

    # Save results
    os.makedirs("models", exist_ok=True)
    proj_data = {key: {
        "p10": compute_bands(runs, key)[0].tolist(),
        "p50": compute_bands(runs, key)[1].tolist(),
        "p90": compute_bands(runs, key)[2].tolist(),
        "days": days.tolist(),
    } for key, _, _ in panels}

    with open("models/projections.json", "w") as f:
        json.dump(proj_data, f, indent=2)
    print(f"\nProjection data saved → models/projections.json")

    if save:
        os.makedirs("plots", exist_ok=True)
        out = "plots/projections.png"
        fig.savefig(out, dpi=160, bbox_inches="tight", facecolor=BG)
        print(f"Plot saved → {out}")
    else:
        plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Revenue projections for ChainEnv")
    parser.add_argument("--model", type=str, default="models/best_model.zip")
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    plot_projections(args.model, n_episodes=args.episodes, save=args.save)
