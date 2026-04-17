"""Economy — global token state, AMM, and action handlers.

One Economy instance lives per episode. It processes every action produced by
entities and applies the RL agent's lever settings each day.

Price discovery: constant-product AMM (x * y = k).
Fee routing: TX tax split → burn / team / treasury / reward pool.
Treasury: issues merchant loans (150% collateral), staking rewards, buybacks.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

from chainenv.config import SimConfig, AntiGamingRules


@dataclass
class EconomyMetrics:
    """Daily snapshot collected for observation and logging."""
    day: int = 0
    price: float = 1.0
    total_supply: float = 0.0
    total_staked: float = 0.0
    treasury_paytkn: float = 0.0
    treasury_stable: float = 0.0
    daily_tx_volume: float = 0.0
    daily_burn: float = 0.0
    daily_mint: float = 0.0
    daily_fees_collected: float = 0.0
    daily_rewards_paid: float = 0.0
    active_users: int = 0
    active_merchants: int = 0


class Economy:
    """Manages all global state and processes entity actions."""

    def __init__(self, cfg: SimConfig) -> None:
        self.cfg = cfg
        self.rules: AntiGamingRules = cfg.rules

        # --- AMM pool (constant product) ---
        self._lp_paytkn: float = cfg.initial_lp_paytkn
        self._lp_stable: float = cfg.initial_lp_stable

        # --- Token supply ---
        self.total_supply: float = cfg.initial_supply
        self._total_staked: float = 0.0

        # --- Treasury ---
        self.treasury_paytkn: float = cfg.initial_treasury_paytkn
        self.treasury_stable: float = cfg.initial_treasury_stable

        # --- Reward pool (funded by minting) ---
        self._reward_pool: float = 0.0

        # --- RL agent lever state (defaults = midpoint of bounds) ---
        self.current_mint_rate: float = 0.01
        self.current_burn_pct: float = 0.005
        self.current_staking_apy: float = 0.08
        self.current_treasury_ratio: float = 0.75
        self.current_reward_alloc: float = 0.25

        # --- Daily accumulators (reset each day) ---
        self._daily_tx_volume: float = 0.0
        self._daily_burn: float = 0.0
        self._daily_mint: float = 0.0
        self._daily_fees_collected: float = 0.0
        self._daily_rewards_paid: float = 0.0

        # --- Outstanding merchant loans {merchant_id: stable_amount} ---
        self._loans: dict[str, float] = {}

        # --- Day counter ---
        self._day: int = 0

    # ─────────────────────────────────────────────────────────
    # Properties
    # ─────────────────────────────────────────────────────────

    @property
    def price(self) -> float:
        """Current PAYTKN price derived from AMM ratio."""
        if self._lp_paytkn == 0:
            return 0.0
        return self._lp_stable / self._lp_paytkn

    @property
    def total_staked(self) -> float:
        return self._total_staked

    # ─────────────────────────────────────────────────────────
    # AMM — constant product x * y = k
    # ─────────────────────────────────────────────────────────

    def execute_buy(self, actor_id: str, stable_amount: float) -> float:
        """Buy PAYTKN with stablecoins. Returns PAYTKN received."""
        stable_amount = max(0.0, stable_amount)
        k = self._lp_paytkn * self._lp_stable
        self._lp_stable += stable_amount
        new_paytkn = k / self._lp_stable
        out = self._lp_paytkn - new_paytkn
        self._lp_paytkn = new_paytkn
        self._daily_tx_volume += stable_amount
        return max(0.0, out)

    def execute_sell(self, actor_id: str, paytkn_amount: float) -> float:
        """Sell PAYTKN for stablecoins. Returns stablecoins received."""
        paytkn_amount = max(0.0, paytkn_amount)
        k = self._lp_paytkn * self._lp_stable
        self._lp_paytkn += paytkn_amount
        new_stable = k / self._lp_paytkn
        out = self._lp_stable - new_stable
        self._lp_stable = new_stable
        self._daily_tx_volume += paytkn_amount * self.price
        return max(0.0, out)

    # ─────────────────────────────────────────────────────────
    # Payment processing (TX tax split)
    # ─────────────────────────────────────────────────────────

    def process_payment(self, payer_id: str, merchant_id: str, amount: float) -> float:
        """Process a user→merchant payment. Returns net amount after TX tax.

        TX tax split:
          - burn_pct  → burned (supply decreases)
          - team_share → team allocation (treasury_stable)
          - remainder → treasury_paytkn
          - reward_alloc fraction of remainder → reward pool
        """
        amount = max(0.0, amount)
        burn_amount = amount * self.current_burn_pct
        fee_amount = amount * 0.005   # 0.5% TX fee on top
        net = amount - burn_amount - fee_amount

        # Burn
        self._burn(burn_amount)

        # Fee routing
        team_share = fee_amount * self.cfg.team_fee_share
        remainder = fee_amount - team_share

        # Reward pool fraction
        to_reward = remainder * self.current_reward_alloc
        to_treasury = remainder - to_reward

        self.treasury_stable += team_share + to_treasury
        self._reward_pool += to_reward

        self._daily_tx_volume += amount
        self._daily_fees_collected += fee_amount

        return net

    # ─────────────────────────────────────────────────────────
    # Staking
    # ─────────────────────────────────────────────────────────

    def record_stake(self, amount: float) -> None:
        self._total_staked += amount

    def record_unstake(self, amount: float) -> None:
        self._total_staked = max(0.0, self._total_staked - amount)

    def distribute_staking_rewards(self, staking_apy: float, epoch_days: int = 1) -> float:
        """Pay out pro-rata staking rewards from reward pool and treasury.

        Returns total rewards distributed.
        """
        if self._total_staked == 0:
            return 0.0

        daily_rate = staking_apy / 365.0
        total_reward = self._total_staked * daily_rate * epoch_days

        # Draw from reward pool first, then treasury as backstop
        from_pool = min(total_reward, self._reward_pool)
        from_treasury = max(0.0, total_reward - from_pool)
        from_treasury = min(from_treasury, self.treasury_paytkn * 0.01)  # cap at 1% treasury/day

        self._reward_pool -= from_pool
        self.treasury_paytkn -= from_treasury
        actual = from_pool + from_treasury

        self._daily_rewards_paid += actual
        return actual

    # ─────────────────────────────────────────────────────────
    # Merchant loans (150% overcollateral)
    # ─────────────────────────────────────────────────────────

    def process_loan_take(
        self, merchant_id: str, amount: float,
        merchant_staked: float, price: float,
    ) -> float:
        """Issue a collateralized loan from treasury. Returns amount approved."""
        max_loan = (merchant_staked * price) / self.rules.collateral_ratio
        approved = min(amount, max_loan, self.treasury_stable * 0.05)
        if approved < 1.0:
            return 0.0
        self.treasury_stable -= approved
        self._loans[merchant_id] = self._loans.get(merchant_id, 0.0) + approved
        return approved

    def process_loan_repay(self, merchant_id: str, amount: float) -> None:
        """Receive loan repayment back into treasury."""
        outstanding = self._loans.get(merchant_id, 0.0)
        repaid = min(amount, outstanding)
        self._loans[merchant_id] = outstanding - repaid
        self.treasury_stable += repaid

    def liquidate_loan(self, merchant_id: str, collateral_paytkn: float) -> float:
        """Liquidate a defaulted merchant loan. Returns collateral burned."""
        outstanding = self._loans.pop(merchant_id, 0.0)
        if outstanding == 0.0:
            return 0.0
        # Collateral covers debt; excess burned for deflationary pressure
        recovered_value = collateral_paytkn * self.price
        surplus_paytkn = max(0.0, (recovered_value - outstanding) / self.price)
        self._burn(surplus_paytkn)
        return surplus_paytkn

    # ─────────────────────────────────────────────────────────
    # Minting (controlled by RL agent via mint_rate)
    # ─────────────────────────────────────────────────────────

    def execute_daily_mint(self) -> float:
        """Mint new tokens according to current agent mint_rate.

        mint_rate is applied daily to circulating supply.
        Minted tokens split: reward_alloc → reward pool, rest → treasury.
        """
        mint_amount = self.total_supply * self.current_mint_rate
        self.total_supply += mint_amount

        to_reward = mint_amount * self.current_reward_alloc
        to_treasury = mint_amount - to_reward

        self._reward_pool += to_reward
        self.treasury_paytkn += to_treasury

        self._daily_mint += mint_amount
        return mint_amount

    # ─────────────────────────────────────────────────────────
    # Treasury rebalancing (buyback & burn)
    # ─────────────────────────────────────────────────────────

    def rebalance_treasury(self) -> None:
        """Buy back PAYTKN using treasury stables if price is below target.

        Uses target treasury_ratio to decide how much stable to redeploy.
        """
        current_paytkn_value = self.treasury_paytkn * self.price
        total_treasury = current_paytkn_value + self.treasury_stable

        if total_treasury == 0:
            return

        current_ratio = current_paytkn_value / total_treasury
        target_ratio = self.current_treasury_ratio

        if current_ratio < target_ratio:
            # Buy PAYTKN to rebalance
            stable_to_spend = (target_ratio - current_ratio) * total_treasury * 0.1
            stable_to_spend = min(stable_to_spend, self.treasury_stable * 0.05)
            if stable_to_spend > 1.0:
                acquired = self.execute_buy("treasury", stable_to_spend)
                self.treasury_stable -= stable_to_spend
                self.treasury_paytkn += acquired
        elif current_ratio > target_ratio + 0.1:
            # Burn excess PAYTKN to reduce inflation pressure
            excess = (current_ratio - target_ratio) * self.treasury_paytkn * 0.05
            if excess > 1.0:
                self._burn(excess)
                self.treasury_paytkn -= excess

    def _burn(self, amount: float) -> None:
        amount = max(0.0, amount)
        self.total_supply = max(0.0, self.total_supply - amount)
        self._daily_burn += amount

    # ─────────────────────────────────────────────────────────
    # RL agent interface
    # ─────────────────────────────────────────────────────────

    def apply_agent_levers(
        self,
        mint_rate: float,
        burn_pct: float,
        staking_apy: float,
        treasury_ratio: float,
        reward_alloc: float,
    ) -> None:
        """Update economy parameters from agent's mapped action values."""
        self.current_mint_rate = mint_rate
        self.current_burn_pct = burn_pct
        self.current_staking_apy = staking_apy
        self.current_treasury_ratio = treasury_ratio
        self.current_reward_alloc = reward_alloc

    # ─────────────────────────────────────────────────────────
    # Day lifecycle
    # ─────────────────────────────────────────────────────────

    def begin_day(self) -> None:
        """Reset daily accumulators at the start of each day."""
        self._day += 1
        self._daily_tx_volume = 0.0
        self._daily_burn = 0.0
        self._daily_mint = 0.0
        self._daily_fees_collected = 0.0
        self._daily_rewards_paid = 0.0

    def end_day(self, active_users: int, active_merchants: int) -> EconomyMetrics:
        """Finalise daily operations and return metrics snapshot."""
        self.execute_daily_mint()
        self.distribute_staking_rewards(self.current_staking_apy, epoch_days=1)
        self.rebalance_treasury()

        return EconomyMetrics(
            day=self._day,
            price=self.price,
            total_supply=self.total_supply,
            total_staked=self._total_staked,
            treasury_paytkn=self.treasury_paytkn,
            treasury_stable=self.treasury_stable,
            daily_tx_volume=self._daily_tx_volume,
            daily_burn=self._daily_burn,
            daily_mint=self._daily_mint,
            daily_fees_collected=self._daily_fees_collected,
            daily_rewards_paid=self._daily_rewards_paid,
            active_users=active_users,
            active_merchants=active_merchants,
        )
