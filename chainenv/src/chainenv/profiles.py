"""Behavioral archetypes for users and merchants.

Each archetype is a frozen dataclass of probability parameters.
Users and merchants sample an archetype at spawn time and keep it for their lifetime.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class UserProfile:
    """Daily behaviour parameters for a user archetype."""
    name: str

    # --- daily action probabilities ---
    payment_prob: float         # chance of paying a merchant today
    stake_prob: float           # chance of staking more PAYTKN today
    unstake_prob: float         # chance of unstaking today
    trade_prob: float           # chance of buying/selling on DEX today
    invite_prob: float          # chance of inviting a new user today
    cancel_prob: float          # chance of cancelling a subscription today

    # --- transaction sizes (in PAYTKN) ---
    avg_payment_amount: float
    avg_trade_amount: float
    avg_stake_amount: float

    # --- market sensitivity ---
    price_sensitivity: float    # 0..1 — how much price drops amplify sell/churn
    reward_sensitivity: float   # 0..1 — how much high APY drives staking

    # --- retention ---
    churn_probability: float    # baseline daily probability of leaving ecosystem
    recurring_factor: float     # 0..1 — daily probability of being active (vs dormant day)


@dataclass(frozen=True)
class MerchantProfile:
    """Behaviour parameters for a merchant archetype."""
    name: str

    # --- revenue activity ---
    daily_expected_payments: int    # average payments received per day
    avg_payment_received: float     # average PAYTKN per payment received

    # --- treasury behaviour ---
    stake_rate: float               # fraction of received payments auto-staked
    loan_prob: float                # daily probability of taking a merchant loan
    loan_size_factor: float         # multiplier on base loan size (treasury_stable * 0.05)

    # --- retention ---
    churn_probability: float        # daily probability of leaving


# ─────────────────────────────────────────────────────────────
# PAYTKN reference archetypes
# ─────────────────────────────────────────────────────────────

USER_ARCHETYPES: dict[str, UserProfile] = {
    "casual": UserProfile(
        name="casual",
        payment_prob=0.15, stake_prob=0.02, unstake_prob=0.01,
        trade_prob=0.05, invite_prob=0.01, cancel_prob=0.03,
        avg_payment_amount=30.0, avg_trade_amount=100.0, avg_stake_amount=50.0,
        price_sensitivity=0.4, reward_sensitivity=0.3,
        churn_probability=0.008, recurring_factor=0.50,
    ),
    "loyal": UserProfile(
        name="loyal",
        payment_prob=0.40, stake_prob=0.08, unstake_prob=0.01,
        trade_prob=0.02, invite_prob=0.05, cancel_prob=0.005,
        avg_payment_amount=50.0, avg_trade_amount=80.0, avg_stake_amount=200.0,
        price_sensitivity=0.2, reward_sensitivity=0.7,
        churn_probability=0.002, recurring_factor=0.90,
    ),
    "whale": UserProfile(
        name="whale",
        payment_prob=0.10, stake_prob=0.05, unstake_prob=0.03,
        trade_prob=0.20, invite_prob=0.02, cancel_prob=0.01,
        avg_payment_amount=500.0, avg_trade_amount=5_000.0, avg_stake_amount=10_000.0,
        price_sensitivity=0.7, reward_sensitivity=0.5,
        churn_probability=0.003, recurring_factor=0.70,
    ),
    "speculator": UserProfile(
        name="speculator",
        payment_prob=0.03, stake_prob=0.01, unstake_prob=0.08,
        trade_prob=0.40, invite_prob=0.005, cancel_prob=0.05,
        avg_payment_amount=20.0, avg_trade_amount=1_500.0, avg_stake_amount=300.0,
        price_sensitivity=0.9, reward_sensitivity=0.2,
        churn_probability=0.015, recurring_factor=0.40,
    ),
    "power_user": UserProfile(
        name="power_user",
        payment_prob=0.50, stake_prob=0.10, unstake_prob=0.02,
        trade_prob=0.10, invite_prob=0.15, cancel_prob=0.01,
        avg_payment_amount=75.0, avg_trade_amount=200.0, avg_stake_amount=500.0,
        price_sensitivity=0.3, reward_sensitivity=0.6,
        churn_probability=0.003, recurring_factor=0.85,
    ),
    "dormant": UserProfile(
        name="dormant",
        payment_prob=0.02, stake_prob=0.005, unstake_prob=0.005,
        trade_prob=0.01, invite_prob=0.001, cancel_prob=0.01,
        avg_payment_amount=15.0, avg_trade_amount=50.0, avg_stake_amount=20.0,
        price_sensitivity=0.1, reward_sensitivity=0.1,
        churn_probability=0.020, recurring_factor=0.20,
    ),
}

MERCHANT_ARCHETYPES: dict[str, MerchantProfile] = {
    "small_retailer": MerchantProfile(
        name="small_retailer",
        daily_expected_payments=5, avg_payment_received=40.0,
        stake_rate=0.30, loan_prob=0.005, loan_size_factor=0.5,
        churn_probability=0.010,
    ),
    "medium_business": MerchantProfile(
        name="medium_business",
        daily_expected_payments=25, avg_payment_received=60.0,
        stake_rate=0.50, loan_prob=0.015, loan_size_factor=1.0,
        churn_probability=0.005,
    ),
    "large_business": MerchantProfile(
        name="large_business",
        daily_expected_payments=100, avg_payment_received=150.0,
        stake_rate=0.60, loan_prob=0.025, loan_size_factor=3.0,
        churn_probability=0.002,
    ),
    "subscription": MerchantProfile(
        name="subscription",
        daily_expected_payments=50, avg_payment_received=12.0,
        stake_rate=0.40, loan_prob=0.010, loan_size_factor=1.2,
        churn_probability=0.004,
    ),
}

# ─────────────────────────────────────────────────────────────
# Sampling distributions
# ─────────────────────────────────────────────────────────────

_USER_WEIGHTS: dict[str, float] = {
    "casual": 0.45,
    "loyal": 0.20,
    "whale": 0.03,
    "speculator": 0.12,
    "power_user": 0.10,
    "dormant": 0.10,
}

_MERCHANT_WEIGHTS: dict[str, float] = {
    "small_retailer": 0.55,
    "medium_business": 0.30,
    "large_business": 0.05,
    "subscription": 0.10,
}


def sample_user_profile(rng: np.random.Generator) -> str:
    """Sample a user archetype name according to realistic population distribution."""
    names = list(_USER_WEIGHTS.keys())
    probs = list(_USER_WEIGHTS.values())
    return str(rng.choice(names, p=probs))


def sample_merchant_profile(rng: np.random.Generator) -> str:
    """Sample a merchant archetype name according to realistic distribution."""
    names = list(_MERCHANT_WEIGHTS.keys())
    probs = list(_MERCHANT_WEIGHTS.values())
    return str(rng.choice(names, p=probs))
