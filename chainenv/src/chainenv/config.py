"""Parameter bounds, tunable reward weights, and simulator defaults.

PAYTKN v3.1 — Payment-utility-first architecture with full diagram alignment.

  Genesis: $10M raise seeds AMM: 10M PAYTKN + $10M stable → price = $1.00
  Payment flow uses Jumper/LI.FI style auto-conversion (modelled as AMM).
  APY is EMERGENT: daily_fee_income / total_staked × 365.
  Agent does NOT directly control APY — it controls reward_alloc, cashback_rate, etc.
  Minting is ADAPTIVE: scales with tx volume, inflation, and price stability.
  Burn is a SEPARATE RL lever — NOT deducted from payment fees.
  Merchant staking pool: separate from user pool, funded by tx fee slice.
  Staking Reward Engine: loyalty × lockup × invite_tier × amount_staked.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


def map_action(raw: float, lo: float, hi: float) -> float:
    """Map RL agent raw action in [-1, 1] to [lo, hi], clipping out-of-range."""
    clamped = float(np.clip(raw, -1.0, 1.0))
    return lo + (clamped + 1.0) / 2.0 * (hi - lo)


@dataclass(frozen=True)
class ActionBounds:
    """Min/max for each economic lever the RL agent controls.

    7 levers in v3.1 (based on system diagram):

    1. mint_factor          — multiplier on adaptive mint rate (0=no mint, 2=2× adaptive)
    2. burn_rate            — daily fraction of treasury PAYTKN to burn (agent-controlled,
                              separate from tx fees per user spec)
    3. reward_alloc         — fraction of tx fees routed to reward pool (user staking APY)
    4. cashback_base_rate   — base fraction of payment amount returned as cashback;
                              actual cashback is amplified by Tx Reward Engine factors
    5. merchant_pool_alloc  — fraction of tx fees routed to merchant staking pool
    6. lp_bonus_rate        — extra daily LP reward as fraction of pool value (attracts LPs)
    7. treasury_ratio       — target stable fraction in treasury (drives rebalancing)

    Note: burn is NOT deducted from payment fees. Team gets 10%, remaining split
    among reward_alloc + merchant_pool_alloc + treasury (remainder).
    LP providers earn naturally from 0.3% swap fees — no treasury subsidy needed.
    Loans removed — not needed at this stage.
    """
    mint_factor:          tuple[float, float] = (0.0,   2.0)    # adaptive mint multiplier
    burn_rate:            tuple[float, float] = (0.0,   0.0005) # daily treas PAYTKN burn fraction (max 0.05%/day)
    reward_alloc:         tuple[float, float] = (0.20,  0.60)   # tx fees → user reward pool
    cashback_base_rate:   tuple[float, float] = (0.001, 0.010)  # base cashback fraction (capped at 1%)
    merchant_pool_alloc:  tuple[float, float] = (0.05,  0.25)   # tx fees → merchant staking pool
    treasury_ratio:       tuple[float, float] = (0.30,  0.90)   # mint split: treasury vs reward pool
    # action=0.0 (midpoint) → 0.60 treasury / 0.40 reward pool (static fixed split)


@dataclass
class RewardWeights:
    """Optimization objective for the RL agent.

    Primary goal: keep treasury healthy (above floor, PAYTKN growing from fees).
    Secondary goals: user growth, stability, payment volume, good APY.

    Positive weights should sum to ~1.0.
    """
    # --- positive objectives ---
    treasury_health: float = 0.30   # PRIMARY — treasury stable above floor + PAYTKN growing
    user_growth:     float = 0.20   # more users = more fee revenue = treasury income
    stability:       float = 0.15   # price + volatility + sentiment
    tx_volume:       float = 0.15   # payment activity = real revenue stream
    apy_signal:      float = 0.10   # sustainable APY attracts + retains stakers
    lp_depth:        float = 0.05   # liquidity health
    price_growth:    float = 0.05   # controlled appreciation is fine

    # --- penalties ---
    treasury_floor_penalty: float = 0.40   # hard signal — treasury stable breached floor
    churn_penalty:          float = 0.20   # user loss hurts fee income
    volatility_penalty:     float = 0.10   # price swings hurt merchant adoption
    inflation_penalty:      float = 0.05   # runaway supply = bad
    treasury_cap_penalty:   float = 0.05   # mild nudge to redistribute excess PAYTKN


@dataclass
class AntiGamingRules:
    """Hardcoded ecosystem protection rules — NOT AI-controlled."""
    # Sheet 7 rules
    cancel_limit_per_week:          int   = 3
    invite_depth_max:               int   = 5
    loyalty_decay_per_cancel:       float = 0.10
    collateral_ratio:               float = 1.50
    tx_staking_delay_days:          int   = 7
    merchant_wallet_limit_per_week: int   = 2

    # Ecosystem floors
    min_staking_apy:        float = 0.03    # 3% floor — APY is emergent
    max_burn_rate:          float = 0.0005  # max 0.05%/day treasury burn (2M PAYTKN treasury)
    min_reward_pool_ratio:  float = 0.01    # reward pool >= 1% of supply

    # LP protection
    min_lp_depth_stable:        float = 2_000_000   # treasury injects if pool < $2M
    il_protection_threshold:    float = 0.05
    lp_risk_premium:            float = 0.02

    # Price corridor the treasury defends
    price_target:               float = 1.00
    price_band_pct:             float = 0.30   # ±30% → defend $0.70–$1.30

    # Merchant churn
    opportunity_cost_rate:      float = 0.03   # 3% (APY is fee-based)

    # User churn triggers
    user_min_apy_trigger:           float = 0.02
    user_bear_sentiment_trigger:    float = 0.25
    user_price_crash_trigger:       float = 0.50   # price < 50% of target = danger

    # Tx Reward Engine — cashback multiplier caps
    max_cashback_loyalty_boost:     float = 1.00   # loyalty can double cashback
    max_cashback_staking_boost:     float = 0.50   # staking adds up to 50% more
    max_cashback_seniority_boost:   float = 0.30   # seniority adds up to 30% more
    max_cashback_invite_boost:      float = 0.20   # invite tier adds up to 20% more

    # Merchant staking — separate pool settings
    merchant_pool_min_apy:          float = 0.02   # 2% minimum merchant pool APY

    # Treasury health limits
    treasury_stable_floor:          float = 500_000   # $500k minimum stable — hard floor
    treasury_paytkn_cap_ratio:      float = 1.50      # if treasury PAYTKN > 1.5× initial_stable
                                                      #   → auto-shift 30% excess to reward pool

    # In-app PAYTKN purchase (direct from treasury, no AMM)
    in_app_discount_rate:           float = 0.003     # price = AMM price × (1 - 0.3%) — saves LP fee
    max_wallet_pct_of_supply:       float = 0.005     # no wallet can hold > 0.5% of total supply
                                                      # prevents ecosystem concentration

    # Treasury price stabilizer (two-sided market maker)
    # Treasury sells PAYTKN when price rises fast → gets stable back
    # Treasury buys PAYTKN when price falls fast → spends stable
    # Goal: dampen daily volatility, not peg the price. Treasury rotates & profits.
    stabilizer_soft_band:           float = 0.03      # ±3% daily move before stabilizer fires
    stabilizer_max_stable_pct:      float = 0.02      # max 2% of available stable per intervention
    stabilizer_max_paytkn_pct:      float = 0.02      # max 2% of available PAYTKN per intervention
    stabilizer_paytkn_floor:        float = 500_000   # keep ≥500k PAYTKN for burns + in-app ops
    stabilizer_abs_cap_usd:         float = 30_000    # hard cap per day — gentle nudge, not a dump
    stabilizer_paytkn_min_threshold: float = 1_000_000 # pause PAYTKN selling when below 1M
                                                        # stabilizer becomes buy-only until treasury
                                                        # PAYTKN recovers via mint + fee routing

    # Treasury buyback (buyer-of-last-resort, from tokenomics design doc)
    # When treasury PAYTKN is depleting, treasury spends stable to buy PAYTKN from AMM.
    # Non-inflationary: converts stable reserves → PAYTKN (no new supply created).
    # Distinct from stabilizer (which dampens daily price swings).
    # Distinct from floor defence (which only fires at crash price <$0.70).
    treasury_buyback_threshold:     float = 1_000_000  # trigger when treasury_paytkn < 1M
    treasury_buyback_stable_buffer: float = 500_000    # need $500k above stable floor before buying
    treasury_buyback_max_pct:       float = 0.01       # max 1% of available stable per day
    treasury_buyback_abs_cap:       float = 20_000     # absolute cap $20k/day — gradual, not a dump
    treasury_target_paytkn_ratio:   float = 0.50       # target: treasury PAYTKN value = 50% of stable

    # Staking epoch (weekly)
    epoch_days:                     int   = 7


@dataclass
class SimConfig:
    """Top-level simulator configuration — PAYTKN v3.1 payment-utility defaults.

    Genesis: $10M raise seeds AMM with 10M PAYTKN + $10M stable → $1.00.
    Hard cap: 100M tokens (conservative adaptive minting).
    Treasury: $2M operational reserve separate from AMM liquidity.
    Users: 1,000 starting (realistic for a launched payment platform).
    """
    # --- token supply ---
    initial_supply: float = 12_000_000      # 10M in AMM + 2M in treasury at genesis
    max_supply:     float = 100_000_000     # hard cap (88M left to mint)
    initial_price:  float = 1.0             # $1.00 at launch

    # --- AMM pool (funded by $10M raise) ---
    initial_lp_paytkn: float = 10_000_000  # ALL genesis tokens in pool
    initial_lp_stable: float = 10_000_000  # $10M from raise → price = $1.00

    # --- treasury (operational reserve, separate from raise) ---
    initial_treasury_paytkn: float = 2_000_000    # 2M PAYTKN at genesis (counts in supply)
    initial_treasury_stable:  float = 2_000_000   # $2M stable operational reserve

    # --- fee structure ---
    lp_fee_rate:        float = 0.003   # 0.3% AMM swap fee → LP providers
    payment_fee_rate:   float = 0.005   # 0.5% protocol fee on every payment
    team_fee_share:     float = 0.10    # 10% of protocol fees → team

    # --- population (realistic launch scale) ---
    initial_users:          int = 1_000
    initial_merchants:      int = 100
    initial_lp_providers:   int = 10

    # --- episode ---
    episode_days: int = 180

    # --- market sentiment ---
    initial_sentiment: float = 0.55
    sentiment_drift:   float = 0.02

    # --- organic growth (faster for a payment utility) ---
    max_daily_signups:  int   = 500     # payment apps can grow virally
    base_churn_rate:    float = 0.001   # payment apps retain users

    # --- reproducibility ---
    rng_seed: int = 42

    # --- sub-configs ---
    weights: RewardWeights   = field(default_factory=RewardWeights)
    bounds:  ActionBounds    = field(default_factory=ActionBounds)
    rules:   AntiGamingRules = field(default_factory=AntiGamingRules)
