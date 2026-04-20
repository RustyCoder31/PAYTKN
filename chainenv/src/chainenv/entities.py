"""User, Merchant, and LiquidityProvider entities — v3.1 payment-utility model.

Diagram-aligned architecture:
  User wallet = STABLE (USD). Payments auto-convert via AMM (economy).
  Staking = user buys PAYTKN from AMM and locks it for Staking Reward Engine.
  Cashback = Tx Reward Engine: loyalty × staking_boost × seniority × invite_tier.

  Merchant = receives PAYTKN from payments, HOLDS it (wallet_paytkn).
    Merchant DECIDES each day whether to sell some PAYTKN (stable need) or hold.
    Merchants can also STAKE PAYTKN → earn from Merchant Staking Pool.

  LP providers = add stable + PAYTKN to AMM, earn 0.3% of every swap + bonus.

Self-sustaining loop:
  More payments → more fees → merchant staking pool grows → more merchant staking
  → less sell pressure → stable price → more user cashback from pool → more payments
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
import numpy as np

from chainenv.profiles import UserProfile, MerchantProfile
from chainenv.config import AntiGamingRules
from chainenv.actions import Action, ActionKind


# ─────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────

@dataclass
class User:
    user_id: str
    profile: UserProfile
    wallet_balance: float           # initial stable (USD) balance

    wallet: float = field(init=False)          # current stable (USD) balance
    staked: float = field(init=False, default=0.0)   # PAYTKN locked in staking
    loyalty_score: float = field(init=False, default=1.0)
    active: bool = field(init=False, default=True)

    churn_pressure: float = field(init=False, default=0.0)

    _cancels_this_week: int = field(init=False, default=0)
    invite_depth: int = field(init=False, default=0)
    invitees: list[str] = field(init=False, default_factory=list)

    days_active: int = field(init=False, default=0)
    lifetime_payments: float = field(init=False, default=0.0)  # USD

    def __post_init__(self) -> None:
        self.wallet = self.wallet_balance

    # ── Pressure-based churn ─────────────────────────────────

    def update_churn_pressure(
        self,
        actual_apy: float,
        sentiment: float,
        price_ratio: float,       # current_price / initial_price
        rules: AntiGamingRules,
    ) -> None:
        p = self.profile
        delta = 0.0

        # Bad conditions → add pressure
        if actual_apy < rules.user_min_apy_trigger:
            gap = rules.user_min_apy_trigger - actual_apy
            delta += min(0.06, gap / rules.user_min_apy_trigger * 0.06)

        if sentiment < rules.user_bear_sentiment_trigger:
            delta += 0.03 * (rules.user_bear_sentiment_trigger - sentiment)

        if price_ratio < rules.user_price_crash_trigger:
            delta += p.price_sensitivity * 0.04 * (1.0 - price_ratio)

        if self.loyalty_score < 0.3:
            delta += 0.02

        # Good conditions → release pressure
        if actual_apy > 0.08:
            delta -= 0.04
        if sentiment > 0.65:
            delta -= 0.03
        if 0.85 <= price_ratio <= 1.15:
            delta -= 0.02
        if self.loyalty_score > 0.8:
            delta -= 0.02

        self.churn_pressure = max(0.0, min(1.0, self.churn_pressure + delta))

    def should_churn(self, rng: np.random.Generator) -> bool:
        if not self.active:
            return False
        effective = self.profile.churn_probability * (1.0 + self.churn_pressure * 3.0)
        return rng.random() < effective

    # ── Sheet-7 guards ────────────────────────────────────────

    def can_cancel(self, rules: AntiGamingRules) -> bool:
        return self._cancels_this_week < rules.cancel_limit_per_week

    def can_invite(self, rules: AntiGamingRules) -> bool:
        return self.invite_depth < rules.invite_depth_max

    def apply_cancel(self, rules: AntiGamingRules) -> None:
        if not self.can_cancel(rules):
            return
        self._cancels_this_week += 1
        self.loyalty_score = max(0.0, self.loyalty_score * (1.0 - rules.loyalty_decay_per_cancel))

    def weekly_reset(self) -> None:
        self._cancels_this_week = 0

    # ── Tx Reward Engine boost signals ───────────────────────

    def staking_boost(self, price: float) -> float:
        """How much the user's staking amplifies their cashback.
        staked_usd up to $5000 → 0.5× boost.
        """
        staked_usd = self.staked * price
        return min(0.50, staked_usd / 10_000)

    def seniority_boost(self) -> float:
        """Time in system → cashback boost (up to 0.30 at 1 year).
        Drives long-term retention.
        """
        return min(0.30, self.days_active / 365 * 0.30)

    def invite_boost(self) -> float:
        """Each invite tier level adds 4% cashback boost (up to 0.20).
        Incentivises referral network growth.
        """
        return min(0.20, self.invite_depth * 0.04)

    # ── Daily decision ────────────────────────────────────────

    def decide_day_actions(
        self,
        rng: np.random.Generator,
        sentiment: float,
        price: float,               # current PAYTKN price
        actual_apy: float,          # emergent APY (not agent-set)
        rules: AntiGamingRules,
        merchants: list[Merchant],
    ) -> list[Action]:
        """Generate today's actions. Wallet is in stable (USD).

        PAYMENT: User pays merchant in USD. Economy handles auto-conversion.
        STAKE:   User buys PAYTKN from AMM using stable, locks it.
        UNSTAKE: User unlocks PAYTKN, sells back to AMM for stable.
        BUY/SELL: Speculative trades (low probability for most archetypes).
        """
        if not self.active:
            return []
        if rng.random() > self.profile.recurring_factor:
            return []

        self.days_active += 1
        actions: list[Action] = []
        p = self.profile

        price_ratio = price  # relative to $1 target (max(0.001,1.0) == 1.0 always)
        sell_boost  = p.price_sensitivity * max(0.0, 1.0 - price_ratio)
        buy_boost   = p.price_sensitivity * max(0.0, price_ratio - 1.0)
        stake_boost = p.reward_sensitivity * min(1.0, actual_apy / 0.10)
        activity_scale = 0.5 + sentiment

        # PAYMENT (primary action — this is a payment utility)
        if self.wallet > 2.0 and merchants:
            prob = min(1.0, p.payment_prob * activity_scale * self.loyalty_score)
            if rng.random() < prob:
                merchant = merchants[rng.integers(len(merchants))]
                amount = float(rng.normal(p.avg_payment_amount, p.avg_payment_amount * 0.25))
                amount = max(1.0, min(amount, self.wallet))
                actions.append(Action(
                    actor_id=self.user_id, kind=ActionKind.PAYMENT,
                    amount=amount, target_id=merchant.merchant_id,
                ))
                self.wallet -= amount
                self.lifetime_payments += amount

        # STAKE (buy PAYTKN from AMM and lock)
        if self.wallet > 20.0:
            prob = min(1.0, (p.stake_prob + stake_boost * 0.1) * activity_scale)
            if rng.random() < prob:
                amount_usd = float(rng.normal(p.avg_stake_amount, p.avg_stake_amount * 0.3))
                amount_usd = max(1.0, min(amount_usd, self.wallet * 0.5))
                actions.append(Action(actor_id=self.user_id, kind=ActionKind.STAKE, amount=amount_usd))
                self.wallet -= amount_usd

        # UNSTAKE (sell PAYTKN back to AMM for stable)
        if self.staked > 0.0:
            unstake_prob = min(1.0, p.unstake_prob * (1.0 + self.churn_pressure + sell_boost))
            if rng.random() < unstake_prob:
                fraction = float(rng.uniform(0.1, 0.4))
                paytkn_amount = self.staked * fraction
                actions.append(Action(actor_id=self.user_id, kind=ActionKind.UNSTAKE, amount=paytkn_amount))
                self.staked -= paytkn_amount

        # SPECULATIVE / STAKING BUY
        # In-app buy probability scales with APY attractiveness:
        #   High APY → users want PAYTKN to stake → prefer in-app (discount, no slippage)
        #   Low APY  → little incentive to hold PAYTKN → fewer in-app buys, less AMM buying too
        # Base 60% in-app share grows up to 90% when APY is very attractive (≥20%).
        # AMM buy kept for price discovery (at least 10% of buys go through AMM).
        if self.wallet > 10.0 and rng.random() < min(1.0, p.trade_prob * (0.3 + buy_boost)):
            trade_usd = max(1.0, float(rng.normal(p.avg_trade_amount * 0.5, p.avg_trade_amount * 0.15)))
            trade_usd = min(trade_usd, self.wallet * 0.3)
            # In-app share: 60% base (saves LP fee + no slippage), scales up to 75% when APY > 15%
            # APY < 5%: 60%, APY at 5%+: linear ramp, APY ≥ 15%: capped at 75%
            inapp_prob = min(0.75, 0.60 + 0.15 * min(1.0, max(0.0, (actual_apy - 0.05) / 0.10)))
            kind = ActionKind.IN_APP_BUY if rng.random() < inapp_prob else ActionKind.BUY
            actions.append(Action(actor_id=self.user_id, kind=kind, amount=trade_usd))

        # SPECULATIVE SELL (tiny probability, higher when price is high)
        if self.staked > 0.0 and rng.random() < min(1.0, p.trade_prob * (0.3 + sell_boost)):
            sell_paytkn = self.staked * float(rng.uniform(0.05, 0.25))
            actions.append(Action(actor_id=self.user_id, kind=ActionKind.SELL, amount=sell_paytkn))

        # INVITE
        if self.can_invite(rules):
            if rng.random() < min(1.0, p.invite_prob * activity_scale * self.loyalty_score):
                actions.append(Action(actor_id=self.user_id, kind=ActionKind.INVITE))

        # CANCEL
        if self.can_cancel(rules) and rng.random() < p.cancel_prob:
            self.apply_cancel(rules)
            actions.append(Action(actor_id=self.user_id, kind=ActionKind.CANCEL))

        return actions

    def receive_cashback(self, amount_usd: float) -> None:
        self.wallet += amount_usd

    def receive_stake_proceeds(self, stable_received: float, paytkn_staked: float) -> None:
        """Called when a STAKE action executes: record PAYTKN acquired."""
        self.staked += paytkn_staked

    def receive_unstake_proceeds(self, stable_received: float) -> None:
        """Called when UNSTAKE executes: add stable back to wallet."""
        self.wallet += stable_received

    def receive_reward(self, amount_stable: float) -> None:
        self.wallet += amount_stable

    def churn(self) -> None:
        self.active = False


# ─────────────────────────────────────────────────────────────
# Merchant
# ─────────────────────────────────────────────────────────────

@dataclass
class Merchant:
    merchant_id: str
    profile: MerchantProfile

    wallet: float = field(init=False, default=0.0)           # stable (USD)
    wallet_paytkn: float = field(init=False, default=0.0)    # free PAYTKN (received from payments)
    staked: float = field(init=False, default=0.0)           # PAYTKN in merchant staking pool
    active: bool = field(init=False, default=True)
    lifetime_volume: float = field(init=False, default=0.0)  # USD equivalent

    churn_pressure: float = field(init=False, default=0.0)
    _wallet_links_this_week: int = field(init=False, default=0)
    days_active: int = field(init=False, default=0)

    def receive_payment_paytkn(self, paytkn_amount: float, price: float) -> None:
        """Merchant receives PAYTKN from a payment.

        Merchant HOLDS this PAYTKN (does not immediately sell).
        Merchant decides each day whether to sell some or stake it.
        USD volume tracked for metrics.
        """
        self.wallet_paytkn += paytkn_amount
        self.lifetime_volume += paytkn_amount * price   # record USD equivalent

    def receive_payment(self, amount_stable: float) -> None:
        """Legacy: receive stable directly. Used for direct USD payments."""
        self.wallet += amount_stable
        self.lifetime_volume += amount_stable

    def stake(self, usd_amount: float) -> None:
        """Merchant uses stable to buy PAYTKN for staking.
        Wallet debit only — AMM buy handled in env._process_merchant_actions.
        """
        usd_amount = min(usd_amount, self.wallet)
        self.wallet -= usd_amount

    def update_churn_pressure(self, actual_apy: float, rules: AntiGamingRules) -> None:
        if actual_apy < rules.opportunity_cost_rate:
            gap = rules.opportunity_cost_rate - actual_apy
            self.churn_pressure += min(0.05, gap / rules.opportunity_cost_rate * 0.05)
        else:
            self.churn_pressure = max(0.0, self.churn_pressure - 0.03)

        if self.lifetime_volume == 0 and self.wallet == 0 and self.wallet_paytkn == 0:
            self.churn_pressure += 0.04

        self.churn_pressure = float(np.clip(self.churn_pressure, 0.0, 1.0))

    def should_churn(self, rng: np.random.Generator) -> bool:
        effective = self.profile.churn_probability * (1.0 + self.churn_pressure * 2.0)
        return rng.random() < effective

    def decide_day_actions(
        self,
        rng: np.random.Generator,
        sentiment: float,
        price: float,
        actual_apy: float,
        rules: AntiGamingRules,
    ) -> list[Action]:
        if not self.active:
            return []
        self.days_active += 1
        actions: list[Action] = []
        p = self.profile
        price_ratio = price / max(0.001, 1.0)

        # SELL PAYTKN holdings (for operational stable needs)
        # Merchants often sell their PAYTKN but not always — they may hold if price is rising.
        if self.wallet_paytkn > 5.0:
            # Base sell probability: merchants need stable for operations
            # Lower sell probability when price is low (don't want to sell cheap)
            # Higher sell probability when price is high (take profits)
            base_sell_prob = 0.60  # most merchants convert frequently
            price_adj = (price_ratio - 1.0) * 0.3   # +0.3 boost if price 100% up, -0.3 if 100% down
            sell_prob = float(np.clip(base_sell_prob + price_adj, 0.1, 0.95))
            if rng.random() < sell_prob:
                # Sell fraction scales DOWN as price rises:
                # At $1 (ratio=1): sell 40–90% as normal
                # At $3 (ratio=3): sell 13–30% (PAYTKN already worth 3× in USD — less urgency)
                # At $5 (ratio=5): sell 8–18% (holding is very valuable at this point)
                # This prevents merchants from dumping all PAYTKN into a rising market
                price_damper = 1.0 / max(1.0, price_ratio)
                lo = max(0.05, 0.40 * price_damper)
                hi = max(lo + 0.05, 0.90 * price_damper)
                fraction = float(rng.uniform(lo, hi))
                sell_amount = self.wallet_paytkn * fraction
                self.wallet_paytkn -= sell_amount
                actions.append(Action(actor_id=self.merchant_id, kind=ActionKind.SELL, amount=sell_amount))

        # STAKE free PAYTKN into merchant staking pool (earn yield)
        if self.wallet_paytkn > 20.0:
            if rng.random() < p.stake_rate:  # profile-defined stake rate
                stake_paytkn = self.wallet_paytkn * p.stake_rate
                self.wallet_paytkn -= stake_paytkn
                actions.append(Action(actor_id=self.merchant_id, kind=ActionKind.MERCHANT_STAKE, amount=stake_paytkn))

        # STAKE from wallet (stable → PAYTKN for merchant pool)
        if self.wallet > 50.0:
            stake_usd = self.wallet * p.stake_rate * 0.5  # moderate wallet staking
            if stake_usd > 5.0:
                self.stake(stake_usd)
                actions.append(Action(actor_id=self.merchant_id, kind=ActionKind.STAKE, amount=stake_usd))

        return actions

    def weekly_reset(self) -> None:
        self._wallet_links_this_week = 0

    def churn(self) -> None:
        self.active = False


# ─────────────────────────────────────────────────────────────
# Liquidity Provider
# ─────────────────────────────────────────────────────────────

@dataclass
class LiquidityProvider:
    """LP entity — provides liquidity to the AMM pool.

    Earns 0.3% of every swap (both legs of each payment = 0.6% per payment)
    plus LP bonus paid by treasury (agent-controlled rate).
    Exposed to IL when price diverges from entry. Treasury covers up to 5%.
    Exits if fee_yield < IL_net + risk_premium, or IL > 15%.
    """
    lp_id: str
    entry_price: float
    paytkn_deposited: float
    stable_deposited: float
    lp_share: float

    accumulated_fees: float = field(init=False, default=0.0)
    il_loss: float = field(init=False, default=0.0)
    active: bool = field(init=False, default=True)
    churn_pressure: float = field(init=False, default=0.0)
    days_in_pool: int = field(init=False, default=0)

    @property
    def total_deposited_value(self) -> float:
        return self.paytkn_deposited * self.entry_price + self.stable_deposited

    def compute_il(self, current_price: float) -> float:
        if self.entry_price <= 0:
            return 0.0
        r = current_price / self.entry_price
        return max(0.0, 1.0 - (2.0 * math.sqrt(r)) / (1.0 + r))

    def update(
        self,
        rng: np.random.Generator,
        current_price: float,
        daily_fee_income: float,
        treasury_covers_il: bool,
        rules: AntiGamingRules,
    ) -> bool:
        self.days_in_pool += 1
        self.il_loss = self.compute_il(current_price)
        self.accumulated_fees += daily_fee_income

        deposit_val = max(1.0, self.total_deposited_value)
        avg_daily_fee = self.accumulated_fees / max(1, self.days_in_pool)
        fee_yield_ann = (avg_daily_fee / deposit_val) * 365.0

        covered_il = min(self.il_loss, rules.il_protection_threshold) if treasury_covers_il else 0.0
        net_il = max(0.0, self.il_loss - covered_il)

        earning_enough = fee_yield_ann >= (net_il + rules.lp_risk_premium)

        if earning_enough:
            self.churn_pressure = max(0.0, self.churn_pressure - 0.03)
        else:
            gap = (net_il + rules.lp_risk_premium) - fee_yield_ann
            self.churn_pressure = min(1.0, self.churn_pressure + gap * 0.4)

        if self.il_loss > 0.15:
            self.active = False
            return False

        if rng.random() < self.churn_pressure * 0.10:
            self.active = False
            return False

        return True

    def churn(self) -> None:
        self.active = False
