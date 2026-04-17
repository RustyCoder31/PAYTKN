"""Population manager — spawns and churns users and merchants organically.

Growth model:
  - Daily signups drawn from Poisson(lambda = max_daily_signups * sentiment²)
  - High sentiment → aggressive growth (super-linear: squared)
  - Bear markets suppress growth to near zero
  - Each new user starts with a random wallet seeded from their archetype
  - Churn: each active entity rolls against (base_churn + sentiment_penalty)
"""

from __future__ import annotations
import numpy as np

from chainenv.config import SimConfig
from chainenv.entities import User, Merchant
from chainenv.profiles import (
    USER_ARCHETYPES, MERCHANT_ARCHETYPES,
    sample_user_profile, sample_merchant_profile,
)


class PopulationManager:
    """Owns the full lists of users and merchants for one episode."""

    def __init__(self, cfg: SimConfig, rng: np.random.Generator) -> None:
        self.cfg = cfg
        self.rng = rng

        self.users: list[User] = []
        self.merchants: list[Merchant] = []

        self._user_counter: int = 0
        self._merchant_counter: int = 0

    # ─────────────────────────────────────────────────────────
    # Seeding
    # ─────────────────────────────────────────────────────────

    def seed_initial(self) -> None:
        """Spawn the starting population defined in SimConfig."""
        for _ in range(self.cfg.initial_users):
            self.users.append(self._spawn_user())
        for _ in range(self.cfg.initial_merchants):
            self.merchants.append(self._spawn_merchant())

    # ─────────────────────────────────────────────────────────
    # Daily update
    # ─────────────────────────────────────────────────────────

    def daily_update(self, sentiment: float) -> tuple[int, int]:
        """Grow and churn population. Returns (new_users, churned_users)."""
        new_users = self._grow_users(sentiment)
        churned = self._churn_users(sentiment)
        self._churn_merchants(sentiment)
        self._grow_merchants(sentiment)
        return new_users, churned

    def weekly_reset(self) -> None:
        """Reset weekly counters on all entities (call every 7 days)."""
        for u in self.users:
            u.weekly_reset()
        for m in self.merchants:
            m.weekly_reset()

    # ─────────────────────────────────────────────────────────
    # Active views
    # ─────────────────────────────────────────────────────────

    @property
    def active_users(self) -> list[User]:
        return [u for u in self.users if u.active]

    @property
    def active_merchants(self) -> list[Merchant]:
        return [m for m in self.merchants if m.active]

    # ─────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────

    def _grow_users(self, sentiment: float) -> int:
        """Add new users. Count drawn from Poisson scaled by sentiment²."""
        lam = self.cfg.max_daily_signups * (sentiment ** 2)
        lam = max(0.1, lam)
        n_new = int(self.rng.poisson(lam))
        n_new = min(n_new, self.cfg.max_daily_signups)
        for _ in range(n_new):
            self.users.append(self._spawn_user())
        return n_new

    def _grow_merchants(self, sentiment: float) -> int:
        """Add new merchants at ~5% of user growth rate."""
        lam = max(0.05, self.cfg.max_daily_signups * 0.05 * sentiment)
        n_new = int(self.rng.poisson(lam))
        for _ in range(n_new):
            self.merchants.append(self._spawn_merchant())
        return n_new

    def _churn_users(self, sentiment: float) -> int:
        """Mark low-loyalty users inactive based on churn probability."""
        churned = 0
        sentiment_penalty = max(0.0, 0.5 - sentiment) * 0.02  # extra churn in bear market
        for u in self.active_users:
            churn_p = u.profile.churn_probability + sentiment_penalty
            churn_p *= (1.0 + (1.0 - u.loyalty_score))  # low loyalty → higher churn
            if self.rng.random() < churn_p:
                u.churn()
                churned += 1
        return churned

    def _churn_merchants(self, sentiment: float) -> None:
        sentiment_penalty = max(0.0, 0.5 - sentiment) * 0.01
        for m in self.active_merchants:
            churn_p = m.profile.churn_probability + sentiment_penalty
            if self.rng.random() < churn_p:
                m.churn()

    def _spawn_user(self) -> User:
        self._user_counter += 1
        archetype_name = sample_user_profile(self.rng)
        profile = USER_ARCHETYPES[archetype_name]
        # Seed wallet from archetype avg_stake (gives variety across archetypes)
        wallet = float(self.rng.exponential(profile.avg_payment_amount * 5.0))
        wallet = max(10.0, wallet)
        return User(
            user_id=f"u{self._user_counter}",
            profile=profile,
            wallet_balance=wallet,
        )

    def _spawn_merchant(self) -> Merchant:
        self._merchant_counter += 1
        archetype_name = sample_merchant_profile(self.rng)
        profile = MERCHANT_ARCHETYPES[archetype_name]
        return Merchant(
            merchant_id=f"m{self._merchant_counter}",
            profile=profile,
        )
