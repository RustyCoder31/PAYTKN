"""Visualisation script — episode traces and training summary.

Usage:
    cd chainenv
    python scripts/visualize.py --model models/paytkn_ppo_final.zip [--save]

Produces a 3x2 grid:
    [Price]        [Sentiment]
    [Treasury]     [Token Supply]
    [TX Volume]    [Staking Ratio]
"""

import argparse
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

SCENARIOS = {
    "bear":    {"initial_sentiment": 0.25, "rng_seed": 10, "color": "#E74C3C"},
    "neutral": {"initial_sentiment": 0.50, "rng_seed": 20, "color": "#2ECC71"},
    "bull":    {"initial_sentiment": 0.75, "rng_seed": 30, "color": "#3498DB"},
}

STATIC_COLOR = "#95A5A6"
BG = "#F8F9FA"


def run_episode_trace(env: PaytknEnv, policy, seed: int) -> list[dict]:
    obs, _ = env.reset(seed=seed)
    done = False
    while not done:
        if policy == "static":
            action = np.zeros(5, dtype=np.float32)
        else:
            action, _ = policy.predict(obs, deterministic=True)
        obs, _, terminated, truncated, _ = env.step(action)
        done = terminated or truncated
    return env._episode_metrics


def plot_traces(model_path: str, save: bool = False) -> None:
    model = PPO.load(model_path)

    fig = plt.figure(figsize=(16, 10), facecolor=BG)
    fig.suptitle("ChainEnv — RL Agent vs Static Baseline\nEpisode Traces by Market Scenario",
                 fontsize=14, fontweight="bold", y=0.98)

    gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.3)
    axes = [fig.add_subplot(gs[r, c]) for r in range(3) for c in range(2)]

    panels = [
        ("price",            "Token Price (USD)", "$"),
        ("sentiment",        "Market Sentiment",  ""),
        ("treasury_stable",  "Treasury Stable ($)", "$"),
        ("total_supply",     "Circulating Supply", ""),
        ("tx_volume",        "Daily TX Volume",    "$"),
        ("staked",           "Total Staked",       ""),
    ]

    for scenario_name, scenario_cfg in SCENARIOS.items():
        cfg = SimConfig()
        cfg.initial_sentiment = scenario_cfg["initial_sentiment"]
        cfg.rng_seed = scenario_cfg["rng_seed"]
        color = scenario_cfg["color"]

        rl_trace = run_episode_trace(PaytknEnv(cfg), model, seed=scenario_cfg["rng_seed"])
        st_trace = run_episode_trace(PaytknEnv(cfg), "static", seed=scenario_cfg["rng_seed"])

        days = [d["day"] for d in rl_trace]

        for i, (key, title, prefix) in enumerate(panels):
            ax = axes[i]
            rl_vals = [d.get(key, 0.0) for d in rl_trace]
            st_vals = [d.get(key, 0.0) for d in st_trace]

            ax.plot(days, rl_vals, color=color, lw=1.8,
                    label=f"RL {scenario_name}")
            ax.plot(days, st_vals, color=color, lw=1.0, linestyle="--",
                    alpha=0.5, label=f"Static {scenario_name}")

            ax.set_title(title, fontsize=10, fontweight="bold")
            ax.set_xlabel("Day", fontsize=8)
            ax.set_facecolor(BG)
            ax.grid(True, alpha=0.3, linestyle=":")
            ax.tick_params(labelsize=7)

    # Legend (shared)
    from matplotlib.lines import Line2D
    legend_elements = []
    for sname, scfg in SCENARIOS.items():
        legend_elements.append(
            Line2D([0], [0], color=scfg["color"], lw=2, label=f"RL — {sname}")
        )
        legend_elements.append(
            Line2D([0], [0], color=scfg["color"], lw=1, linestyle="--",
                   alpha=0.6, label=f"Static — {sname}")
        )
    fig.legend(handles=legend_elements, loc="lower center",
               ncol=3, fontsize=8, bbox_to_anchor=(0.5, 0.01))

    plt.subplots_adjust(bottom=0.12)

    if save:
        os.makedirs("plots", exist_ok=True)
        out = "plots/episode_traces.png"
        fig.savefig(out, dpi=160, bbox_inches="tight", facecolor=BG)
        print(f"Saved → {out}")
    else:
        plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visualise ChainEnv episode traces")
    parser.add_argument("--model", type=str, default="models/best_model.zip")
    parser.add_argument("--save", action="store_true", help="Save PNG instead of showing")
    args = parser.parse_args()
    plot_traces(args.model, save=args.save)
