"""Population manager — spawns and churns users, merchants, and LP providers.

Growth model:
  - Daily signups drawn from Poisson(lambda = max_daily_signups * sentiment^2)
  - High sentiment -> aggressive growth (super-linear: squared)
  - Bear markets suppress growth to near zero
  - Churn is PRESSURE-BASED (gradual) — entities accumulate churn_pressure
    from bad conditions; should_churn() rolls against effective probability.
  - LP providers enter at random intervals; exit when fee_yield < IL + risk_premium
    or when IL > 15% (catastrophic).

Performance notes:
  - _active_users / _active_merchants are maintained lists (O(1) add/remove)
    rather than recomputed every step via list comprehension.
  - Churn RNG is batched: rng.random(n) → one C call instead of n Python calls.
  - Loyalty average tracked as running mean — no per-step list comprehension.
"""

from __future__ import annotations
import numpy as np

from chainenv.config import SimConfig, AntiGamingRules
from chainenv.entities import User, Merchant, LiquidityProvider
from chainenv.profiles import (
    USER_ARCHETYPES, MERCHANT_ARCHETYPES,
    sample_user_profile, sample_merchant_profile,
)


class PopulationManager:
    """Owns the full lists of all entity types for one episode."""

    def __init__(self, cfg: SimConfig, rng: np.random.Generator) -> None:
        self.cfg = cfg
        self.rng = rng
        self.rules: AntiGamingRules = cfg.rules

        self.users: list[User] = []
        self.merchants: list[Merchant] = []
        self.lp_providers: list[LiquidityProvider] = []

        # Maintained active lists — mutated on add/churn (no per-step scan)
        self._active_users: list[User] = []
        self._active_merchants: list[Merchant] = []

        # Running loyalty mean (updated incrementally — no per-step comprehension)
        self._loyalty_sum: float = 0.0

        self._user_counter: int = 0
        self._merchant_counter: int = 0
        self._lp_counter: int = 0

    # ─────────────────────────────────────────────────────────
    # Seeding
    # ─────────────────────────────────────────────────────────

    def seed_initial(self, initial_price: float = 1.0) -> None:
        """Spawn the starting population defined in SimConfig."""
        for _ in range(self.cfg.initial_users):
            self._add_user(self._spawn_user())
        for _ in range(self.cfg.initial_merchants):
            self._add_merchant(self._spawn_merchant())
        for _ in range(self.cfg.initial_lp_providers):
            self.lp_providers.append(self._spawn_lp(initial_price))

    # ─────────────────────────────────────────────────────────
    # Daily update — main entry point
    # ─────────────────────────────────────────────────────────

    def daily_update(
        self,
        sentiment: float,
        actual_apy: float,
        price: float,
        price_ratio: float,
    ) -> tuple[int, int]:
        """Grow and churn population. Returns (new_users, churned_users)."""
        self._update_all_churn_pressure(actual_apy, sentiment, price_ratio)

        new_users = self._grow_users(sentiment)
        self._grow_merchants(sentiment)

        churned = self._churn_users()
        self._churn_merchants()

        return new_users, churned

    def daily_update_lp_providers(
        self,
        current_price: float,
        daily_fees_to_lps: float,
        treasury_covers_il: bool,
    ) -> int:
        """Update LP provider state and handle exits. Returns count of exits."""
        exits = 0
        for lp in self.lp_providers:
            if not lp.active:
                continue
            lp_fee_income = daily_fees_to_lps * lp.lp_share
            stayed = lp.update(
                rng=self.rng,
                current_price=current_price,
                daily_fee_income=lp_fee_income,
                treasury_covers_il=treasury_covers_il,
                rules=self.rules,
            )
            if not stayed:
                exits += 1
        self._grow_lp_providers(current_price)
        return exits

    def weekly_reset(self) -> None:
        """Reset weekly counters on all entities (call every 7 days)."""
        for u in self.users:
            u.weekly_reset()
        for m in self.merchants:
            m.weekly_reset()

    # ─────────────────────────────────────────────────────────
    # Active views — maintained lists, not recomputed each step
    # ─────────────────────────────────────────────────────────

    @property
    def active_users(self) -> list[User]:
        return self._active_users

    @property
    def active_merchants(self) -> list[Merchant]:
        return self._active_merchants

    @property
    def active_lp_providers(self) -> list[LiquidityProvider]:
        return [lp for lp in self.lp_providers if lp.active]

    @property
    def loyalty_avg(self) -> float:
        """Running mean loyalty — no per-step list comprehension."""
        n = len(self._active_users)
        return self._loyalty_sum / n if n > 0 else 1.0

    # ─────────────────────────────────────────────────────────
    # Internal list maintenance
    # ─────────────────────────────────────────────────────────

    def _add_user(self, u: User) -> None:
        self.users.append(u)
        self._active_users.append(u)
        self._loyalty_sum += u.loyalty_score

    def _add_merchant(self, m: Merchant) -> None:
        self.merchants.append(m)
        self._active_merchants.append(m)

    def _remove_user(self, u: User) -> None:
        """Mark inactive and remove from active list."""
        u.churn()
        self._active_users.remove(u)
        self._loyalty_sum -= u.loyalty_score

    def _remove_merchant(self, m: Merchant) -> None:
        m.churn()
        self._active_merchants.remove(m)

    # ─────────────────────────────────────────────────────────
    # Churn pressure updates
    # ─────────────────────────────────────────────────────────

    def _update_all_churn_pressure(
        self,
        actual_apy: float,
        sentiment: float,
        price_ratio: float,
    ) -> None:
        """Update pressure for all active users and merchants each day."""
        for u in self._active_users:
            u.update_churn_pressure(actual_apy, sentiment, price_ratio, self.rules)
        for m in self._active_merchants:
            m.update_churn_pressure(actual_apy, self.rules)

    # ─────────────────────────────────────────────────────────
    # Growth
    # ─────────────────────────────────────────────────────────

    def _grow_users(self, sentiment: float) -> int:
        lam = self.cfg.max_daily_signups * (sentiment ** 2)
        lam = max(0.1, lam)
        n_new = min(int(self.rng.poisson(lam)), self.cfg.max_daily_signups)
        for _ in range(n_new):
            self._add_user(self._spawn_user())
        return n_new

    def _grow_merchants(self, sentiment: float) -> int:
        lam = max(0.05, self.cfg.max_daily_signups * 0.05 * sentiment)
        n_new = int(self.rng.poisson(lam))
        for _ in range(n_new):
            self._add_merchant(self._spawn_merchant())
        return n_new

    def _grow_lp_providers(self, current_price: float) -> None:
        if self.rng.random() < 0.05:
            self.lp_providers.append(self._spawn_lp(current_price))

    # ─────────────────────────────────────────────────────────
    # Pressure-based churn — batched RNG
    # ─────────────────────────────────────────────────────────

    def _churn_users(self) -> int:
        """Batch RNG churn: one rng.random(n) call instead of n Python calls."""
        n = len(self._active_users)
        if n == 0:
            return 0

        rolls = self.rng.random(n)
        probs = np.array([
            u.profile.churn_probability * (1.0 + u.churn_pressure * 3.0)
            for u in self._active_users
        ])
        to_churn = [u for u, roll, prob in zip(self._active_users, rolls, probs) if roll < prob]

        for u in to_churn:
            self._loyalty_sum -= u.loyalty_score
            u.churn()

        for u in to_churn:
            self._active_users.remove(u)

        return len(to_churn)

    def _churn_merchants(self) -> None:
        """Batch RNG churn for merchants."""
        n = len(self._active_merchants)
        if n == 0:
            return

        rolls = self.rng.random(n)
        probs = np.array([
            m.profile.churn_probability * (1.0 + m.churn_pressure * 3.0)
            for m in self._active_merchants
        ])
        to_churn = [m for m, roll, prob in zip(self._active_merchants, rolls, probs) if roll < prob]

        for m in to_churn:
            m.churn()
        for m in to_churn:
            self._active_merchants.remove(m)

    # ─────────────────────────────────────────────────────────
    # Spawning helpers
    # ─────────────────────────────────────────────────────────

    def _spawn_user(self) -> User:
        self._user_counter += 1
        archetype_name = sample_user_profile(self.rng)
        profile = USER_ARCHETYPES[archetype_name]
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

    def _spawn_lp(self, entry_price: float) -> LiquidityProvider:
        self._lp_counter += 1
        paytkn_dep = float(self.rng.lognormal(mean=9.0, sigma=1.2))
        stable_dep = paytkn_dep * entry_price
        lp_share = float(self.rng.uniform(0.02, 0.15))
        return LiquidityProvider(
            lp_id=f"lp{self._lp_counter}",
            entry_price=max(0.001, entry_price),
            paytkn_deposited=paytkn_dep,
            stable_deposited=stable_dep,
            lp_share=lp_share,
        )
