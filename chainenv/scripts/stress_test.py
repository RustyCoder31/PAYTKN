"""Stress test — 20 unique environments for RL vs Static evaluation.

Usage:
    cd chainenv
    python scripts/stress_test.py --model models/best_model.zip

Categories (4 scenarios each, except cycles=5 and combined=3):
  A. Market Sentiment Extremes  (4) — deep_bear, mild_bear, mild_bull, euphoria
  B. Treasury Stress            (4) — crisis, depleted, flush, underfunded_launch
  C. Population Dynamics        (4) — viral_growth, ghost_town, high_churn, merchant_desert
  D. Market Cycles              (5) — realistic, early_crash, extended_bear, v_recovery, double_bull
  E. Combined Stress            (3) — perfect_storm, bootstrapped, late_adopter_crash

Outputs:
    models/stress_results.json
    plots/stress_01_heatmap.png
    plots/stress_02_ranking.png
    plots/stress_03_categories.png
"""

from __future__ import annotations
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
from stable_baselines3 import PPO

from chainenv.env import PaytknEnv
from chainenv.config import SimConfig
from scripts.evaluate import static_action, run_episode


# ─────────────────────────────────────────────────────────────
# Phase schedule helpers
# ─────────────────────────────────────────────────────────────

def _ph(*phases):
    """Shorthand: list of (start, end, target_sentiment, drift) tuples."""
    return list(phases)


REALISTIC    = _ph(
    (0,    180,  0.50, 0.03),
    (181,  545,  0.75, 0.04),
    (546,  910,  0.20, 0.05),
    (911,  1275, 0.45, 0.03),
    (1276, 1825, 0.65, 0.03),
)

EARLY_CRASH  = _ph(
    (0,    90,   0.65, 0.04),   # brief honeymoon bull
    (91,   365,  0.15, 0.06),   # hard crash year 1
    (366,  730,  0.35, 0.03),   # slow recovery year 2
    (731,  1095, 0.50, 0.03),   # stabilisation year 3
    (1096, 1825, 0.62, 0.03),   # mature growth years 4-5
)

EXTENDED_BEAR = _ph(
    (0,    180,  0.50, 0.03),   # neutral launch
    (181,  1095, 0.20, 0.04),   # 3-year crypto winter
    (1096, 1460, 0.45, 0.03),   # recovery year 4
    (1461, 1825, 0.63, 0.03),   # late bull year 5
)

V_RECOVERY   = _ph(
    (0,    180,  0.65, 0.04),   # bull start
    (181,  365,  0.10, 0.08),   # violent crash (6 months)
    (366,  545,  0.72, 0.06),   # sharp V recovery
    (546,  1825, 0.60, 0.03),   # sustained bull
)

DOUBLE_BULL  = _ph(
    (0,    180,  0.50, 0.03),   # neutral launch
    (181,  450,  0.75, 0.04),   # first bull
    (451,  630,  0.30, 0.05),   # correction/bear
    (631,  1000, 0.72, 0.04),   # second bull
    (1001, 1275, 0.28, 0.04),   # second bear
    (1276, 1825, 0.55, 0.03),   # stabilisation
)


# ─────────────────────────────────────────────────────────────
# 20 Stress Scenarios
# ─────────────────────────────────────────────────────────────

STRESS_SCENARIOS = {

    # ── A. Market Sentiment Extremes ─────────────────────────
    "deep_bear": {
        "category": "A. Sentiment",
        "desc": "Extreme fear — sentiment 0.10",
        "cfg": dict(initial_sentiment=0.10, rng_seed=101),
    },
    "mild_bear": {
        "category": "A. Sentiment",
        "desc": "Mild pessimism — sentiment 0.30",
        "cfg": dict(initial_sentiment=0.30, rng_seed=102),
    },
    "mild_bull": {
        "category": "A. Sentiment",
        "desc": "Optimism — sentiment 0.65",
        "cfg": dict(initial_sentiment=0.65, rng_seed=103),
    },
    "euphoria": {
        "category": "A. Sentiment",
        "desc": "Extreme greed — sentiment 0.90",
        "cfg": dict(initial_sentiment=0.90, rng_seed=104),
    },

    # ── B. Treasury Stress ────────────────────────────────────
    "treasury_crisis": {
        "category": "B. Treasury",
        "desc": "Near-empty treasury ($300k — 15% of normal)",
        "cfg": dict(initial_sentiment=0.50, rng_seed=201,
                    initial_treasury_stable=300_000),
    },
    "treasury_depleted": {
        "category": "B. Treasury",
        "desc": "Half treasury ($1M)",
        "cfg": dict(initial_sentiment=0.50, rng_seed=202,
                    initial_treasury_stable=1_000_000),
    },
    "treasury_flush": {
        "category": "B. Treasury",
        "desc": "4× treasury ($8M) — test overspending guard",
        "cfg": dict(initial_sentiment=0.55, rng_seed=203,
                    initial_treasury_stable=8_000_000),
    },
    "underfunded_launch": {
        "category": "B. Treasury",
        "desc": "Tiny treasury ($500k) + only 200 users",
        "cfg": dict(initial_sentiment=0.40, rng_seed=204,
                    initial_treasury_stable=500_000,
                    initial_users=200, initial_merchants=20),
    },

    # ── C. Population Dynamics ────────────────────────────────
    "viral_growth": {
        "category": "C. Population",
        "desc": "500 signups/day — viral payment app explosion",
        "cfg": dict(initial_sentiment=0.60, rng_seed=301,
                    max_daily_signups=500),
    },
    "ghost_town": {
        "category": "C. Population",
        "desc": "5 signups/day — struggling adoption",
        "cfg": dict(initial_sentiment=0.45, rng_seed=302,
                    max_daily_signups=5),
    },
    "high_churn": {
        "category": "C. Population",
        "desc": "8× normal churn — retention crisis",
        "cfg": dict(initial_sentiment=0.50, rng_seed=303,
                    base_churn_rate=0.008),
    },
    "merchant_desert": {
        "category": "C. Population",
        "desc": "Only 5 merchants — near-zero payment utility",
        "cfg": dict(initial_sentiment=0.50, rng_seed=304,
                    initial_merchants=5),
    },

    # ── D. Market Cycles ──────────────────────────────────────
    "realistic": {
        "category": "D. Cycles",
        "desc": "Launch → Bull → Crash → Recovery → Mature bull",
        "cfg": dict(initial_sentiment=0.50, rng_seed=401,
                    market_phase_schedule=REALISTIC),
    },
    "early_crash": {
        "category": "D. Cycles",
        "desc": "Honeymoon → Hard crash year 1 → Long recovery",
        "cfg": dict(initial_sentiment=0.60, rng_seed=402,
                    market_phase_schedule=EARLY_CRASH),
    },
    "extended_bear": {
        "category": "D. Cycles",
        "desc": "3-year crypto winter then late recovery",
        "cfg": dict(initial_sentiment=0.50, rng_seed=403,
                    market_phase_schedule=EXTENDED_BEAR),
    },
    "v_recovery": {
        "category": "D. Cycles",
        "desc": "Bull → violent crash → sharp V recovery → sustained bull",
        "cfg": dict(initial_sentiment=0.65, rng_seed=404,
                    market_phase_schedule=V_RECOVERY),
    },
    "double_bull": {
        "category": "D. Cycles",
        "desc": "Two separate bull runs with a bear in between",
        "cfg": dict(initial_sentiment=0.50, rng_seed=405,
                    market_phase_schedule=DOUBLE_BULL),
    },

    # ── E. Combined Stress ────────────────────────────────────
    "perfect_storm": {
        "category": "E. Combined",
        "desc": "Bear + high churn + depleted treasury",
        "cfg": dict(initial_sentiment=0.20, rng_seed=501,
                    base_churn_rate=0.005,
                    initial_treasury_stable=600_000),
    },
    "bootstrapped": {
        "category": "E. Combined",
        "desc": "Tiny start (100 users) + viral growth mid-way",
        "cfg": dict(initial_sentiment=0.45, rng_seed=502,
                    initial_users=100, initial_merchants=10,
                    max_daily_signups=300,
                    market_phase_schedule=_ph(
                        (0,    365,  0.40, 0.03),   # quiet bootstrap period
                        (366,  730,  0.75, 0.05),   # viral breakout
                        (731,  1825, 0.58, 0.03),   # steady mature growth
                    )),
    },
    "late_adopter_crash": {
        "category": "E. Combined",
        "desc": "Large ecosystem (5k users) hit by sudden extended bear",
        "cfg": dict(initial_sentiment=0.55, rng_seed=503,
                    initial_users=5_000, initial_merchants=500,
                    market_phase_schedule=_ph(
                        (0,    180,  0.60, 0.03),   # stable mature start
                        (181,  1095, 0.18, 0.05),   # sudden 3-year bear
                        (1096, 1825, 0.50, 0.03),   # recovery
                    )),
    },
}


# ─────────────────────────────────────────────────────────────
# Config builder
# ─────────────────────────────────────────────────────────────

def make_stress_cfg(scenario_cfg: dict, episode_days: int = 1825) -> SimConfig:
    return SimConfig(
        episode_days=episode_days,
        max_daily_signups=scenario_cfg.get("max_daily_signups", 100),
        **{k: v for k, v in scenario_cfg.items()
           if k not in ("max_daily_signups",)
           and k in SimConfig.__dataclass_fields__},
    )


# ─────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────

def run_stress(model_path: str, n_episodes: int = 2, episode_days: int = 1825) -> dict:
    print(f"\n{'='*80}")
    print(f"  PAYTKN Stress Test — 20 Environments")
    print(f"  Model: {model_path}")
    print(f"  Episodes per scenario: {n_episodes}  |  Days: {episode_days}")
    print(f"{'='*80}\n")

    model = None
    if model_path and os.path.exists(model_path):
        model = PPO.load(model_path, device="cpu")
        print(f"  Loaded RL model: {model_path}\n")
    else:
        print(f"  [!] Model not found — static baseline only\n")

    header = (
        f"{'#':<3} {'Scenario':<22} {'Category':<14} "
        f"{'RL Rew':>8} {'ST Rew':>8} "
        f"{'Price+%':>8} {'Users+%':>8} {'Tsy+%':>8}  Description"
    )
    print(header)
    print("─" * len(header))

    all_results = {}
    idx = 1

    for name, meta in STRESS_SCENARIOS.items():
        cfg = make_stress_cfg(meta["cfg"], episode_days=episode_days)
        rl_eps, st_eps = [], []

        for ep in range(n_episodes):
            seed = meta["cfg"].get("rng_seed", 42) + ep * 100

            if model is not None:
                env_rl = PaytknEnv(cfg)
                rl_eps.append(run_episode(env_rl, model, seed=seed))

            env_st = PaytknEnv(cfg)
            st_eps.append(run_episode(env_st, "static", seed=seed))

        def avg(eps, key):
            return float(np.mean([e[key] for e in eps])) if eps else 0.0

        def edge(key):
            rl_v = avg(rl_eps, key)
            st_v = avg(st_eps, key)
            return (rl_v - st_v) / max(abs(st_v), 1e-8) * 100

        rl_rew = avg(rl_eps, "total_reward")
        st_rew = avg(st_eps, "total_reward")

        print(
            f"{idx:<3} {name:<22} {meta['category']:<14} "
            f"{rl_rew:>8.1f} {st_rew:>8.1f} "
            f"{edge('final_price'):>+7.1f}% "
            f"{edge('final_users'):>+7.1f}% "
            f"{edge('final_treasury_stable'):>+7.1f}%  "
            f"{meta['desc']}"
        )

        all_results[name] = {
            "category": meta["category"],
            "desc": meta["desc"],
            "rl":     rl_eps,
            "static": st_eps,
        }
        idx += 1

    print(f"\n{'='*80}")
    # Save
    os.makedirs("models", exist_ok=True)
    out = "models/stress_results.json"
    with open(out, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"Results saved -> {out}")

    return all_results


# ─────────────────────────────────────────────────────────────
# Visualisations
# ─────────────────────────────────────────────────────────────

CATEGORY_COLORS = {
    "A. Sentiment": "#42A5F5",
    "B. Treasury":  "#EF5350",
    "C. Population":"#66BB6A",
    "D. Cycles":    "#FFA726",
    "E. Combined":  "#AB47BC",
}

METRIC_KEYS = [
    ("total_reward",          "Reward"),
    ("final_price",           "Price"),
    ("final_users",           "Users"),
    ("final_treasury_stable", "Treasury"),
    ("cumulative_tx_volume",  "TX Volume"),
    ("avg_daily_fees",        "Daily Fees"),
]


def plot_heatmap(results: dict):
    """Heatmap: scenarios × metrics, colour = RL % advantage over static."""
    names    = list(results.keys())
    met_keys = [m[0] for m in METRIC_KEYS]
    met_lbls = [m[1] for m in METRIC_KEYS]

    data = np.zeros((len(names), len(met_keys)))
    for i, name in enumerate(names):
        rl_eps = results[name]["rl"]
        st_eps = results[name]["static"]
        for j, mk in enumerate(met_keys):
            def avg(eps):
                return float(np.mean([e[mk] for e in eps])) if eps else 0.0
            rl_v, st_v = avg(rl_eps), avg(st_eps)
            data[i, j] = (rl_v - st_v) / max(abs(st_v), 1e-8) * 100

    fig, ax = plt.subplots(figsize=(13, 11))
    fig.patch.set_facecolor("#0D1117")
    ax.set_facecolor("#0D1117")

    cmap = mcolors.LinearSegmentedColormap.from_list(
        "rg", ["#EF5350", "#FFFFFF", "#4CAF50"])
    vmax = max(abs(data.max()), abs(data.min()), 5)
    im   = ax.imshow(data, cmap=cmap, aspect="auto",
                     vmin=-vmax, vmax=vmax)

    ax.set_xticks(range(len(met_lbls)))
    ax.set_xticklabels(met_lbls, fontsize=11, color="white", fontweight="bold")
    ax.set_yticks(range(len(names)))

    # Y-axis labels coloured by category
    ylabels = []
    for name in names:
        cat   = results[name]["category"]
        color = CATEGORY_COLORS.get(cat, "white")
        ylabels.append(name)
    ax.set_yticklabels(ylabels, fontsize=9)
    for tick, name in zip(ax.get_yticklabels(), names):
        cat = results[name]["category"]
        tick.set_color(CATEGORY_COLORS.get(cat, "white"))

    # Cell annotations
    for i in range(len(names)):
        for j in range(len(met_keys)):
            val   = data[i, j]
            color = "black" if abs(val) < vmax * 0.4 else "white"
            ax.text(j, i, f"{val:+.1f}%", ha="center", va="center",
                    fontsize=8, color=color, fontweight="bold")

    cb = plt.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.set_label("RL % advantage over Static", color="white", fontsize=10)
    cb.ax.yaxis.set_tick_params(color="white")
    plt.setp(cb.ax.yaxis.get_ticklabels(), color="white")

    ax.set_title("Stress Test Heatmap — RL Agent % Advantage Across 20 Environments",
                 color="white", fontsize=13, fontweight="bold", pad=15)

    # Category legend
    patches = [mpatches.Patch(color=c, label=k)
               for k, c in CATEGORY_COLORS.items()]
    ax.legend(handles=patches, loc="upper right",
              bbox_to_anchor=(1.28, 1), fontsize=9,
              facecolor="#1C2128", edgecolor="gray",
              labelcolor="white")

    plt.tight_layout()
    os.makedirs("plots", exist_ok=True)
    plt.savefig("plots/stress_01_heatmap.png", dpi=150,
                bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.show()
    print("Saved: plots/stress_01_heatmap.png")


def plot_ranking(results: dict):
    """Horizontal bar chart: scenarios ranked by overall RL advantage."""
    names, edges, cats = [], [], []
    for name, meta in results.items():
        rl_eps = meta["rl"]
        st_eps = meta["static"]
        if not rl_eps:
            continue
        vals = []
        for mk, _ in METRIC_KEYS:
            rl_v = float(np.mean([e[mk] for e in rl_eps]))
            st_v = float(np.mean([e[mk] for e in st_eps]))
            vals.append((rl_v - st_v) / max(abs(st_v), 1e-8) * 100)
        names.append(name)
        edges.append(float(np.mean(vals)))
        cats.append(meta["category"])

    # Sort by edge descending
    order  = np.argsort(edges)[::-1]
    names  = [names[i]  for i in order]
    edges  = [edges[i]  for i in order]
    cats   = [cats[i]   for i in order]
    colors = [CATEGORY_COLORS.get(c, "#90CAF9") for c in cats]

    fig, ax = plt.subplots(figsize=(13, 9))
    fig.patch.set_facecolor("#0D1117")
    ax.set_facecolor("#0D1117")

    bars = ax.barh(range(len(names)), edges, color=colors, alpha=0.85,
                   edgecolor="white", linewidth=0.5)

    for bar, val in zip(bars, edges):
        x = bar.get_width()
        ax.text(x + 0.1 if x >= 0 else x - 0.1,
                bar.get_y() + bar.get_height() / 2,
                f"{val:+.1f}%", va="center",
                fontsize=9, color="white", fontweight="bold",
                ha="left" if x >= 0 else "right")

    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=10, color="white")
    ax.axvline(0, color="white", linewidth=1)
    ax.set_xlabel("Average RL % advantage over Static (across all metrics)",
                  color="white", fontsize=11)
    ax.set_title("Stress Test Ranking — RL vs Static Across 20 Environments",
                 color="white", fontsize=13, fontweight="bold")
    ax.tick_params(colors="white")
    ax.spines["bottom"].set_color("gray")
    ax.spines["left"].set_color("gray")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", alpha=0.2, color="white")

    patches = [mpatches.Patch(color=c, label=k)
               for k, c in CATEGORY_COLORS.items()]
    ax.legend(handles=patches, loc="lower right",
              facecolor="#1C2128", edgecolor="gray",
              labelcolor="white", fontsize=9)

    plt.tight_layout()
    plt.savefig("plots/stress_02_ranking.png", dpi=150,
                bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.show()
    print("Saved: plots/stress_02_ranking.png")


def plot_categories(results: dict):
    """Box plot showing RL advantage distribution per category."""
    cat_edges = {c: [] for c in CATEGORY_COLORS}

    for name, meta in results.items():
        rl_eps = meta["rl"]
        st_eps = meta["static"]
        if not rl_eps:
            continue
        cat = meta["category"]
        for mk, _ in METRIC_KEYS:
            rl_v = float(np.mean([e[mk] for e in rl_eps]))
            st_v = float(np.mean([e[mk] for e in st_eps]))
            cat_edges[cat].append((rl_v - st_v) / max(abs(st_v), 1e-8) * 100)

    cats  = [c for c in CATEGORY_COLORS if cat_edges[c]]
    data  = [cat_edges[c] for c in cats]
    clrs  = [CATEGORY_COLORS[c] for c in cats]

    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor("#0D1117")
    ax.set_facecolor("#0D1117")

    bps = ax.boxplot(data, patch_artist=True, notch=False,
                     medianprops=dict(color="white", linewidth=2))
    for patch, clr in zip(bps["boxes"], clrs):
        patch.set_facecolor(clr)
        patch.set_alpha(0.75)
    for element in ["whiskers", "caps", "fliers"]:
        for item in bps[element]:
            item.set_color("gray")

    # Overlay individual points
    for i, (d, clr) in enumerate(zip(data, clrs), 1):
        jitter = np.random.default_rng(i).uniform(-0.15, 0.15, len(d))
        ax.scatter([i + j for j in jitter], d, color=clr,
                   edgecolors="white", linewidths=0.5, s=40, zorder=5)

    ax.set_xticks(range(1, len(cats)+1))
    ax.set_xticklabels([c.split(". ")[1] for c in cats],
                       fontsize=11, color="white")
    ax.axhline(0, color="white", linewidth=1, linestyle="--", alpha=0.5)
    ax.set_ylabel("RL % advantage over Static", color="white", fontsize=11)
    ax.set_title("RL Advantage Distribution by Stress Category",
                 color="white", fontsize=13, fontweight="bold")
    ax.tick_params(colors="white")
    for sp in ax.spines.values():
        sp.set_color("gray")
    ax.grid(axis="y", alpha=0.2, color="white")

    plt.tight_layout()
    plt.savefig("plots/stress_03_categories.png", dpi=150,
                bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.show()
    print("Saved: plots/stress_03_categories.png")


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PAYTKN 20-environment stress test")
    parser.add_argument("--model",    type=str, default="models/best_model.zip")
    parser.add_argument("--episodes", type=int, default=2,
                        help="Episodes per scenario (default 2, use 1 for speed)")
    parser.add_argument("--days",     type=int, default=1825,
                        help="Episode length in days (default 1825 = 5yr)")
    args = parser.parse_args()

    results = run_stress(
        model_path=args.model,
        n_episodes=args.episodes,
        episode_days=args.days,
    )

    print("\nGenerating visualisations...")
    plot_heatmap(results)
    plot_ranking(results)
    plot_categories(results)
    print("\nAll done! Check plots/stress_*.png")
