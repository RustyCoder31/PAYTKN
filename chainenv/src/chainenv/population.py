"""Population manager — vectorized numpy implementation (v4.0).

Replaces per-User/Merchant Python loops with bulk numpy array operations.
All mutable entity state is stored in pre-allocated arrays; profile data is
also stored in arrays after spawn.  UserView / MerchantView provide backward-
compatible object-style access for tests and read-only inspection.

Vectorisation gives ~50–100× speedup over the previous Python-loop approach
at population scales of 10 k–100 k users.
"""

from __future__ import annotations
import numpy as np

from chainenv.config import SimConfig, AntiGamingRules
from chainenv.entities import LiquidityProvider
from chainenv.profiles import (
    USER_ARCHETYPES, MERCHANT_ARCHETYPES,
    sample_user_profile, sample_merchant_profile,
)

# ─────────────────────────────────────────────────────────────────
# Profile lookup tables (fixed order)
# ─────────────────────────────────────────────────────────────────

_USER_NAMES = list(USER_ARCHETYPES.keys())          # 6 archetypes
_USER_PROBS = np.array([0.40, 0.25, 0.15, 0.10, 0.05, 0.05], dtype=np.float64)

_MERCH_NAMES = list(MERCHANT_ARCHETYPES.keys())     # 4 archetypes
_MERCH_PROBS = np.array([0.45, 0.30, 0.15, 0.10], dtype=np.float64)


# ─────────────────────────────────────────────────────────────────
# Array storage classes
# ─────────────────────────────────────────────────────────────────

class _UserArrays:
    """Pre-allocated numpy arrays for all user state."""

    __slots__ = (
        # mutable state
        "active", "wallet", "staked", "loyalty", "pressure",
        "days", "invite_depth", "cancels_this_week", "lifetime_pay",
        # profile (immutable after spawn, stored for vectorised access)
        "payment_prob", "avg_payment", "stake_prob", "avg_stake",
        "unstake_prob", "churn_prob", "recurring", "reward_sens",
        "price_sens", "trade_prob", "avg_trade", "cancel_prob", "invite_prob",
        # capacity cursor
        "_next",
    )

    def __init__(self, capacity: int) -> None:
        C = capacity
        self.active   = np.zeros(C, dtype=bool)
        self.wallet   = np.zeros(C, dtype=np.float64)
        self.staked   = np.zeros(C, dtype=np.float64)
        self.loyalty  = np.ones(C,  dtype=np.float64)
        self.pressure = np.zeros(C, dtype=np.float64)
        self.days     = np.zeros(C, dtype=np.int32)
        self.invite_depth          = np.zeros(C, dtype=np.int32)
        self.cancels_this_week     = np.zeros(C, dtype=np.int32)
        self.lifetime_pay          = np.zeros(C, dtype=np.float64)
        # profile
        self.payment_prob = np.zeros(C, dtype=np.float32)
        self.avg_payment  = np.zeros(C, dtype=np.float32)
        self.stake_prob   = np.zeros(C, dtype=np.float32)
        self.avg_stake    = np.zeros(C, dtype=np.float32)
        self.unstake_prob = np.zeros(C, dtype=np.float32)
        self.churn_prob   = np.zeros(C, dtype=np.float32)
        self.recurring    = np.zeros(C, dtype=np.float32)
        self.reward_sens  = np.zeros(C, dtype=np.float32)
        self.price_sens   = np.zeros(C, dtype=np.float32)
        self.trade_prob   = np.zeros(C, dtype=np.float32)
        self.avg_trade    = np.zeros(C, dtype=np.float32)
        self.cancel_prob  = np.zeros(C, dtype=np.float32)
        self.invite_prob  = np.zeros(C, dtype=np.float32)
        self._next = 0

    def spawn_batch(
        self,
        rng: np.random.Generator,
        n: int,
        profile_indices: np.ndarray,
        wallets: np.ndarray,
    ) -> np.ndarray:
        """Fill n slots from _next. Returns array of slot indices."""
        start = self._next
        end   = start + n
        idx   = np.arange(start, end, dtype=np.int32)

        self.active[idx]  = True
        self.wallet[idx]  = wallets
        self.staked[idx]  = 0.0
        self.loyalty[idx] = 1.0
        self.pressure[idx]= 0.0
        self.days[idx]    = 0
        self.invite_depth[idx]      = 0
        self.cancels_this_week[idx] = 0
        self.lifetime_pay[idx]      = 0.0

        for slot, pi in zip(idx.tolist(), profile_indices.tolist()):
            p = USER_ARCHETYPES[_USER_NAMES[pi]]
            self.payment_prob[slot] = p.payment_prob
            self.avg_payment[slot]  = p.avg_payment_amount
            self.stake_prob[slot]   = p.stake_prob
            self.avg_stake[slot]    = p.avg_stake_amount
            self.unstake_prob[slot] = p.unstake_prob
            self.churn_prob[slot]   = p.churn_probability
            self.recurring[slot]    = p.recurring_factor
            self.reward_sens[slot]  = p.reward_sensitivity
            self.price_sens[slot]   = p.price_sensitivity
            self.trade_prob[slot]   = p.trade_prob
            self.avg_trade[slot]    = p.avg_trade_amount
            self.cancel_prob[slot]  = p.cancel_prob
            self.invite_prob[slot]  = p.invite_prob

        self._next = end
        return idx

    def active_indices(self) -> np.ndarray:
        """Return array of active slot indices (fast numpy op)."""
        return np.where(self.active[: self._next])[0].astype(np.int32)


class _MerchantArrays:
    """Pre-allocated numpy arrays for all merchant state."""

    __slots__ = (
        "active", "wallet", "wallet_paytkn", "staked",
        "pressure", "days", "lifetime",
        "churn_prob", "stake_rate",
        "_next",
    )

    def __init__(self, capacity: int) -> None:
        C = capacity
        self.active        = np.zeros(C, dtype=bool)
        self.wallet        = np.zeros(C, dtype=np.float64)
        self.wallet_paytkn = np.zeros(C, dtype=np.float64)
        self.staked        = np.zeros(C, dtype=np.float64)
        self.pressure      = np.zeros(C, dtype=np.float64)
        self.days          = np.zeros(C, dtype=np.int32)
        self.lifetime      = np.zeros(C, dtype=np.float64)
        self.churn_prob    = np.zeros(C, dtype=np.float32)
        self.stake_rate    = np.zeros(C, dtype=np.float32)
        self._next = 0

    def spawn_batch(
        self,
        n: int,
        profile_indices: np.ndarray,
    ) -> np.ndarray:
        start = self._next
        end   = start + n
        idx   = np.arange(start, end, dtype=np.int32)

        self.active[idx]        = True
        self.wallet[idx]        = 0.0
        self.wallet_paytkn[idx] = 0.0
        self.staked[idx]        = 0.0
        self.pressure[idx]      = 0.0
        self.days[idx]          = 0
        self.lifetime[idx]      = 0.0

        for slot, pi in zip(idx.tolist(), profile_indices.tolist()):
            p = MERCHANT_ARCHETYPES[_MERCH_NAMES[pi]]
            self.churn_prob[slot] = p.churn_probability
            self.stake_rate[slot] = p.stake_rate

        self._next = end
        return idx

    def active_indices(self) -> np.ndarray:
        return np.where(self.active[: self._next])[0].astype(np.int32)


# ─────────────────────────────────────────────────────────────────
# Backward-compatible proxy objects
# ─────────────────────────────────────────────────────────────────

class UserView:
    """Read/write proxy into _UserArrays — looks like a User object."""
    __slots__ = ("_u", "_i")

    def __init__(self, arrays: _UserArrays, idx: int) -> None:
        object.__setattr__(self, "_u", arrays)
        object.__setattr__(self, "_i", idx)

    # ── identity ─────────────────────────────────────────────────
    @property
    def user_id(self) -> str: return f"u{self._i + 1}"

    # ── mutable state ─────────────────────────────────────────────
    @property
    def wallet(self) -> float: return float(self._u.wallet[self._i])
    @wallet.setter
    def wallet(self, v: float) -> None: self._u.wallet[self._i] = v

    @property
    def staked(self) -> float: return float(self._u.staked[self._i])
    @staked.setter
    def staked(self, v: float) -> None: self._u.staked[self._i] = v

    @property
    def loyalty_score(self) -> float: return float(self._u.loyalty[self._i])
    @loyalty_score.setter
    def loyalty_score(self, v: float) -> None: self._u.loyalty[self._i] = v

    @property
    def churn_pressure(self) -> float: return float(self._u.pressure[self._i])
    @property
    def days_active(self) -> int:      return int(self._u.days[self._i])
    @property
    def lifetime_payments(self) -> float: return float(self._u.lifetime_pay[self._i])
    @property
    def active(self) -> bool:          return bool(self._u.active[self._i])
    @property
    def invite_depth(self) -> int:     return int(self._u.invite_depth[self._i])

    def __repr__(self) -> str:
        return f"UserView(id={self.user_id}, wallet={self.wallet:.1f}, staked={self.staked:.1f})"


class MerchantView:
    """Read/write proxy into _MerchantArrays."""
    __slots__ = ("_m", "_i")

    def __init__(self, arrays: _MerchantArrays, idx: int) -> None:
        object.__setattr__(self, "_m", arrays)
        object.__setattr__(self, "_i", idx)

    @property
    def merchant_id(self) -> str: return f"m{self._i + 1}"

    @property
    def wallet(self) -> float: return float(self._m.wallet[self._i])
    @wallet.setter
    def wallet(self, v: float) -> None: self._m.wallet[self._i] = v

    @property
    def wallet_paytkn(self) -> float: return float(self._m.wallet_paytkn[self._i])
    @wallet_paytkn.setter
    def wallet_paytkn(self, v: float) -> None: self._m.wallet_paytkn[self._i] = v

    @property
    def staked(self) -> float:        return float(self._m.staked[self._i])
    @property
    def lifetime_volume(self) -> float: return float(self._m.lifetime[self._i])
    @property
    def active(self) -> bool:         return bool(self._m.active[self._i])
    @property
    def churn_pressure(self) -> float: return float(self._m.pressure[self._i])
    @property
    def days_active(self) -> int:     return int(self._m.days[self._i])

    def __repr__(self) -> str:
        return f"MerchantView(id={self.merchant_id}, paytkn={self.wallet_paytkn:.1f})"


# ─────────────────────────────────────────────────────────────────
# PopulationManager
# ─────────────────────────────────────────────────────────────────

class PopulationManager:
    """Vectorised population manager.  All user / merchant state lives in
    pre-allocated numpy arrays; no Python loops over individual entities
    during the simulation hot path."""

    USER_CAPACITY  = 1_000_000   # handles 1M+ total spawned users
    MERCH_CAPACITY =  150_000

    def __init__(self, cfg: SimConfig, rng: np.random.Generator) -> None:
        self.cfg   = cfg
        self.rng   = rng
        self.rules: AntiGamingRules = cfg.rules

        self._u = _UserArrays(self.USER_CAPACITY)
        self._m = _MerchantArrays(self.MERCH_CAPACITY)

        # LP providers — small count, keep as objects
        self.lp_providers: list[LiquidityProvider] = []
        self._lp_counter = 0

        # Cached active index arrays (rebuilt each day)
        self._u_idx: np.ndarray = np.empty(0, dtype=np.int32)
        self._m_idx: np.ndarray = np.empty(0, dtype=np.int32)

        # Running loyalty sum (for O(1) loyalty_avg)
        self._loyalty_sum: float = 0.0

        # Counters
        self._user_counter: int  = 0
        self._merch_counter: int = 0

    # ─────────────────────────────────────────────────────────────
    # Seeding
    # ─────────────────────────────────────────────────────────────

    def seed_initial(self, initial_price: float = 1.0) -> None:
        n_u = self.cfg.initial_users
        n_m = self.cfg.initial_merchants

        u_profiles = self.rng.choice(len(_USER_NAMES), size=n_u, p=_USER_PROBS)
        m_profiles = self.rng.choice(len(_MERCH_NAMES), size=n_m, p=_MERCH_PROBS)

        avg_pays = np.array(
            [USER_ARCHETYPES[_USER_NAMES[pi]].avg_payment_amount for pi in u_profiles],
            dtype=np.float64,
        )
        wallets = np.maximum(10.0, self.rng.exponential(avg_pays * 5.0))

        u_idx = self._u.spawn_batch(self.rng, n_u, u_profiles, wallets)
        m_idx = self._m.spawn_batch(n_m, m_profiles)

        self._u_idx = u_idx.copy()
        self._m_idx = m_idx.copy()
        self._loyalty_sum = float(n_u)   # all start at loyalty = 1.0
        self._user_counter  = n_u
        self._merch_counter = n_m

        # Seed initial LPs — they collectively own the full initial AMM pool.
        # Each LP gets an equal share; pool depth is already in Economy (10M/10M).
        n_lps = self.cfg.initial_lp_providers
        paytkn_per_lp = self.cfg.initial_lp_paytkn / max(1, n_lps)
        stable_per_lp = self.cfg.initial_lp_stable / max(1, n_lps)
        for _ in range(n_lps):
            lp = self._spawn_lp_seeded(initial_price, paytkn_per_lp, stable_per_lp)
            self.lp_providers.append(lp)

    # ─────────────────────────────────────────────────────────────
    # Daily update — main entry point
    # ─────────────────────────────────────────────────────────────

    def daily_update(
        self,
        sentiment: float,
        actual_apy: float,
        price: float,
        price_ratio: float,
        treasury_health: float = 1.0,
    ) -> tuple[int, int]:
        """Grow and churn population. Returns (new_users, churned_users)."""
        # Rebuild active index arrays once (fast numpy op)
        self._u_idx = self._u.active_indices()
        self._m_idx = self._m.active_indices()

        self._update_all_churn_pressure(actual_apy, sentiment, price_ratio)

        # Compute ecosystem growth multiplier
        # APY in sweet spot (8-20%) attracts stakers and earners
        apy_mult = 1.0 + float(np.clip((actual_apy - 0.05) / 0.10, 0.0, 1.0))   # 1.0x–2.0x
        # Price appreciation → FOMO / adoption news
        price_mult = 1.0 + float(np.clip((price_ratio - 1.0) * 0.15, 0.0, 0.5)) # 1.0x–1.5x
        # Treasury health → trust, marketing capacity, ecosystem confidence
        treasury_mult = 0.6 + 0.4 * float(np.clip(treasury_health, 0.0, 1.0))   # 0.6x–1.0x
        growth_mult = float(np.clip(apy_mult * price_mult * treasury_mult, 0.3, 4.0))

        new_users = self._grow_users(sentiment, growth_mult)
        self._grow_merchants(sentiment)

        churned = self._churn_users()
        self._churn_merchants()

        return new_users, churned

    def daily_update_lp_providers(
        self,
        current_price: float,
        daily_fees_to_lps: float,
        treasury_covers_il: bool,
    ) -> dict:
        """Update all LP providers. Returns pool delta dict for Economy to apply.

        Returns:
            {
              "paytkn_removed": float,  # from exiting LPs
              "stable_removed":  float,
              "paytkn_added":   float,  # from newly joined LPs
              "stable_added":    float,
            }
        """
        paytkn_removed = 0.0
        stable_removed  = 0.0

        # Update existing LPs and collect exits
        for lp in self.lp_providers:
            if not lp.active:
                continue
            stayed = lp.update(
                rng=self.rng,
                current_price=current_price,
                daily_fee_income=daily_fees_to_lps * lp.lp_share,
                treasury_covers_il=treasury_covers_il,
                rules=self.rules,
            )
            if not stayed:
                # Compute how much pool liquidity this LP owned
                paytkn_removed += lp.paytkn_deposited
                stable_removed  += lp.stable_deposited

        # Renormalize remaining LP shares after exits
        self._renormalize_lp_shares()

        # Grow pool with new LPs
        paytkn_added, stable_added = self._grow_lp_providers(current_price)

        return {
            "paytkn_removed": paytkn_removed,
            "stable_removed":  stable_removed,
            "paytkn_added":   paytkn_added,
            "stable_added":    stable_added,
        }

    def weekly_reset(self) -> None:
        """Reset weekly cancel counters (vectorised numpy write)."""
        n = self._u._next
        if n > 0:
            self._u.cancels_this_week[:n] = 0

    # ─────────────────────────────────────────────────────────────
    # Vectorised daily actions
    # ─────────────────────────────────────────────────────────────

    def compute_daily_user_actions(
        self,
        sentiment: float,
        price: float,
        actual_apy: float,
        rules: AntiGamingRules,
    ) -> dict:
        """All user decisions for one day — entirely vectorised.

        Returns a dict of aggregate economic values; no Python loop over users.
        Economy processes these aggregates via process_payment_batch() etc.
        """
        u   = self._u
        idx = self._u_idx
        n   = len(idx)

        _EMPTY: dict = {
            "total_payment_usd": 0.0, "n_payments": 0,
            "avg_loyalty": 1.0, "avg_staking_boost": 0.0,
            "avg_seniority_boost": 0.0, "avg_invite_boost": 0.0,
            "payer_indices": np.empty(0, dtype=np.int32),
            "payment_amounts": np.empty(0, dtype=np.float64),
            "total_stake_usd": 0.0,
            "stake_indices": np.empty(0, dtype=np.int32),
            "stake_amounts_usd": np.empty(0, dtype=np.float64),
            "total_unstake_paytkn": 0.0,
            "unstake_indices": np.empty(0, dtype=np.int32),
            "unstake_amounts_paytkn": np.empty(0, dtype=np.float64),
            "total_inapp_usd": 0.0,
            "total_amm_buy_usd": 0.0,
            "total_sell_paytkn": 0.0,
        }
        if n == 0:
            return _EMPTY

        rng            = self.rng
        activity_scale = 0.5 + sentiment

        # Local array views (reads — no copy needed for float arrays)
        wallets   = u.wallet[idx]
        stakeds   = u.staked[idx]
        loyalties = u.loyalty[idx]
        pressures = u.pressure[idx]
        days_f    = u.days[idx].astype(np.float64)
        invites_f = u.invite_depth[idx].astype(np.float64)
        price_sens   = u.price_sens[idx].astype(np.float64)
        reward_sens  = u.reward_sens[idx].astype(np.float64)

        sell_boost = price_sens * float(max(0.0, 1.0 - price))
        buy_boost  = price_sens * float(max(0.0, price - 1.0))
        stake_boost = reward_sens * float(min(1.0, actual_apy / 0.10))

        # ── Who is active today (recurring_factor check) ───────────
        act_rolls  = rng.random(n)
        today_mask = act_rolls <= u.recurring[idx].astype(np.float64)

        # Age all users (active or not)
        u.days[idx] += 1
        days_f += 1.0    # keep local view in sync

        if not today_mask.any():
            return _EMPTY

        # ── PAYMENTS ──────────────────────────────────────────────
        pay_prob_eff = np.minimum(
            1.0,
            u.payment_prob[idx].astype(np.float64) * activity_scale * loyalties,
        )
        can_pay  = wallets > 2.0
        pay_rolls = rng.random(n)
        pay_mask  = today_mask & can_pay & (pay_rolls < pay_prob_eff)

        if pay_mask.any():
            avg_p    = u.avg_payment[idx].astype(np.float64)
            raw_amt  = rng.normal(avg_p, avg_p * 0.25)
            amounts  = np.clip(raw_amt, 1.0, wallets)
            amounts[~pay_mask] = 0.0

            payer_local   = np.where(pay_mask)[0]
            payer_idx_arr = idx[payer_local]
            pay_amounts   = amounts[payer_local]

            stk_usd_pay  = stakeds[payer_local] * price
            avg_stk_b    = float(np.minimum(0.50, stk_usd_pay / 10_000).mean())
            avg_sen_b    = float(np.minimum(0.30, days_f[payer_local] / 365.0 * 0.30).mean())
            avg_inv_b    = float(np.minimum(0.20, invites_f[payer_local] * 0.04).mean())
            avg_loy      = float(loyalties[payer_local].mean())
            total_pay_usd = float(pay_amounts.sum())

            u.wallet[payer_idx_arr]     -= pay_amounts
            u.lifetime_pay[payer_idx_arr] += pay_amounts
        else:
            payer_idx_arr = np.empty(0, dtype=np.int32)
            pay_amounts   = np.empty(0, dtype=np.float64)
            total_pay_usd = avg_loy = avg_stk_b = avg_sen_b = avg_inv_b = 0.0

        # ── STAKES ────────────────────────────────────────────────
        stk_prob_eff = np.minimum(
            1.0,
            (u.stake_prob[idx].astype(np.float64) + stake_boost * 0.1) * activity_scale,
        )
        can_stake  = u.wallet[idx] > 20.0   # re-read after payment deductions
        stk_rolls  = rng.random(n)
        stk_mask   = today_mask & can_stake & (stk_rolls < stk_prob_eff)

        if stk_mask.any():
            avg_s    = u.avg_stake[idx].astype(np.float64)
            stk_raw  = rng.normal(avg_s, avg_s * 0.3)
            stk_amts = np.clip(stk_raw, 1.0, u.wallet[idx] * 0.5)
            stk_amts[~stk_mask] = 0.0

            stk_local   = np.where(stk_mask)[0]
            stk_idx_arr = idx[stk_local]
            stk_usd_arr = stk_amts[stk_local]

            u.wallet[stk_idx_arr] -= stk_usd_arr
            total_stake_usd = float(stk_usd_arr.sum())
        else:
            stk_idx_arr = np.empty(0, dtype=np.int32)
            stk_usd_arr = np.empty(0, dtype=np.float64)
            total_stake_usd = 0.0

        # ── UNSTAKES ──────────────────────────────────────────────
        has_staked   = u.staked[idx] > 0.0
        unstk_prob_eff = np.minimum(
            1.0,
            u.unstake_prob[idx].astype(np.float64) * (1.0 + pressures + sell_boost),
        )
        unstk_rolls = rng.random(n)
        unstk_mask  = today_mask & has_staked & (unstk_rolls < unstk_prob_eff)

        if unstk_mask.any():
            fracs        = rng.uniform(0.1, 0.4, n)
            unstk_amts   = u.staked[idx] * fracs
            unstk_amts[~unstk_mask] = 0.0

            unstk_local   = np.where(unstk_mask)[0]
            unstk_idx_arr = idx[unstk_local]
            unstk_paytkn  = unstk_amts[unstk_local]

            u.staked[unstk_idx_arr] -= unstk_paytkn
            total_unstake_paytkn = float(unstk_paytkn.sum())
        else:
            unstk_idx_arr  = np.empty(0, dtype=np.int32)
            unstk_paytkn   = np.empty(0, dtype=np.float64)
            total_unstake_paytkn = 0.0

        # ── BUYS (speculative) ────────────────────────────────────
        buy_prob_eff = np.minimum(
            1.0, u.trade_prob[idx].astype(np.float64) * (0.3 + buy_boost),
        )
        can_buy   = u.wallet[idx] > 10.0
        buy_rolls = rng.random(n)
        buy_mask  = today_mask & can_buy & (buy_rolls < buy_prob_eff)

        if buy_mask.any():
            avg_t    = u.avg_trade[idx].astype(np.float64)
            buy_raw  = rng.normal(avg_t * 0.5, avg_t * 0.15)
            buy_amts = np.clip(buy_raw, 1.0, u.wallet[idx] * 0.3)
            buy_amts[~buy_mask] = 0.0

            inapp_prob  = min(0.75, 0.60 + 0.15 * min(1.0, max(0.0, (actual_apy - 0.05) / 0.10)))
            inapp_rolls = rng.random(n)
            inapp_mask  = buy_mask & (inapp_rolls < inapp_prob)
            amm_buy_mask = buy_mask & ~inapp_mask

            buy_local   = np.where(buy_mask)[0]
            buy_idx_arr = idx[buy_local]
            u.wallet[buy_idx_arr] -= buy_amts[buy_local]

            total_inapp_usd   = float(buy_amts[inapp_mask].sum())
            total_amm_buy_usd = float(buy_amts[amm_buy_mask].sum())
        else:
            total_inapp_usd = total_amm_buy_usd = 0.0

        # ── SELLS (speculative) ───────────────────────────────────
        sell_prob_eff = np.minimum(
            1.0, u.trade_prob[idx].astype(np.float64) * (0.3 + sell_boost),
        )
        sell_rolls = rng.random(n)
        sell_mask  = today_mask & (u.staked[idx] > 0.0) & (sell_rolls < sell_prob_eff)

        if sell_mask.any():
            s_fracs    = rng.uniform(0.05, 0.25, n)
            sell_amts  = u.staked[idx] * s_fracs
            sell_amts[~sell_mask] = 0.0

            sell_local   = np.where(sell_mask)[0]
            sell_idx_arr = idx[sell_local]
            u.staked[sell_idx_arr] -= sell_amts[sell_local]
            total_sell_paytkn = float(sell_amts[sell_local].sum())
        else:
            total_sell_paytkn = 0.0

        return {
            "total_payment_usd":     total_pay_usd,
            "n_payments":            int(pay_mask.sum()),
            "avg_loyalty":           avg_loy,
            "avg_staking_boost":     avg_stk_b,
            "avg_seniority_boost":   avg_sen_b,
            "avg_invite_boost":      avg_inv_b,
            "payer_indices":         payer_idx_arr,
            "payment_amounts":       pay_amounts,
            "total_stake_usd":       total_stake_usd,
            "stake_indices":         stk_idx_arr,
            "stake_amounts_usd":     stk_usd_arr,
            "total_unstake_paytkn":  total_unstake_paytkn,
            "unstake_indices":       unstk_idx_arr,
            "unstake_amounts_paytkn": unstk_paytkn,
            "total_inapp_usd":       total_inapp_usd,
            "total_amm_buy_usd":     total_amm_buy_usd,
            "total_sell_paytkn":     total_sell_paytkn,
        }

    def compute_daily_merchant_actions(
        self,
        sentiment: float,
        price: float,
        actual_apy: float,
        rules: AntiGamingRules,
    ) -> dict:
        """Vectorised merchant sell / stake decisions."""
        m   = self._m
        idx = self._m_idx
        n   = len(idx)

        if n == 0:
            return {"total_sell_paytkn": 0.0, "total_stake_paytkn": 0.0, "total_stake_usd": 0.0}

        m.days[idx] += 1
        price_ratio = float(price / max(0.001, 1.0))

        # ── SELL PAYTKN ───────────────────────────────────────────
        has_paytkn  = m.wallet_paytkn[idx] > 5.0
        price_adj   = float(np.clip((price_ratio - 1.0) * 0.3, -0.5, 0.35))
        sell_prob   = float(np.clip(0.60 + price_adj, 0.1, 0.95))
        sell_rolls  = self.rng.random(n)
        sell_mask   = has_paytkn & (sell_rolls < sell_prob)

        total_sell_paytkn = 0.0
        if sell_mask.any():
            price_damper = 1.0 / max(1.0, price_ratio)
            lo = max(0.05, 0.40 * price_damper)
            hi = max(lo + 0.05, 0.90 * price_damper)
            fracs = self.rng.uniform(lo, hi, n)
            sell_amts = m.wallet_paytkn[idx] * fracs
            sell_amts[~sell_mask] = 0.0
            sell_idx = idx[sell_mask]
            m.wallet_paytkn[sell_idx] -= sell_amts[sell_mask]
            total_sell_paytkn = float(sell_amts[sell_mask].sum())

        # ── STAKE free PAYTKN ─────────────────────────────────────
        can_stk_p  = m.wallet_paytkn[idx] > 20.0
        stk_p_rolls = self.rng.random(n)
        stk_p_mask  = can_stk_p & (stk_p_rolls < m.stake_rate[idx].astype(np.float64))

        total_stake_paytkn = 0.0
        if stk_p_mask.any():
            stk_p_amts = m.wallet_paytkn[idx] * m.stake_rate[idx].astype(np.float64)
            stk_p_amts[~stk_p_mask] = 0.0
            stk_p_idx = idx[stk_p_mask]
            m.wallet_paytkn[stk_p_idx] -= stk_p_amts[stk_p_mask]
            m.staked[stk_p_idx]        += stk_p_amts[stk_p_mask]
            total_stake_paytkn = float(stk_p_amts[stk_p_mask].sum())

        # ── STAKE from wallet (stable → AMM) ──────────────────────
        can_stk_w  = m.wallet[idx] > 50.0
        stk_w_amts = m.wallet[idx] * m.stake_rate[idx].astype(np.float64) * 0.5
        stk_w_amts = np.where(can_stk_w & (stk_w_amts > 5.0), stk_w_amts, 0.0)

        total_stake_usd = 0.0
        if (stk_w_amts > 0).any():
            stk_w_idx = idx[stk_w_amts > 0]
            m.wallet[stk_w_idx] -= stk_w_amts[stk_w_amts > 0]
            total_stake_usd = float(stk_w_amts.sum())

        return {
            "total_sell_paytkn":   total_sell_paytkn,
            "total_stake_paytkn":  total_stake_paytkn,
            "total_stake_usd":     total_stake_usd,
        }

    # ─────────────────────────────────────────────────────────────
    # Cashback / proceeds distribution
    # ─────────────────────────────────────────────────────────────

    def receive_user_cashback(
        self,
        payer_indices: np.ndarray,
        payment_amounts: np.ndarray,
        total_cashback_paytkn: float,
    ) -> None:
        """Distribute cashback proportionally to payment amounts → user.staked."""
        if len(payer_indices) == 0 or total_cashback_paytkn <= 0:
            return
        tot = float(payment_amounts.sum())
        if tot <= 0:
            return
        shares = payment_amounts / tot * total_cashback_paytkn
        self._u.staked[payer_indices] += shares

    def record_user_stakes(
        self,
        stake_indices: np.ndarray,
        stake_amounts_usd: np.ndarray,
        total_paytkn_received: float,
    ) -> None:
        """Add PAYTKN received from batch AMM buy proportionally to stakers."""
        if len(stake_indices) == 0 or total_paytkn_received <= 0:
            return
        tot = float(stake_amounts_usd.sum())
        if tot <= 0:
            return
        shares = stake_amounts_usd / tot * total_paytkn_received
        self._u.staked[stake_indices] += shares

    def record_user_unstake_proceeds(
        self,
        unstake_indices: np.ndarray,
        unstake_amounts_paytkn: np.ndarray,
        total_stable_received: float,
    ) -> None:
        """Add stable proceeds back to unstakers' wallets proportionally."""
        if len(unstake_indices) == 0 or total_stable_received <= 0:
            return
        tot = float(unstake_amounts_paytkn.sum())
        if tot <= 0:
            return
        shares = unstake_amounts_paytkn / tot * total_stable_received
        self._u.wallet[unstake_indices] += shares

    def distribute_merchant_paytkn(self, total_paytkn: float, price: float) -> None:
        """Distribute payment PAYTKN receipts evenly among active merchants."""
        idx = self._m_idx
        n   = len(idx)
        if n == 0 or total_paytkn <= 0:
            return
        per_m = total_paytkn / n
        self._m.wallet_paytkn[idx] += per_m
        self._m.lifetime[idx]      += per_m * price

    # ─────────────────────────────────────────────────────────────
    # Backward-compatible properties
    # ─────────────────────────────────────────────────────────────

    @property
    def active_users(self) -> list[UserView]:
        """List of UserView proxies for active users (tests + inspection)."""
        return [UserView(self._u, int(i)) for i in self._u_idx]

    @property
    def active_merchants(self) -> list[MerchantView]:
        """List of MerchantView proxies for active merchants."""
        return [MerchantView(self._m, int(i)) for i in self._m_idx]

    @property
    def active_lp_providers(self) -> list[LiquidityProvider]:
        return [lp for lp in self.lp_providers if lp.active]

    @property
    def users(self) -> list[UserView]:
        """All users ever spawned (for test_unique_user_ids)."""
        return [UserView(self._u, i) for i in range(self._u._next)]

    @property
    def merchants(self) -> list[MerchantView]:
        return [MerchantView(self._m, i) for i in range(self._m._next)]

    @property
    def n_active_users(self) -> int:
        return len(self._u_idx)

    @property
    def n_active_merchants(self) -> int:
        return len(self._m_idx)

    @property
    def loyalty_avg(self) -> float:
        idx = self._u_idx
        return float(self._u.loyalty[idx].mean()) if len(idx) > 0 else 1.0

    @property
    def user_stable_total(self) -> float:
        """Total stable USD held across all active user wallets."""
        idx = self._u_idx
        return float(self._u.wallet[idx].sum()) if len(idx) > 0 else 0.0

    @property
    def user_staked_total_paytkn(self) -> float:
        """Total PAYTKN staked by all active users."""
        idx = self._u_idx
        return float(self._u.staked[idx].sum()) if len(idx) > 0 else 0.0

    @property
    def merchant_stable_total(self) -> float:
        """Total stable USD held by all active merchants."""
        idx = self._m_idx
        return float(self._m.wallet[idx].sum()) if len(idx) > 0 else 0.0

    @property
    def merchant_paytkn_total(self) -> float:
        """Total PAYTKN held + staked by all active merchants."""
        idx = self._m_idx
        if len(idx) == 0:
            return 0.0
        return float((self._m.wallet_paytkn[idx] + self._m.staked[idx]).sum())

    # ─────────────────────────────────────────────────────────────
    # Internal: churn pressure
    # ─────────────────────────────────────────────────────────────

    def _update_all_churn_pressure(
        self,
        actual_apy: float,
        sentiment: float,
        price_ratio: float,
    ) -> None:
        u   = self._u
        idx = self._u_idx
        if len(idx) == 0:
            return

        loyalties  = u.loyalty[idx]
        pressures  = u.pressure[idx]
        price_sens = u.price_sens[idx].astype(np.float64)
        r          = self.rules

        delta = np.zeros(len(idx), dtype=np.float64)

        # Bad conditions → add pressure
        if actual_apy < r.user_min_apy_trigger:
            gap = r.user_min_apy_trigger - actual_apy
            delta += min(0.06, gap / max(1e-9, r.user_min_apy_trigger) * 0.06)

        if sentiment < r.user_bear_sentiment_trigger:
            delta += 0.03 * (r.user_bear_sentiment_trigger - sentiment)

        if price_ratio < r.user_price_crash_trigger:
            delta += price_sens * 0.04 * (1.0 - price_ratio)

        delta[loyalties < 0.3] += 0.02

        # Good conditions → release pressure
        if actual_apy > 0.08:
            delta -= 0.04
        if sentiment > 0.65:
            delta -= 0.03
        if 0.85 <= price_ratio <= 1.15:
            delta -= 0.02
        delta[loyalties > 0.8] -= 0.02

        u.pressure[idx] = np.clip(pressures + delta, 0.0, 1.0)

        # Merchants
        m    = self._m
        midx = self._m_idx
        if len(midx) == 0:
            return

        mp = m.pressure[midx]
        if actual_apy < r.opportunity_cost_rate:
            gap = r.opportunity_cost_rate - actual_apy
            m_delta = min(0.05, gap / max(1e-9, r.opportunity_cost_rate) * 0.05)
            m.pressure[midx] = np.clip(mp + m_delta, 0.0, 1.0)
        else:
            m.pressure[midx] = np.maximum(0.0, mp - 0.03)

    # ─────────────────────────────────────────────────────────────
    # Internal: growth
    # ─────────────────────────────────────────────────────────────

    def _grow_users(self, sentiment: float, growth_mult: float = 1.0) -> int:
        lam   = max(0.1, self.cfg.max_daily_signups * (sentiment ** 2) * growth_mult)
        n_new = min(int(self.rng.poisson(lam)), self.cfg.max_daily_signups * 4)  # allow burst
        n_new = min(n_new, self.USER_CAPACITY - self._u._next)
        if n_new <= 0:
            return 0

        u_profiles = self.rng.choice(len(_USER_NAMES), size=n_new, p=_USER_PROBS)
        avg_pays   = np.array(
            [USER_ARCHETYPES[_USER_NAMES[pi]].avg_payment_amount for pi in u_profiles],
            dtype=np.float64,
        )
        wallets  = np.maximum(10.0, self.rng.exponential(avg_pays * 5.0))
        new_idx  = self._u.spawn_batch(self.rng, n_new, u_profiles, wallets)
        self._u_idx = np.concatenate([self._u_idx, new_idx])
        self._loyalty_sum += float(n_new)
        self._user_counter += n_new
        return n_new

    def _grow_merchants(self, sentiment: float) -> int:
        lam   = max(0.05, self.cfg.max_daily_signups * 0.05 * sentiment)
        n_new = min(int(self.rng.poisson(lam)), self.MERCH_CAPACITY - self._m._next)
        if n_new <= 0:
            return 0

        m_profiles = self.rng.choice(len(_MERCH_NAMES), size=n_new, p=_MERCH_PROBS)
        new_idx    = self._m.spawn_batch(n_new, m_profiles)
        self._m_idx = np.concatenate([self._m_idx, new_idx])
        self._merch_counter += n_new
        return n_new

    def _renormalize_lp_shares(self) -> None:
        """Ensure all active LP lp_share values sum to exactly 1.0."""
        active = [lp for lp in self.lp_providers if lp.active]
        total = sum(lp.lp_share for lp in active)
        if total > 0:
            for lp in active:
                lp.lp_share /= total

    def _grow_lp_providers(self, current_price: float) -> tuple[float, float]:
        """Possibly attract a new LP. Returns (paytkn_added, stable_added)."""
        if self.rng.random() >= 0.05:
            return 0.0, 0.0

        active = [lp for lp in self.lp_providers if lp.active]
        if len(active) >= 50:
            return 0.0, 0.0

        # New LP deposit size: log-normal around $200k in stable terms
        stable_dep = float(self.rng.lognormal(mean=12.2, sigma=0.8))  # ~$200k median
        paytkn_dep = stable_dep / max(0.001, current_price)

        # Compute how much of the pool this LP would represent
        # Approximate pool value using deposit sizes of all existing LPs
        total_existing = sum(
            lp.paytkn_deposited * lp.entry_price + lp.stable_deposited
            for lp in active
        ) or (stable_dep * 20)   # fallback if no existing LPs
        deposit_value = stable_dep * 2
        new_share = deposit_value / (total_existing + deposit_value)
        new_share = float(max(0.005, min(new_share, 0.30)))

        # Scale down existing shares proportionally
        for lp in active:
            lp.lp_share *= (1.0 - new_share)
        self._renormalize_lp_shares()

        # Create and register the new LP
        lp = self._spawn_lp(current_price, paytkn_dep, stable_dep, new_share)
        self.lp_providers.append(lp)
        return paytkn_dep, stable_dep

    # ─────────────────────────────────────────────────────────────
    # Internal: churn
    # ─────────────────────────────────────────────────────────────

    def _churn_users(self) -> int:
        u   = self._u
        idx = self._u_idx
        n   = len(idx)
        if n == 0:
            return 0

        probs  = u.churn_prob[idx].astype(np.float64) * (1.0 + u.pressure[idx] * 3.0)
        rolls  = self.rng.random(n)
        c_mask = rolls < probs

        if not c_mask.any():
            return 0

        c_idx = idx[c_mask]
        self._loyalty_sum -= float(u.loyalty[c_idx].sum())
        u.active[c_idx]    = False
        self._u_idx        = idx[~c_mask]
        return int(c_mask.sum())

    def _churn_merchants(self) -> None:
        m   = self._m
        idx = self._m_idx
        n   = len(idx)
        if n == 0:
            return

        probs  = m.churn_prob[idx].astype(np.float64) * (1.0 + m.pressure[idx] * 2.0)
        rolls  = self.rng.random(n)
        c_mask = rolls < probs

        if not c_mask.any():
            return

        m.active[idx[c_mask]] = False
        self._m_idx = idx[~c_mask]

    # ─────────────────────────────────────────────────────────────
    # Internal: LP spawn
    # ─────────────────────────────────────────────────────────────

    def _spawn_lp_seeded(
        self,
        entry_price: float,
        paytkn_dep: float,
        stable_dep: float,
    ) -> LiquidityProvider:
        """Create an initial LP that already owns part of the seeded pool."""
        self._lp_counter += 1
        n_lps = max(1, self.cfg.initial_lp_providers)
        return LiquidityProvider(
            lp_id=f"lp{self._lp_counter}",
            entry_price=max(0.001, entry_price),
            paytkn_deposited=paytkn_dep,
            stable_deposited=stable_dep,
            lp_share=1.0 / n_lps,       # equal shares at genesis
        )

    def _spawn_lp(
        self,
        entry_price: float,
        paytkn_dep: float,
        stable_dep: float,
        lp_share: float,
    ) -> LiquidityProvider:
        """Create a new LP that is joining an existing pool."""
        self._lp_counter += 1
        return LiquidityProvider(
            lp_id=f"lp{self._lp_counter}",
            entry_price=max(0.001, entry_price),
            paytkn_deposited=paytkn_dep,
            stable_deposited=stable_dep,
            lp_share=lp_share,
        )
