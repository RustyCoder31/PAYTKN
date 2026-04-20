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
    """Rule-based static policy — grounded entirely in the PAYTKN tokenomics design (Excel).

    Rules derived from:
      - Lifecycle sheet: mint tied to TX activity, price, inflation, treasury health
      - Incentive Mechanisms: burn % offsets minting; emergency burns during inflation
      - Treasury sheet: auto-balance PAYTKN:Stable ratio; scale rewards with treasury health
      - Modeling sheet: reward pool per epoch, max reward % of TX fees
      - Thresholds sheet: loyalty decay, APY targets, cancellation thresholds

    Key design principles from Excel:
      1. Mint rate DECREASES as system matures (day_norm proxy)
      2. Burns offset minting — burn more when inflation risk is high
      3. Rewards SCALE with treasury health (not fixed)
      4. Cashback scales with loyalty tier behavior
      5. Merchant pool scales with real TX volume
      6. Treasury maintains PAYTKN:Stable ratio bands (60:40 → 40:60)

    Observation space (indices used):
      0  price_ratio           current_price / $1.00
      1  volatility_norm       7-day price std dev / $1.00
      2  tx_volume_norm        daily USD volume / 500,000
      4  sentiment             market sentiment [0, 1]
      5  treasury_stable_norm  treasury_stable / $2M initial
      6  treasury_paytkn_norm  treasury_paytkn * price / $2M initial
      7  staking_ratio         total_staked_USD / total_supply_USD
      8  supply_inflation      (total_supply / initial_supply) - 1
      9  reward_pool_norm      reward_pool * price / $2M initial
      10 day_norm              day / episode_days  (maturity proxy)
      11 user_growth_rate      (users_today - users_yesterday) / users_yesterday
      13 loyalty_avg           mean user loyalty score [0, 1]
      17 actual_apy_norm       actual_apy / 0.30  (1.0 = 30% APY)

    Action space ([-1, 1] maps to actual range):
      0  mint_factor        → [0.0,  2.0]    midpoint 1.0×
      1  burn_rate          → [0.0,  0.0005] midpoint 0.00025/day
      2  reward_alloc       → [0.20, 0.60]   midpoint 40% of fees
      3  cashback_base_rate → [0.001,0.010]  midpoint 0.55%
      4  merchant_pool_alloc→ [0.05, 0.25]   midpoint 15% of fees
      5  treasury_ratio     → [0.30, 0.90]   action=0.0 → 0.60 (fixed 60/40 split for static)
    """
    # ── Unpack observations ───────────────────────────────────
    price_ratio      = float(obs[0])   # 1.0 = at target $1.00
    volatility       = float(obs[1])   # normalised 7-day std dev
    tx_volume_norm   = float(obs[2])   # 1.0 = $500k/day
    sentiment        = float(obs[4])   # 0=bear, 1=bull
    tsy_stable_norm  = float(obs[5])   # 1.0 = $2M stable (healthy)
    tsy_paytkn_norm  = float(obs[6])   # 1.0 = initial treasury PAYTKN at current price
    staking_ratio    = float(obs[7])   # % of supply staked
    inflation        = float(obs[8])   # supply growth above initial
    reward_pool_norm = float(obs[9])   # reward pool size normalised
    day_norm         = float(obs[10])  # 0=day1, 1=last day (maturity proxy)
    user_growth      = float(obs[11])  # daily user growth rate
    loyalty          = float(obs[13])  # mean loyalty [0,1]; Excel: decay -10%/cancel
    # obs[17] = actual_apy / 0.30, clipped [0,1].  At 1.0 it is SATURATED — actual APY ≥ 30%.
    # Do NOT reconvert with ×0.30 because any APY above 30% looks identical to 30%.
    # Instead threshold directly on the normalised value so saturation (1.0) triggers max cut.
    apy_norm    = float(obs[17])          # 0=0% APY, 1.0=≥30% APY
    actual_apy  = apy_norm * 0.30        # best-estimate (lower-bound when saturated)

    # ── Treasury health composite (drives reward scaling per Excel) ──
    # Excel: "Build rules that scale rewards with treasury health (dynamic APY)"
    # Excel: "Safe PAYTKN:Stable ratio bands (60:40 → 40:60)"
    tsy_healthy      = tsy_stable_norm >= 1.0 and tsy_paytkn_norm >= 0.50
    tsy_stressed     = tsy_stable_norm < 0.50 or tsy_paytkn_norm < 0.20
    tsy_paytkn_low   = tsy_paytkn_norm < 0.50   # below half of initial

    # ── AdjustFactor (Excel user formula: Sheet static simulations) ───
    # TreasuryHealth = min(max(treasury_stable / (DailyRewardCost × 100), 0), 1)
    # Approximated with tsy_stable_norm (already normalised 0–1 against $2M initial)
    # Sentiment (Excel tanh variant) ≈ tanh(price_ratio - 1 + tx_volume_norm - 0.5)
    #                                  / (volatility + 0.5)
    # AdjustFactor = min(1, TreasuryHealth + Sentiment)
    # Controls how generously we can afford to distribute staking rewards.
    _sentiment_signal = float(np.tanh((price_ratio - 1.0) + (tx_volume_norm - 0.5)))
    _adjust_sentiment  = _sentiment_signal / max(0.5, volatility + 0.5)
    _adjust_sentiment  = float(np.clip(_adjust_sentiment, 0.0, 1.0))
    _treasury_health   = float(np.clip(tsy_stable_norm, 0.0, 1.0))
    adjust_factor      = float(np.clip(_treasury_health + _adjust_sentiment, 0.0, 1.0))
    # Excel: "DailyRewards ≤ Treasury / RunwayDays"
    # Translated to reward lever: reward_alloc_cap scales with treasury runway.
    # If tsy_stable_norm < 0.25 → treasury has < 6-month runway → cut reward leverage.
    # reward_alloc maps [-1, 1] → [0.20, 0.60]; capping in that space:
    # safe_reward_cap = adjust_factor * 0.8 - 0.5 → biases alloc fraction downward
    # when treasury/runway is tight (adjust_factor < 0.6).
    _reward_cap_action = float(np.clip(adjust_factor * 1.6 - 0.5, -1.0, 1.0))

    # ── Defaults (midpoints — fallback when no rule fires) ───────
    mint   = 0.0
    burn   = 0.0
    reward = 0.0
    cash   = 0.0
    merch  = 0.0
    tsy_r  = 0.0

    # ════════════════════════════════════════════════════════
    # RULE SET 1: MINT FACTOR
    # Excel: "Minting rate DECREASES over time as system matures"
    # Excel: "Mint tied to: TX size, price, network activity, liquidity depth, treasury health"
    # ════════════════════════════════════════════════════════

    # Base maturity adjustment — reduce mint as ecosystem grows
    maturity_cut = day_norm * 0.4          # by end of episode, cut mint by 0.4 (→ 0.6× baseline)
    mint -= maturity_cut

    # Network activity boost — more TX = justify more mint (Excel: "network activity")
    if tx_volume_norm > 0.4:
        mint += 0.3                        # high activity → allow more mint
    elif tx_volume_norm > 0.2:
        mint += 0.1

    # Inflation control — Excel: "Minting penalised by inflation/price drop"
    if inflation > 0.05:
        mint = -0.8                        # >5% inflation → cut mint hard (0.2×)
    elif inflation > 0.03:
        mint = min(mint, -0.3)             # mild inflation → reduce

    # Price signal — Excel: "Mint reduced if price falling"
    if price_ratio < 0.80:
        mint = min(mint, -0.5)             # price crash → stop minting

    # Reward pool low + treasury ok → top up via mint
    if reward_pool_norm < 0.03 and tsy_healthy:
        mint = max(mint, 0.4)              # reward pool nearly empty → boost mint

    # ════════════════════════════════════════════════════════
    # RULE SET 2: BURN RATE
    # Excel: "% of TX fee burned to offset minting"
    # Excel: "Treasury burns when reserves EXCEED thresholds"
    # Excel: "Emergency burns during inflationary stress"
    # ════════════════════════════════════════════════════════

    if tsy_paytkn_norm < 0.20:
        burn = -1.0                        # treasury PAYTKN critical → STOP burning entirely
    elif tsy_paytkn_low:
        burn = -0.6                        # low PAYTKN reserve → reduce burn significantly
    elif inflation > 0.05:
        burn = 1.0                         # Excel: "Emergency burns during inflationary stress"
    elif inflation > 0.03:
        burn = 0.6                         # mild inflation → burn moderately more
    elif tsy_paytkn_norm > 1.5 and price_ratio > 1.2:
        burn = 0.8                         # Excel: "Burns when reserves exceed thresholds"
    elif tsy_healthy and price_ratio > 1.0:
        burn = 0.3                         # healthy ecosystem + rising price → steady burn
    elif price_ratio < 0.85:
        burn = -0.4                        # falling price → reduce burn, don't squeeze supply

    # ════════════════════════════════════════════════════════
    # RULE SET 3: REWARD ALLOC
    # Excel: "Rewards SCALE with treasury health (dynamic APY)"
    # Excel: "Max reward % relative to TX fees" (system-level threshold)
    # Excel: "AdjustFactor = min(1, TreasuryHealth + Sentiment)" — scales reward generosity
    # Excel: "DailyRewards ≤ Treasury / RunwayDays" → reward_cap capped by adjust_factor
    # Target APY range: 8–20% (sweet spot per reward weights)
    # ════════════════════════════════════════════════════════

    if tsy_stressed:
        reward = -0.6                      # treasury under pressure → cut rewards to protect treasury
    elif apy_norm >= 1.0:
        reward = -1.0                      # obs saturated → APY ≥ 30%: minimum reward_alloc (0.20)
    elif apy_norm >= 0.83:
        reward = -0.8                      # APY 25–30%: hard cut
    elif apy_norm >= 0.67:
        reward = -0.5                      # APY 20–25%: reduce
    elif apy_norm >= 0.50:
        reward = -0.2                      # APY 15–20%: at top of sweet spot → nudge down
    elif apy_norm < 0.17:
        reward = 0.8                       # APY < 5%: boost hard
    elif apy_norm < 0.27:
        reward = 0.5                       # APY 5–8%: boost
    elif apy_norm < 0.40 and tsy_healthy:
        reward = 0.2                       # APY 8–12%: gentle boost into sweet spot

    # Apply AdjustFactor cap: DailyRewards <= Treasury / RunwayDays.
    # When adjust_factor is low (treasury stressed or sentiment sour),
    # clamp reward_alloc action toward the _reward_cap_action ceiling.
    if adjust_factor < 0.60:
        reward = min(reward, _reward_cap_action)   # enforce runway-proportional cap

    # ════════════════════════════════════════════════════════
    # RULE SET 4: CASHBACK BASE RATE
    # Excel: "TX rewards scale with loyalty, value, frequency"
    # Excel: "Loyalty decay -10% per cancel — rebuild with consistent use"
    # Excel: "Users stay for cashback + staking to unlock higher tiers"
    # ════════════════════════════════════════════════════════

    # Loyalty tier mapping (Excel: tiered loyalty scaling)
    if loyalty > 0.75:
        cash = 0.5                         # high loyalty tier → generous cashback to reinforce
    elif loyalty > 0.50:
        cash = 0.2                         # mid loyalty → moderate boost
    elif loyalty < 0.30:
        cash = 0.7                         # loyalty decaying → max cashback to rebuild it
    elif loyalty < 0.45:
        cash = 0.4                         # low loyalty → boost cashback

    # Bear market / users leaving → retention priority
    if sentiment < 0.25 or user_growth < -0.05:
        cash = max(cash, 0.6)              # retention emergency — match max cashback

    # Treasury stressed → can't afford high cashback
    if tsy_stressed:
        cash = min(cash, 0.0)              # protect treasury over cashback

    # ════════════════════════════════════════════════════════
    # RULE SET 5: MERCHANT POOL ALLOC
    # Excel: "Rank-based bonuses scale with REAL TX volume"
    # Excel: "More merchants → more users → stronger token demand"
    # Excel: "Merchant invite rewards only valid if invitee meets TX + staking thresholds"
    # ════════════════════════════════════════════════════════

    if tx_volume_norm > 0.5:
        merch = 0.7                        # high TX volume → generous merchant rewards
    elif tx_volume_norm > 0.3:
        merch = 0.4                        # decent volume → good rewards to retain merchants
    elif tx_volume_norm > 0.15:
        merch = 0.1                        # moderate volume → slight boost
    elif tx_volume_norm < 0.05:
        merch = -0.5                       # very low volume → conserve fees for treasury

    # Treasury stressed → protect fees
    if tsy_stressed:
        merch = min(merch, -0.2)

    # ════════════════════════════════════════════════════════
    # RULE SET 6: TREASURY RATIO (mint split: treasury vs reward pool)
    # Static policy: FIXED 60/40 split — 60% of mint to treasury, 40% to reward pool.
    # With bounds (0.30, 0.90): action=0.0 maps exactly to 0.60 treasury ratio.
    # RL agent decides dynamically; static always uses the principled 60/40 default.
    # ════════════════════════════════════════════════════════

    tsy_r = 0.0   # fixed: action=0.0 → 0.60 treasury / 0.40 reward pool

    # ════════════════════════════════════════════════════════
    # GLOBAL SAFETY OVERRIDES
    # Excel: "Treasury cannot spend more than X% per epoch"
    # Excel: "Hard-coded allocation rules for rewards, buybacks, liquidity, burns"
    # ════════════════════════════════════════════════════════

    # High volatility → conservative across all levers
    if volatility > 0.5:
        mint  = min(mint,  -0.2)           # reduce new supply when market is volatile
        burn  = min(burn,   0.0)           # don't aggravate with extra burns
        cash  = max(cash,   0.3)           # keep cashback up for retention
        merch = min(merch,  0.0)           # conserve merchant pool

    # Clip all outputs to valid range
    return np.clip(
        np.array([mint, burn, reward, cash, merch, tsy_r], dtype=np.float32),
        -1.0, 1.0
    )


# ─────────────────────────────────────────────────────────────
# Scenario definitions
# ─────────────────────────────────────────────────────────────

SCENARIOS = {
    "bear":    {"initial_sentiment": 0.25, "rng_seed": 10},
    "neutral": {"initial_sentiment": 0.50, "rng_seed": 20},
    "bull":    {"initial_sentiment": 0.75, "rng_seed": 30},
}


def make_scenario_cfg(scenario: dict, episode_days: int = 180) -> SimConfig:
    # Population cap no longer needed for performance — PopulationManager is fully
    # vectorised (numpy arrays).  100 signups/day gives realistic ~50k-80k steady-state
    # populations for long episodes while staying within array capacity.
    max_signups = 100
    return SimConfig(
        initial_sentiment=scenario["initial_sentiment"],
        rng_seed=scenario["rng_seed"],
        episode_days=episode_days,
        max_daily_signups=max_signups,
    )


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
        "total_reward":          total_reward,
        "final_price":           last.get("price", 1.0),
        "final_treasury_stable": last.get("treasury_stable", 0.0),
        "final_treasury_paytkn": last.get("treasury_paytkn", 0.0),
        "final_users":           last.get("active_users", 0),
        "final_merchants":       last.get("active_merchants", 0),
        "final_lp_providers":    last.get("active_lp_providers", 0),
        "final_supply":          last.get("total_supply", 0.0),
        "final_staked":          last.get("total_staked", 0.0),
        "final_apy":             last.get("actual_apy", 0.0),
        "final_lp_depth":        last.get("lp_depth_stable", 0.0),
        "avg_daily_fees":        float(np.mean([d.get("daily_fees_collected", 0.0) for d in m])) if m else 0.0,
        "avg_daily_rewards":     float(np.mean([d.get("daily_rewards_paid", 0.0) for d in m])) if m else 0.0,
        "avg_daily_lp_fees":     float(np.mean([d.get("daily_fees_to_lps", 0.0) for d in m])) if m else 0.0,
        "avg_sentiment":         float(np.mean([d.get("sentiment", 0.5) for d in m])) if m else 0.0,
        "avg_staked":              float(np.mean([d.get("total_staked", 0.0) for d in m])) if m else 0.0,
        "avg_merchant_staked":     float(np.mean([d.get("merchant_staked", 0.0) for d in m])) if m else 0.0,
        "avg_merchant_pool_apy":   float(np.mean([d.get("merchant_pool_apy", 0.0) for d in m])) if m else 0.0,
        "avg_daily_cashback":      float(np.mean([d.get("daily_cashback_paid", 0.0) for d in m])) if m else 0.0,
        "avg_daily_tx_count":      float(np.mean([d.get("payment_count", 0) for d in m])) if m else 0.0,
        "cumulative_tx_volume":    last.get("cumulative_tx_volume", 0.0),
        "cumulative_rewards":      last.get("cumulative_rewards_paid", 0.0),
        "final_merchant_staked":   last.get("merchant_staked", 0.0),
        "final_merchant_pool":     last.get("merchant_staking_pool", 0.0),
        "avg_daily_burn":          float(np.mean([d.get("daily_burn", 0.0) for d in m])) if m else 0.0,
        "avg_daily_mint":          float(np.mean([d.get("daily_mint", 0.0) for d in m])) if m else 0.0,
        "final_treasury_paytkn":   last.get("treasury_paytkn", 0.0),
        "avg_daily_dev_fees":      float(np.mean([d.get("daily_fees_collected", 0.0) * 0.10 for d in m])) if m else 0.0,
        "avg_daily_in_app_volume": float(np.mean([d.get("daily_in_app_volume", 0.0) for d in m])) if m else 0.0,
    }


# ─────────────────────────────────────────────────────────────
# Main evaluation loop
# ─────────────────────────────────────────────────────────────

def print_results(scenario_name: str, results: dict, agents: list[str]) -> None:
    def avg(key, agent):
        return float(np.mean([r[key] for r in results[agent]]))

    for agent in agents:
        print(
            f"{scenario_name:<10} {agent:<10} "
            f"{avg('total_reward', agent):>8.1f} "
            f"{avg('final_price', agent):>7.4f} "
            f"{avg('final_users', agent):>7.0f} "
            f"{avg('final_merchants', agent):>7.0f} "
            f"{avg('final_lp_providers', agent):>4.0f} "
            f"{avg('final_apy', agent)*100:>6.1f}% "
            f"{avg('avg_merchant_pool_apy', agent)*100:>6.1f}% "
            f"{avg('final_treasury_stable', agent):>10.0f} "
            f"{avg('avg_daily_fees', agent):>8.1f} "
            f"{avg('avg_daily_cashback', agent):>8.2f} "
            f"{avg('avg_daily_tx_count', agent):>7.0f} "
            f"{avg('avg_daily_burn', agent):>8.2f} "
            f"{avg('cumulative_tx_volume', agent)/1e6:>7.2f}M"
        )


def evaluate(model_path: str | None, n_episodes: int = 3, baseline_only: bool = False, episode_days: int = 180) -> dict:
    agents = ["static"]
    model = None

    if not baseline_only and model_path:
        print(f"\n{'='*80}")
        print(f"  ChainEnv v3.2 Evaluation  |  Model: {model_path}")
    else:
        print(f"\n{'='*80}")
        print(f"  ChainEnv v3.1 Baseline Evaluation (rule-based heuristic policy)")

    print(f"  Scenarios: bear / neutral / bull  |  Episodes each: {n_episodes}  |  Days: {episode_days}")
    print(f"{'='*80}\n")

    if not baseline_only and model_path and os.path.exists(model_path):
        model = PPO.load(model_path, device="cpu")   # MlpPolicy runs faster on CPU
        agents = ["rl", "static"]
    elif not baseline_only:
        print(f"  [!] Model not found at {model_path} — running baseline only\n")

    header = (
        f"{'Scenario':<10} {'Agent':<10} {'Reward':>8} {'Price':>7} "
        f"{'Users':>7} {'Mrchts':>7} {'LPs':>4} "
        f"{'UserAPY':>7} {'MrchAPY':>7} "
        f"{'Treasury$':>10} {'Fees/d':>8} {'Cashbk/d':>8} "
        f"{'Txns/d':>7} {'Burn/d':>8} {'TxVol':>8}"
    )
    print(header)
    print("-" * len(header))

    all_results = {}

    for scenario_name, scenario_cfg in SCENARIOS.items():
        cfg = make_scenario_cfg(scenario_cfg, episode_days=episode_days)
        results = {a: [] for a in agents}

        for ep in range(n_episodes):
            seed = scenario_cfg["rng_seed"] + ep * 100

            if model is not None:
                env_rl = PaytknEnv(cfg)
                results["rl"].append(run_episode(env_rl, model, seed=seed))

            env_static = PaytknEnv(cfg)
            results["static"].append(run_episode(env_static, "static", seed=seed))

        print_results(scenario_name, results, agents)
        all_results[scenario_name] = results
        print()

    # Summary stats
    print("\n--- Summary (static baseline across all scenarios) ---")
    all_static = [r for sc in all_results.values() for r in sc["static"]]
    def gavg(key): return float(np.mean([r[key] for r in all_static]))

    print(f"  Avg cumulative TX volume : ${gavg('cumulative_tx_volume'):>12,.0f}")
    print(f"  Avg final users          : {gavg('final_users'):>8,.0f}")
    print(f"  Avg final merchants      : {gavg('final_merchants'):>8,.0f}")
    print(f"  Avg final price          : ${gavg('final_price'):>8.4f}")
    print(f"")
    print(f"  -- Treasury -------------------------------------------------")
    print(f"  Avg final treasury stable  : ${gavg('final_treasury_stable'):>12,.0f}")
    print(f"  Avg final treasury PAYTKN  : {gavg('final_treasury_paytkn'):>12,.0f} PAYTKN")
    print(f"")
    print(f"  -- Revenue & Fees -------------------------------------------")
    print(f"  Avg daily fees collected   : ${gavg('avg_daily_fees'):>10,.2f}")
    print(f"  Avg daily dev fees (10%)   : ${gavg('avg_daily_dev_fees'):>10,.2f}")
    print(f"  Avg daily in-app volume    : ${gavg('avg_daily_in_app_volume'):>10,.2f}")
    print(f"  Avg daily cashback paid    : ${gavg('avg_daily_cashback'):>10,.2f}")
    print(f"  Avg daily tx count         :  {gavg('avg_daily_tx_count'):>8,.0f}")
    print(f"")
    print(f"  -- Token Supply ---------------------------------------------")
    print(f"  Avg daily burn             :  {gavg('avg_daily_burn'):>10,.2f} PAYTKN")
    print(f"  Avg daily mint             :  {gavg('avg_daily_mint'):>10,.2f} PAYTKN")
    print(f"")
    print(f"  -- Staking --------------------------------------------------")
    print(f"  Avg user staking APY       :  {gavg('final_apy')*100:>6.2f}%")
    print(f"  Avg merchant pool APY      :  {gavg('avg_merchant_pool_apy')*100:>6.2f}%")

    # Save results
    os.makedirs("models", exist_ok=True)
    out_path = "models/eval_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nFull results saved -> {out_path}")

    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate ChainEnv v3.1")
    parser.add_argument("--model", type=str, default="models/best_model.zip")
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--baseline-only", action="store_true",
                        help="Skip RL model, run static baseline only")
    parser.add_argument("--days", type=int, default=180,
                        help="Episode length in days (default 180, try 365 for 1-year eval)")
    args = parser.parse_args()
    evaluate(
        model_path=args.model,
        n_episodes=args.episodes,
        baseline_only=args.baseline_only,
        episode_days=args.days,
    )
