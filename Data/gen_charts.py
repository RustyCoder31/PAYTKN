"""Generate stress-test charts from stress_results.json for FYDP_Report."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path

DATA_DIR = Path(r"C:\Users\Muhammad Essa\Desktop\FYP\Data")
OUT_DIR  = DATA_DIR / "charts"
OUT_DIR.mkdir(exist_ok=True)

with open(DATA_DIR / "stress_results.json") as f:
    raw = json.load(f)

# ── helpers ────────────────────────────────────────────────────
def avg_runs(runs, key):
    vals = [r[key] for r in runs if key in r]
    return sum(vals) / len(vals) if vals else 0.0

def scenario_means(data):
    rows = []
    for scenario, d in data.items():
        rl_r  = avg_runs(d["rl"],     "total_reward")
        st_r  = avg_runs(d["static"], "total_reward")
        rl_tr = avg_runs(d["rl"],     "final_treasury_stable") / 1e6
        st_tr = avg_runs(d["static"], "final_treasury_stable") / 1e6
        rl_u  = avg_runs(d["rl"],     "final_users")
        st_u  = avg_runs(d["static"], "final_users")
        rl_p  = avg_runs(d["rl"],     "final_price")
        st_p  = avg_runs(d["static"], "final_price")
        rl_lp = avg_runs(d["rl"],     "final_lp_depth") / 1e6
        st_lp = avg_runs(d["static"], "final_lp_depth") / 1e6
        rows.append({
            "scenario": scenario,
            "category": d["category"],
            "desc":     d["desc"],
            "rl_reward": rl_r,  "st_reward": st_r,
            "rl_treasury": rl_tr, "st_treasury": st_tr,
            "rl_users": rl_u,   "st_users": st_u,
            "rl_price": rl_p,   "st_price": st_p,
            "rl_lp_depth": rl_lp, "st_lp_depth": st_lp,
        })
    return rows

rows = scenario_means(raw)

# Category order for consistent colouring
CAT_COLORS = {
    "A. Sentiment":  "#4f46e5",
    "B. Treasury":   "#0891b2",
    "C. Population": "#16a34a",
    "D. Cycles":     "#d97706",
    "E. Combined":   "#dc2626",
}

NAVY  = "#1a236e"
BLUE  = "#4338ca"
GREY  = "#9ca3af"

# ── short labels ───────────────────────────────────────────────
LABEL_MAP = {
    "deep_bear":          "Deep Bear",
    "moderate_bear":      "Mod. Bear",
    "neutral_market":     "Neutral",
    "moderate_bull":      "Mod. Bull",
    "euphoria":           "Euphoria",
    "treasury_drain":     "Treas. Drain",
    "fee_drought":        "Fee Drought",
    "treasury_flush":     "Treas. Flush",
    "ghost_town":         "Ghost Town",
    "viral_growth":       "Viral Growth",
    "merchant_exodus":    "Merch. Exodus",
    "whale_entry":        "Whale Entry",
    "extended_bear":      "Ext. Bear",
    "bull_to_bear":       "Bull→Bear",
    "bear_to_bull":       "Bear→Bull",
    "late_adopter_crash": "Late Crash",
    "staking_war":        "Staking War",
    "liquidity_crunch":   "Liq. Crunch",
    "sentiment_shock":    "Sent. Shock",
    "full_stress":        "Full Stress",
}

labels   = [LABEL_MAP.get(r["scenario"], r["scenario"]) for r in rows]
cats     = [r["category"] for r in rows]
bar_cols = [CAT_COLORS[c] for c in cats]

x = np.arange(len(rows))
W = 0.38

# ════════════════════════════════════════════════════════════════
# Chart 1 — Total RL Reward across all 20 scenarios
# ════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(14, 5))
fig.patch.set_facecolor("#f8f9ff")
ax.set_facecolor("#f8f9ff")

b1 = ax.bar(x - W/2, [r["rl_reward"] for r in rows], W, label="RL Agent",
            color=[c for c in bar_cols], alpha=0.92, zorder=3)
b2 = ax.bar(x + W/2, [r["st_reward"] for r in rows], W, label="Static Baseline",
            color=bar_cols, alpha=0.40, hatch="//", edgecolor=[c for c in bar_cols], zorder=3)

ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8.5)
ax.set_ylabel("Cumulative Reward (365-day)", fontsize=10)
ax.set_title("RL Agent vs Static Baseline — Cumulative Reward (All 20 Stress Scenarios)",
             fontsize=12, fontweight="bold", color=NAVY, pad=12)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
ax.grid(axis="y", alpha=0.35, zorder=0)
ax.spines[["top","right"]].set_visible(False)

# category legend patches
patches = [mpatches.Patch(color=c, label=k) for k, c in CAT_COLORS.items()]
leg1 = ax.legend(handles=patches, loc="upper left", fontsize=8.5, title="Category",
                 framealpha=0.7, title_fontsize=8.5)
rl_patch  = mpatches.Patch(color="#444466", label="RL Agent (solid)")
st_patch  = mpatches.Patch(facecolor="#aaaaaa", hatch="//", edgecolor="#444466", label="Static (hatched)")
ax.legend(handles=[rl_patch, st_patch], loc="upper right", fontsize=9, framealpha=0.7)
ax.add_artist(leg1)

plt.tight_layout()
plt.savefig(OUT_DIR / "chart1_reward_comparison.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved chart1_reward_comparison.png")

# ════════════════════════════════════════════════════════════════
# Chart 2 — Treasury stable ($M) RL vs Static
# ════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(14, 5))
fig.patch.set_facecolor("#f8f9ff")
ax.set_facecolor("#f8f9ff")

ax.bar(x - W/2, [r["rl_treasury"] for r in rows], W, color=bar_cols, alpha=0.92, zorder=3)
ax.bar(x + W/2, [r["st_treasury"] for r in rows], W, color=bar_cols, alpha=0.40,
       hatch="//", edgecolor=bar_cols, zorder=3)

ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8.5)
ax.set_ylabel("Final Treasury Stable Reserve ($M)", fontsize=10)
ax.set_title("Treasury Stable Reserve — RL Agent vs Static Baseline",
             fontsize=12, fontweight="bold", color=NAVY, pad=12)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:.1f}M"))
ax.grid(axis="y", alpha=0.35, zorder=0)
ax.spines[["top","right"]].set_visible(False)

patches = [mpatches.Patch(color=c, label=k) for k, c in CAT_COLORS.items()]
ax.legend(handles=patches, loc="upper left", fontsize=8.5, title="Category",
          framealpha=0.7, title_fontsize=8.5)

plt.tight_layout()
plt.savefig(OUT_DIR / "chart2_treasury_comparison.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved chart2_treasury_comparison.png")

# ════════════════════════════════════════════════════════════════
# Chart 3 — Final active users RL vs Static
# ════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(14, 5))
fig.patch.set_facecolor("#f8f9ff")
ax.set_facecolor("#f8f9ff")

ax.bar(x - W/2, [r["rl_users"]/1000 for r in rows], W, color=bar_cols, alpha=0.92, zorder=3)
ax.bar(x + W/2, [r["st_users"]/1000 for r in rows], W, color=bar_cols, alpha=0.40,
       hatch="//", edgecolor=bar_cols, zorder=3)

ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8.5)
ax.set_ylabel("Final Active Users (thousands)", fontsize=10)
ax.set_title("User Retention — RL Agent vs Static Baseline",
             fontsize=12, fontweight="bold", color=NAVY, pad=12)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}k"))
ax.grid(axis="y", alpha=0.35, zorder=0)
ax.spines[["top","right"]].set_visible(False)

patches = [mpatches.Patch(color=c, label=k) for k, c in CAT_COLORS.items()]
ax.legend(handles=patches, loc="upper left", fontsize=8.5, title="Category",
          framealpha=0.7, title_fontsize=8.5)

plt.tight_layout()
plt.savefig(OUT_DIR / "chart3_users_comparison.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved chart3_users_comparison.png")

# ════════════════════════════════════════════════════════════════
# Chart 4 — Final token price RL vs Static
# ════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(14, 5))
fig.patch.set_facecolor("#f8f9ff")
ax.set_facecolor("#f8f9ff")

ax.bar(x - W/2, [r["rl_price"] for r in rows], W, color=bar_cols, alpha=0.92, zorder=3)
ax.bar(x + W/2, [r["st_price"] for r in rows], W, color=bar_cols, alpha=0.40,
       hatch="//", edgecolor=bar_cols, zorder=3)

ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8.5)
ax.set_ylabel("Final PAYTKN Price (USD)", fontsize=10)
ax.set_title("Token Price Stability — RL Agent vs Static Baseline",
             fontsize=12, fontweight="bold", color=NAVY, pad=12)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:.1f}"))
ax.grid(axis="y", alpha=0.35, zorder=0)
ax.spines[["top","right"]].set_visible(False)

patches = [mpatches.Patch(color=c, label=k) for k, c in CAT_COLORS.items()]
ax.legend(handles=patches, loc="upper left", fontsize=8.5, title="Category",
          framealpha=0.7, title_fontsize=8.5)

plt.tight_layout()
plt.savefig(OUT_DIR / "chart4_price_comparison.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved chart4_price_comparison.png")

# ════════════════════════════════════════════════════════════════
# Chart 5 — RL advantage heatmap (delta %)
# ════════════════════════════════════════════════════════════════
# Compute % delta for reward, treasury, users, price
metrics = ["Reward", "Treasury", "Users", "Price"]
deltas = []
for r in rows:
    def pct(rl, st): return (rl - st) / abs(st) * 100 if st != 0 else 0
    deltas.append([
        pct(r["rl_reward"],   r["st_reward"]),
        pct(r["rl_treasury"], r["st_treasury"]),
        pct(r["rl_users"],    r["st_users"]),
        pct(r["rl_price"],    r["st_price"]),
    ])

delta_arr = np.array(deltas).T   # shape (4, 20)

fig, ax = plt.subplots(figsize=(14, 4))
fig.patch.set_facecolor("#f8f9ff")

im = ax.imshow(delta_arr, cmap="RdYlGn", aspect="auto", vmin=-15, vmax=15)
ax.set_xticks(range(len(rows)))
ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8.5)
ax.set_yticks(range(len(metrics)))
ax.set_yticklabels(metrics, fontsize=10)
ax.set_title("RL Agent Advantage over Static Baseline (% delta per metric)",
             fontsize=12, fontweight="bold", color=NAVY, pad=10)

for i in range(len(metrics)):
    for j in range(len(rows)):
        val = delta_arr[i, j]
        ax.text(j, i, f"{val:+.1f}%", ha="center", va="center",
                fontsize=7, color="black" if abs(val) < 8 else "white")

plt.colorbar(im, ax=ax, fraction=0.02, pad=0.01, label="% advantage vs Static")
plt.tight_layout()
plt.savefig(OUT_DIR / "chart5_advantage_heatmap.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved chart5_advantage_heatmap.png")

# ════════════════════════════════════════════════════════════════
# Chart 6 — LP depth RL vs Static
# ════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(14, 5))
fig.patch.set_facecolor("#f8f9ff")
ax.set_facecolor("#f8f9ff")

ax.bar(x - W/2, [r["rl_lp_depth"] for r in rows], W, color=bar_cols, alpha=0.92, zorder=3)
ax.bar(x + W/2, [r["st_lp_depth"] for r in rows], W, color=bar_cols, alpha=0.40,
       hatch="//", edgecolor=bar_cols, zorder=3)

ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8.5)
ax.set_ylabel("Final LP Pool Depth ($M)", fontsize=10)
ax.set_title("AMM Liquidity Depth — RL Agent vs Static Baseline",
             fontsize=12, fontweight="bold", color=NAVY, pad=12)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:.0f}M"))
ax.grid(axis="y", alpha=0.35, zorder=0)
ax.spines[["top","right"]].set_visible(False)

patches = [mpatches.Patch(color=c, label=k) for k, c in CAT_COLORS.items()]
ax.legend(handles=patches, loc="upper left", fontsize=8.5, title="Category", framealpha=0.7)

plt.tight_layout()
plt.savefig(OUT_DIR / "chart6_lp_depth_comparison.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved chart6_lp_depth_comparison.png")

# ════════════════════════════════════════════════════════════════
# Print summary table data for Markdown
# ════════════════════════════════════════════════════════════════
print("\n=== MARKDOWN TABLE DATA ===")
print(f"{'Scenario':<20} {'Cat':<14} {'RL Reward':>10} {'ST Reward':>10} {'RL Treas':>9} {'ST Treas':>9} {'RL Users':>8} {'ST Users':>8} {'RL Price':>9} {'ST Price':>9}")
print("-"*110)
for r in rows:
    print(f"{r['scenario']:<20} {r['category']:<14} {r['rl_reward']:>10.1f} {r['st_reward']:>10.1f} "
          f"{r['rl_treasury']:>9.2f} {r['st_treasury']:>9.2f} "
          f"{r['rl_users']:>8,.0f} {r['st_users']:>8,.0f} "
          f"{r['rl_price']:>9.2f} {r['st_price']:>9.2f}")

print("\nDone.")
