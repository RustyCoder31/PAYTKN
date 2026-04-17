"""User and Merchant entities with persistent state and daily decision logic.

Each entity lives for the duration of an episode. State accumulates across days.
Anti-gaming rules from Sheet 7 are enforced here, not by the RL agent.
"""

from __future__ import annotations
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
    wallet_balance: float

    # --- persistent state ---
    wallet: float = field(init=False)
    staked: float = field(init=False, default=0.0)
    loyalty_score: float = field(init=False, default=1.0)
    active: bool = field(init=False, default=True)

    # --- weekly cancel tracking (Sheet 7) ---
    _cancels_this_week: int = field(init=False, default=0)

    # --- invite tree ---
    invite_depth: int = field(init=False, default=0)   # depth in the invite tree
    invitees: list[str] = field(init=False, default_factory=list)

    # --- activity history (for loyalty & retention) ---
    days_active: int = field(init=False, default=0)
    lifetime_payments: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self.wallet = self.wallet_balance

    # ── Sheet-7 guard methods ─────────────────────────────────

    def can_cancel(self, rules: AntiGamingRules) -> bool:
        return self._cancels_this_week < rules.cancel_limit_per_week

    def can_invite(self, rules: AntiGamingRules) -> bool:
        return self.invite_depth < rules.invite_depth_max

    def apply_cancel(self, rules: AntiGamingRules) -> None:
        """Record a cancel and apply loyalty decay."""
        if not self.can_cancel(rules):
            return
        self._cancels_this_week += 1
        self.loyalty_score *= (1.0 - rules.loyalty_decay_per_cancel)
        self.loyalty_score = max(0.0, self.loyalty_score)

    def weekly_reset(self) -> None:
        """Call once per 7 days to reset weekly cancel counter."""
        self._cancels_this_week = 0

    # ── Daily decision ────────────────────────────────────────

    def decide_day_actions(
        self,
        rng: np.random.Generator,
        sentiment: float,
        price: float,
        staking_apy: float,
        rules: AntiGamingRules,
        merchants: list[Merchant],
    ) -> list[Action]:
        """Generate today's actions based on profile + market conditions."""
        if not self.active:
            return []

        # Dormant check: recurring_factor gates whether entity does anything today
        if rng.random() > self.profile.recurring_factor:
            return []

        self.days_active += 1
        actions: list[Action] = []
        p = self.profile

        # ── Price sensitivity modulates sell/buy ─────────────
        sell_boost = p.price_sensitivity * max(0.0, 1.0 - price)   # sell more when price drops
        buy_boost = p.price_sensitivity * max(0.0, price - 1.0)     # buy more when rising

        # ── APY sensitivity modulates staking ────────────────
        stake_boost = p.reward_sensitivity * staking_apy

        # ── Sentiment modulates overall activity ─────────────
        activity_scale = 0.5 + sentiment  # 0.5..1.5 multiplier

        # PAYMENT
        if self.wallet > 5.0 and merchants:
            prob = min(1.0, p.payment_prob * activity_scale * self.loyalty_score)
            if rng.random() < prob:
                merchant = merchants[rng.integers(len(merchants))]
                amount = float(rng.normal(p.avg_payment_amount, p.avg_payment_amount * 0.2))
                amount = max(1.0, min(amount, self.wallet))
                actions.append(Action(
                    actor_id=self.user_id, kind=ActionKind.PAYMENT,
                    amount=amount, target_id=merchant.merchant_id,
                ))
                self.wallet -= amount
                self.lifetime_payments += amount

        # STAKE
        if self.wallet > 10.0:
            prob = min(1.0, (p.stake_prob + stake_boost) * activity_scale)
            if rng.random() < prob:
                amount = float(rng.normal(p.avg_stake_amount, p.avg_stake_amount * 0.3))
                amount = max(1.0, min(amount, self.wallet))
                actions.append(Action(
                    actor_id=self.user_id, kind=ActionKind.STAKE, amount=amount,
                ))
                self.wallet -= amount
                self.staked += amount

        # UNSTAKE
        if self.staked > 0.0:
            prob = min(1.0, p.unstake_prob * (1.0 + sell_boost))
            if rng.random() < prob:
                amount = self.staked * float(rng.uniform(0.1, 0.5))
                actions.append(Action(
                    actor_id=self.user_id, kind=ActionKind.UNSTAKE, amount=amount,
                ))
                self.staked -= amount
                self.wallet += amount

        # BUY (uses stablecoins — represented as a negative-balance action economy handles)
        buy_prob = min(1.0, p.trade_prob * (0.5 + buy_boost))
        if rng.random() < buy_prob:
            stable_amount = float(rng.normal(p.avg_trade_amount * 0.5, p.avg_trade_amount * 0.1))
            stable_amount = max(1.0, stable_amount)
            actions.append(Action(
                actor_id=self.user_id, kind=ActionKind.BUY, amount=stable_amount,
            ))

        # SELL
        if self.wallet > 5.0:
            sell_prob = min(1.0, p.trade_prob * (0.5 + sell_boost))
            if rng.random() < sell_prob:
                amount = self.wallet * float(rng.uniform(0.05, 0.30))
                actions.append(Action(
                    actor_id=self.user_id, kind=ActionKind.SELL, amount=amount,
                ))
                self.wallet -= amount

        # INVITE
        if self.can_invite(rules):
            prob = min(1.0, p.invite_prob * activity_scale * self.loyalty_score)
            if rng.random() < prob:
                actions.append(Action(
                    actor_id=self.user_id, kind=ActionKind.INVITE,
                ))

        # CANCEL
        if self.can_cancel(rules) and rng.random() < p.cancel_prob:
            self.apply_cancel(rules)
            actions.append(Action(actor_id=self.user_id, kind=ActionKind.CANCEL))

        return actions

    def receive_reward(self, amount: float) -> None:
        self.wallet += amount

    def churn(self) -> None:
        self.active = False


# ─────────────────────────────────────────────────────────────
# Merchant
# ─────────────────────────────────────────────────────────────

@dataclass
class Merchant:
    merchant_id: str
    profile: MerchantProfile

    # --- persistent state ---
    wallet: float = field(init=False, default=0.0)
    staked: float = field(init=False, default=0.0)
    active: bool = field(init=False, default=True)

    # --- loan state ---
    loan_outstanding: float = field(init=False, default=0.0)   # in stablecoins

    # --- metrics ---
    lifetime_volume: float = field(init=False, default=0.0)

    # --- weekly wallet-link tracking (Sheet 7) ---
    _wallet_links_this_week: int = field(init=False, default=0)

    def receive_payment(self, amount: float) -> None:
        self.wallet += amount
        self.lifetime_volume += amount

    def stake(self, amount: float) -> None:
        """Move tokens from merchant wallet → staking pool."""
        amount = min(amount, self.wallet)
        self.wallet -= amount
        self.staked += amount

    def max_borrow(self, rules: AntiGamingRules, price: float) -> float:
        """Max loan size in stablecoins = staked_value / collateral_ratio."""
        staked_value = self.staked * price
        return staked_value / rules.collateral_ratio

    def decide_day_actions(
        self,
        rng: np.random.Generator,
        sentiment: float,
        price: float,
        staking_apy: float,
        rules: AntiGamingRules,
    ) -> list[Action]:
        """Generate today's merchant actions."""
        if not self.active:
            return []

        actions: list[Action] = []
        p = self.profile

        # Auto-stake fraction of wallet
        if self.wallet > 10.0:
            stake_amount = self.wallet * p.stake_rate
            if stake_amount > 1.0:
                self.stake(stake_amount)
                actions.append(Action(
                    actor_id=self.merchant_id, kind=ActionKind.STAKE, amount=stake_amount,
                ))

        # Loan request
        if (self.loan_outstanding == 0.0 and
                rng.random() < p.loan_prob * (0.5 + sentiment)):
            base_loan = 1000.0  # base loan in stablecoins
            requested = base_loan * p.loan_size_factor
            cap = self.max_borrow(rules, price)
            loan_amount = min(requested, cap)
            if loan_amount > 10.0:
                actions.append(Action(
                    actor_id=self.merchant_id, kind=ActionKind.LOAN_TAKE, amount=loan_amount,
                ))
                self.loan_outstanding = loan_amount

        # Loan repayment (simple: 10% of outstanding per day if wallet allows)
        if self.loan_outstanding > 0.0 and self.wallet > 50.0:
            repay = min(self.loan_outstanding * 0.10, self.wallet * 0.20)
            if repay > 1.0:
                actions.append(Action(
                    actor_id=self.merchant_id, kind=ActionKind.LOAN_REPAY, amount=repay,
                ))
                self.loan_outstanding -= repay

        return actions

    def weekly_reset(self) -> None:
        self._wallet_links_this_week = 0

    def churn(self) -> None:
        self.active = False
