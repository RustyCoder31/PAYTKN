"""Behavioral archetypes for users and merchants.

v3: Payment-utility-first. Users are payment CONSUMERS, not DeFi farmers.
  - payment_prob is the primary activity (not staking)
  - wallet is in STABLE (USD), not PAYTKN
  - Staking is optional/secondary — users who want to earn passively
  - Churn is low (people don't abandon payment apps the way they abandon DeFi)
  - Speculators are a tiny, separate minority
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class UserProfile:
    """Daily behaviour parameters for a user archetype.

    wallet unit: stable (USD)
    staked unit: PAYTKN (bought from AMM and locked)
    """
    name: str

    # --- daily action probabilities ---
    payment_prob:   float   # chance of making a payment today
    stake_prob:     float   # chance of staking (buying PAYTKN to lock)
    unstake_prob:   float   # chance of unstaking
    trade_prob:     float   # chance of speculative buy/sell (tiny for most)
    invite_prob:    float   # chance of inviting a friend today
    cancel_prob:    float   # chance of cancelling a subscription

    # --- transaction sizes (USD / stable equivalent) ---
    avg_payment_amount: float   # average payment size in USD
    avg_trade_amount:   float   # average speculative trade in USD
    avg_stake_amount:   float   # average PAYTKN stake in USD equivalent

    # --- market sensitivity ---
    price_sensitivity:  float   # 0..1 — speculators high, regular payers low
    reward_sensitivity: float   # 0..1 — how much APY/cashback drives behaviour

    # --- retention ---
    churn_probability:  float   # baseline daily probability of leaving
    recurring_factor:   float   # 0..1 — daily active probability


@dataclass(frozen=True)
class MerchantProfile:
    """Behaviour parameters for a merchant archetype."""
    name: str

    daily_expected_payments: int    # average payment transactions received per day
    avg_payment_received:    float  # average USD per payment received

    stake_rate:      float   # fraction of wallet auto-staked each day

    churn_probability: float


# ─────────────────────────────────────────────────────────────
# User archetypes — payment-utility first
# ─────────────────────────────────────────────────────────────

USER_ARCHETYPES: dict[str, UserProfile] = {

    # 40% of users — everyday consumer, pays regularly, doesn't think about staking
    "regular_payer": UserProfile(
        name="regular_payer",
        payment_prob=0.65,  stake_prob=0.03,  unstake_prob=0.01,
        trade_prob=0.01,    invite_prob=0.03, cancel_prob=0.01,
        avg_payment_amount=25.0, avg_trade_amount=50.0, avg_stake_amount=100.0,
        price_sensitivity=0.10, reward_sensitivity=0.50,
        churn_probability=0.0008, recurring_factor=0.75,
    ),

    # 25% — heavy everyday user, pays a lot, moderately stakes for cashback
    "power_payer": UserProfile(
        name="power_payer",
        payment_prob=0.85,  stake_prob=0.08,  unstake_prob=0.01,
        trade_prob=0.02,    invite_prob=0.06, cancel_prob=0.005,
        avg_payment_amount=80.0, avg_trade_amount=100.0, avg_stake_amount=400.0,
        price_sensitivity=0.10, reward_sensitivity=0.80,
        churn_probability=0.0004, recurring_factor=0.90,
    ),

    # 15% — passive holder and staker, pays occasionally
    "staker": UserProfile(
        name="staker",
        payment_prob=0.25,  stake_prob=0.20,  unstake_prob=0.03,
        trade_prob=0.02,    invite_prob=0.02, cancel_prob=0.01,
        avg_payment_amount=40.0, avg_trade_amount=150.0, avg_stake_amount=800.0,
        price_sensitivity=0.30, reward_sensitivity=0.95,
        churn_probability=0.0010, recurring_factor=0.70,
    ),

    # 10% — inactive / low-engagement (signed up, rarely pays)
    "inactive": UserProfile(
        name="inactive",
        payment_prob=0.08,  stake_prob=0.01,  unstake_prob=0.01,
        trade_prob=0.005,   invite_prob=0.005, cancel_prob=0.02,
        avg_payment_amount=10.0, avg_trade_amount=30.0, avg_stake_amount=50.0,
        price_sensitivity=0.15, reward_sensitivity=0.20,
        churn_probability=0.0050, recurring_factor=0.25,
    ),

    # 5% — speculator, minimal payments, heavy trading
    "speculator": UserProfile(
        name="speculator",
        payment_prob=0.05,  stake_prob=0.04,  unstake_prob=0.10,
        trade_prob=0.35,    invite_prob=0.01, cancel_prob=0.04,
        avg_payment_amount=20.0, avg_trade_amount=2_000.0, avg_stake_amount=500.0,
        price_sensitivity=0.95, reward_sensitivity=0.30,
        churn_probability=0.0020, recurring_factor=0.55,
    ),

    # 5% — whale, large payments and large stakes
    "whale": UserProfile(
        name="whale",
        payment_prob=0.45,  stake_prob=0.12,  unstake_prob=0.03,
        trade_prob=0.08,    invite_prob=0.04, cancel_prob=0.005,
        avg_payment_amount=500.0, avg_trade_amount=5_000.0, avg_stake_amount=8_000.0,
        price_sensitivity=0.25, reward_sensitivity=0.70,
        churn_probability=0.0004, recurring_factor=0.80,
    ),
}

MERCHANT_ARCHETYPES: dict[str, MerchantProfile] = {

    # 45% — small shop, café, freelancer
    "small_retailer": MerchantProfile(
        name="small_retailer",
        daily_expected_payments=8,   avg_payment_received=20.0,
        stake_rate=0.10,
        churn_probability=0.002,
    ),

    # 30% — medium business (restaurant, online store)
    "medium_business": MerchantProfile(
        name="medium_business",
        daily_expected_payments=35,  avg_payment_received=55.0,
        stake_rate=0.15,
        churn_probability=0.001,
    ),

    # 15% — large business (chain, platform)
    "large_business": MerchantProfile(
        name="large_business",
        daily_expected_payments=120, avg_payment_received=150.0,
        stake_rate=0.20,
        churn_probability=0.0005,
    ),

    # 10% — subscription / SaaS (recurring small amounts, very predictable)
    "subscription": MerchantProfile(
        name="subscription",
        daily_expected_payments=60,  avg_payment_received=12.0,
        stake_rate=0.08,
        churn_probability=0.0008,
    ),
}

# ─────────────────────────────────────────────────────────────
# Sampling distributions
# ─────────────────────────────────────────────────────────────

_USER_WEIGHTS: dict[str, float] = {
    "regular_payer": 0.40,
    "power_payer":   0.25,
    "staker":        0.15,
    "inactive":      0.10,
    "speculator":    0.05,
    "whale":         0.05,
}

_MERCHANT_WEIGHTS: dict[str, float] = {
    "small_retailer":  0.45,
    "medium_business": 0.30,
    "large_business":  0.15,
    "subscription":    0.10,
}


def sample_user_profile(rng: np.random.Generator) -> str:
    names = list(_USER_WEIGHTS.keys())
    probs = list(_USER_WEIGHTS.values())
    return str(rng.choice(names, p=probs))


def sample_merchant_profile(rng: np.random.Generator) -> str:
    names = list(_MERCHANT_WEIGHTS.keys())
    probs = list(_MERCHANT_WEIGHTS.values())
    return str(rng.choice(names, p=probs))
