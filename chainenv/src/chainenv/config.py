"""Parameter bounds, tunable reward weights, and simulator defaults.

This is the primary public interface for ChainEnv.
To simulate your own token: subclass or replace SimConfig with your parameters.
PAYTKN values are the shipped defaults.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


def map_action(raw: float, lo: float, hi: float) -> float:
    """Map RL agent raw action in [-1, 1] → [lo, hi], clipping out-of-range values."""
    clamped = float(np.clip(raw, -1.0, 1.0))
    return lo + (clamped + 1.0) / 2.0 * (hi - lo)


@dataclass(frozen=True)
class ActionBounds:
    """Min/max for each economic lever the RL agent controls.

    All five correspond to PAYTKN tokenomics levers.
    Other token configs should override these to match their mechanisms.
    """
    mint_rate: tuple[float, float] = (0.0, 0.05)       # daily mint as fraction of supply
    burn_pct: tuple[float, float] = (0.001, 0.03)      # fraction of TX value burned
    staking_apy: tuple[float, float] = (0.02, 0.25)    # annualised staking yield
    treasury_ratio: tuple[float, float] = (0.6, 0.9)   # target PAYTKN:stable in treasury
    reward_alloc: tuple[float, float] = (0.1, 0.4)     # fraction of minted tokens → rewards


@dataclass
class RewardWeights:
    """User-tunable optimization objective weights.

    Positive weights (should sum to 1.0):
        price_growth, treasury_growth, user_retention, tx_volume, staking_ratio

    Penalty weights (applied as negative, keep small):
        volatility_penalty, inflation_penalty, churn_penalty
    """
    # --- positive objectives ---
    price_growth: float = 0.25
    treasury_growth: float = 0.20
    user_retention: float = 0.20
    tx_volume: float = 0.20
    staking_ratio: float = 0.15
    # --- penalties (negative direction) ---
    volatility_penalty: float = 0.10
    inflation_penalty: float = 0.05
    churn_penalty: float = 0.10


@dataclass
class AntiGamingRules:
    """Hardcoded Sheet-7 thresholds — these are protocol invariants, NOT AI-controlled.

    The RL agent cannot override these. They are enforced at the entity level.
    """
    cancel_limit_per_week: int = 3
    invite_depth_max: int = 5
    loyalty_decay_per_cancel: float = 0.10      # multiplicative decay per cancel event
    collateral_ratio: float = 1.50              # 150% overcollateral for merchant loans
    tx_staking_delay_days: int = 7              # delay before staked TX tokens mature
    merchant_wallet_limit_per_week: int = 2     # linked wallet changes per merchant/week


@dataclass
class SimConfig:
    """Top-level simulator configuration — all PAYTKN defaults.

    Fixed-seed by design (decision: deterministic start conditions for reproducibility).
    Set rng_seed=None for randomized starts.
    """
    # --- population ---
    initial_users: int = 100
    initial_merchants: int = 20

    # --- token supply ---
    initial_supply: float = 100_000_000        # total circulating at genesis
    initial_price: float = 1.0                 # USD peg at launch (floats immediately)

    # --- AMM (constant product x*y=k) ---
    initial_lp_paytkn: float = 5_000_000
    initial_lp_stable: float = 5_000_000       # implies price = 1.0 at start

    # --- treasury seed ---
    initial_treasury_paytkn: float = 10_000_000
    initial_treasury_stable: float = 5_000_000

    # --- episode ---
    episode_days: int = 180                    # 6-month training episode

    # --- market sentiment ---
    initial_sentiment: float = 0.55            # slight optimism at launch
    sentiment_drift: float = 0.02              # daily reversion strength toward 0.5

    # --- organic growth model ---
    max_daily_signups: int = 50                # cap on new users per day
    base_churn_rate: float = 0.005             # 0.5% daily baseline churn

    # --- fee splits ---
    team_fee_share: float = 0.10               # 10% of TX tax → team allocation

    # --- reproducibility ---
    rng_seed: int = 42                         # fixed seed for deterministic episodes

    # --- sub-configs (composable) ---
    weights: RewardWeights = field(default_factory=RewardWeights)
    bounds: ActionBounds = field(default_factory=ActionBounds)
    rules: AntiGamingRules = field(default_factory=AntiGamingRules)
