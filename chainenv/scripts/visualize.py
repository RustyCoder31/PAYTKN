"""Visualisation script — ChainEnv v3.2 Ecosystem Dashboard.

Usage:
    cd chainenv
    python scripts/visualize.py [--model models/best_model.zip] [--save]

Produces a 4x3 grid showing all interconnected ecosystem metrics:
  Row 0: Token Price | Treasury Stable | Treasury PAYTKN
  Row 1: Staking APY | Active Users    | Daily TX Volume
  Row 2: Total Staked | Daily Mint     | Daily Burn
  Row 3: Cumulative TX Volume | Daily Cashback | Daily Fees Collected

All panels: RL agent (solid) vs Static baseline (dashed)
            across Bear / Neutral / Bull market scenarios.
"""

from __future__ import annotations
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
from stable_baselines3 import PPO

from chainenv.env import PaytknEnv
from chainenv.config import SimConfig
from scripts.evaluate import static_action


# ─────────────────────────────────────────────────────────────
# Scenario definitions
# ─────────────────────────────────────────────────────────────

SCENARIOS = {
    "Bear":    {"initial_sentiment": 0.25, "rng_seed": 10, "color": "#E74C3C"},
    "Neutral": {"initial_sentiment": 0.50, "rng_seed": 20, "color": "#2ECC71"},
    "Bull":    {"initial_sentiment": 0.75, "rng_seed": 30, "color": "#3498DB"},
}

BG         = "#F8F9FA"
GRID_COLOR = "#DEE2E6"

# ─────────────────────────────────────────────────────────────
# Panel definitions
# (data_key, title, y_label, format_hint)
# format_hint: "$" = dollar, "%" = percent, "" = raw / auto
# ─────────────────────────────────────────────────────────────

PANELS = [
    # Row 0 — Price & Treasury
    ("price",                   "Token Price",             "USD",    "$"),
    ("treasury_stable",         "Treasury Stable",         "USD",    "$"),
    ("treasury_paytkn",         "Treasury PAYTKN",         "tokens", ""),

    # Row 1 — Users & Volume
    ("actual_apy",              "User Staking APY",        "",       "%"),
    ("active_users",            "Active Users",            "count",  ""),
    ("tx_volume",               "Daily TX Volume",         "USD",    "$"),

    # Row 2 — Staking & Mint/Burn
    ("total_staked",            "Total Staked (PAYTKN)",   "tokens", ""),
    ("daily_mint",              "Daily Mint (PAYTKN)",     "tokens", ""),
    ("daily_burn",              "Daily Burn (PAYTKN)",     "tokens", ""),

    # Row 3 — Revenue
    ("cumulative_tx_volume",    "Cumul. TX Volume",        "USD",    "$"),
    ("daily_cashback_paid",     "Daily Cashback Paid",     "USD",    "$"),
    ("daily_fees_collected",    "Daily Fees Collected",    "USD",    "$"),
]

NROWS = 4
NCOLS = 3
assert len(PANELS) == NROWS * NCOLS


# ─────────────────────────────────────────────────────────────
# Reference lines shown on specific panels
# ─────────────────────────────────────────────────────────────

def _ref_lines(cfg: SimConfig) -> dict:
    return {
        "price":          (cfg.initial_price,             "#888888", "Launch $1.00"),
        "treasury_stable":(cfg.rules.treasury_stable_floor, "#F39C12", "Floor $500k"),
        "actual_apy":     (cfg.rules.min_staking_apy,    "#F39C12", "APY floor 3%"),
    }


# ─────────────────────────────────────────────────────────────
# Episode runner — collects day-by-day metrics
# ─────────────────────────────────────────────────────────────

def run_episode(env: PaytknEnv, policy, seed: int) -> list[dict]:
    obs, _ = env.reset(seed=seed)
    done = False
    while not done:
        if policy == "static":
            action = static_action(obs)
        else:
            action, _ = policy.predict(obs, deterministic=True)
        obs, _, terminated, truncated, _ = env.step(action)
        done = terminated or truncated
    return env._episode_metrics


# ─────────────────────────────────────────────────────────────
# Y-axis smart formatter
# ─────────────────────────────────────────────────────────────

def _fmt_yaxis(ax, hint: str, vals: list[float]) -> None:
    peak = max(abs(v) for v in vals) if vals else 1.0
    if hint == "$":
        if peak >= 1_000_000:
            ax.yaxis.set_major_formatter(
                matplotlib.ticker.FuncFormatter(lambda x, _: f"${x/1e6:.1f}M"))
        elif peak >= 1_000:
            ax.yaxis.set_major_formatter(
                matplotlib.ticker.FuncFormatter(lambda x, _: f"${x/1e3:.0f}k"))
        else:
            ax.yaxis.set_major_formatter(
                matplotlib.ticker.FuncFormatter(lambda x, _: f"${x:.2f}"))
    elif hint == "%":
        ax.yaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(lambda x, _: f"{x*100:.0f}%"))
    elif peak >= 1_000_000:
        ax.yaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(lambda x, _: f"{x/1e6:.1f}M"))
    elif peak >= 1_000:
        ax.yaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(lambda x, _: f"{x/1e3:.0f}k"))


# ─────────────────────────────────────────────────────────────
# Main dashboard
# ─────────────────────────────────────────────────────────────

def plot_dashboard(model_path: str, save: bool = False) -> None:
    print(f"\nLoading model: {model_path}")
    model = PPO.load(model_path)
    cfg_base = SimConfig()
    refs = _ref_lines(cfg_base)

    # ── Run all 6 episodes (3 scenarios × 2 agents) ──────────
    traces: dict[str, dict] = {}
    for name, scfg in SCENARIOS.items():
        cfg = SimConfig(
            initial_sentiment=scfg["initial_sentiment"],
            rng_seed=scfg["rng_seed"],
        )
        seed = scfg["rng_seed"]
        print(f"  Running {name} scenario...", end=" ", flush=True)
        traces[name] = {
            "rl":     run_episode(PaytknEnv(cfg), model,    seed),
            "static": run_episode(PaytknEnv(cfg), "static", seed),
        }
        # compute final rewards for title annotation
        rl_r  = sum(0 for _ in traces[name]["rl"])   # placeholder, reward not in metrics
        print("done")

    # ── Figure layout ─────────────────────────────────────────
    fig = plt.figure(figsize=(20, 22), facecolor=BG)
    fig.suptitle(
        "PAYTKN ChainEnv v3.2  —  Ecosystem Dashboard\n"
        "RL Agent (solid lines) vs Static Baseline (dashed)  |  Bear / Neutral / Bull",
        fontsize=14, fontweight="bold", y=0.998,
    )

    gs = gridspec.GridSpec(
        NROWS, NCOLS, figure=fig,
        hspace=0.60, wspace=0.35,
        top=0.965, bottom=0.07,
    )
    axes = [fig.add_subplot(gs[r, c]) for r in range(NROWS) for c in range(NCOLS)]

    # ── Draw each panel ───────────────────────────────────────
    for i, (key, title, ylabel, hint) in enumerate(PANELS):
        ax = axes[i]
        ax.set_facecolor(BG)
        ax.set_title(title, fontsize=9, fontweight="bold", pad=5)
        ax.set_xlabel("Day", fontsize=7)
        ax.set_ylabel(ylabel, fontsize=7)
        ax.grid(True, alpha=0.4, linestyle=":", color=GRID_COLOR)
        ax.tick_params(labelsize=7)

        all_vals: list[float] = []

        for sname, scfg in SCENARIOS.items():
            color = scfg["color"]
            rl_data = traces[sname]["rl"]
            st_data = traces[sname]["static"]

            days    = [d["day"] for d in rl_data]
            rl_vals = [d.get(key, 0.0) for d in rl_data]
            st_vals = [d.get(key, 0.0) for d in st_data]
            all_vals.extend(rl_vals + st_vals)

            ax.plot(days, rl_vals, color=color, lw=2.0, alpha=0.95)
            ax.plot(days, st_vals, color=color, lw=1.1, linestyle="--", alpha=0.50)

        # Reference lines
        if key in refs:
            ref_val, ref_color, ref_label = refs[key]
            ax.axhline(ref_val, color=ref_color, lw=1.2, linestyle=":",
                       alpha=0.85, zorder=0)

        _fmt_yaxis(ax, hint, all_vals)

    # ── Shared legend ─────────────────────────────────────────
    legend_elems = []
    for sname, scfg in SCENARIOS.items():
        c = scfg["color"]
        legend_elems.append(Line2D([0],[0], color=c, lw=2.0,        label=f"RL — {sname}"))
        legend_elems.append(Line2D([0],[0], color=c, lw=1.1, linestyle="--", alpha=0.6,
                                   label=f"Static — {sname}"))
    legend_elems.append(Line2D([0],[0], color="#888", lw=1.2, linestyle=":",
                               label="Reference floor / launch price"))

    fig.legend(
        handles=legend_elems,
        loc="lower center",
        ncol=4,
        fontsize=8.5,
        bbox_to_anchor=(0.5, 0.005),
        framealpha=0.92,
        edgecolor="#CCC",
    )

    # ── Save or show ──────────────────────────────────────────
    if save:
        os.makedirs("plots", exist_ok=True)
        out = "plots/ecosystem_dashboard.png"
        fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
        print(f"\nSaved -> {out}")
    else:
        plt.show()
        print("\nDashboard displayed.")


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChainEnv v3.2 ecosystem dashboard")
    parser.add_argument("--model", type=str, default="models/best_model.zip")
    parser.add_argument("--save",  action="store_true",
                        help="Save PNG to plots/ecosystem_dashboard.png")
    args = parser.parse_args()

    plot_dashboard(args.model, save=args.save)
