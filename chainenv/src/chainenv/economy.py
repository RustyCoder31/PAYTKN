"""Economy — global token state, AMM, and action handlers.

v3.1: Payment-utility-first. Diagram-aligned full flow.

Payment round-trip (auto-convert via Jumper/AMM, net price-neutral):
  User stable → [AMM buy, 0.3% LP fee] → PAYTKN
  → Protocol fee (0.5%) split: team (dynamic 5-15%) | merchant_pool | treasury
    (NO burn from fees, NO reward_pool from fees — reward_pool funded by mint only)
    (NO burn from fees — burn is a separate RL-controlled daily action)
  → Per-payment MINT fires (5%/yr cap), split treasury_ratio → treasury / reward_pool
  → Tx Reward Engine cashback → payer (loyalty × staking × seniority × invite)
  → Merchant receives net PAYTKN → holds in wallet_paytkn (sells when they choose)

Tx Reward Engine (from diagram):
  cashback = base_rate × loyalty_mult × staking_mult × seniority_mult × invite_mult
  — All factors observable, RL learns to set base_rate optimally
  — Cashback paid from reward_pool (PAYTKN funded by mint)

Merchant Staking Pool (diagram: separate from user pool):
  Funded by merchant_pool_alloc fraction of tx fees.
  Distributes yield to staked merchants (epoch-based).

APY is EMERGENT: (treasury_paytkn * daily_pct) / total_staked × 365.
  daily_pct set by reward_alloc lever (controls how fast treasury pays stakers).
  Treasury maintains 100-day runway — auto-throttles if depleting too fast.
Per-payment Mint: fires on each payment (not daily), 5%/yr hard cap.
Agent Burn: RL burns treasury PAYTKN at current_burn_rate daily.
Price corridor: treasury defends ±30% around $1.00 target.
Treasury buyback: fires when runway < 100 days (dynamic, not fixed threshold).
Dev fee: 5-15% of protocol fees based on treasury stable health.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
import numpy as np

from chainenv.config import SimConfig, AntiGamingRules

if TYPE_CHECKING:
    from chainenv.entities import LiquidityProvider


@dataclass
class EconomyMetrics:
    """Daily snapshot for observation, reward, and logging."""
    day: int = 0
    price: float = 1.0
    total_supply: float = 0.0
    total_staked: float = 0.0
    treasury_paytkn: float = 0.0
    treasury_stable: float = 0.0
    daily_tx_volume: float = 0.0          # USD payment volume (not speculation)
    daily_payment_count: int = 0
    daily_burn: float = 0.0
    daily_mint: float = 0.0
    daily_fees_collected: float = 0.0     # protocol fees in USD
    daily_rewards_paid: float = 0.0       # user staking rewards (USD equiv)
    daily_cashback_paid: float = 0.0      # cashback to payers (USD)
    daily_merchant_rewards: float = 0.0   # merchant pool yields paid out
    active_users: int = 0
    active_merchants: int = 0
    lp_depth_stable: float = 0.0
    lp_provider_count: int = 0
    avg_il: float = 0.0
    actual_apy: float = 0.0               # emergent user staking APY
    merchant_pool_apy: float = 0.0        # merchant staking pool APY
    daily_fees_to_lps: float = 0.0
    cumulative_rewards_paid: float = 0.0
    cumulative_tx_volume: float = 0.0     # lifetime payment volume
    merchant_staking_pool: float = 0.0    # size of merchant pool (PAYTKN)
    daily_in_app_volume:  float = 0.0    # stable spent on in-app PAYTKN purchases
    daily_dev_fees:       float = 0.0    # team cut (10% of protocol fees, stable)
    # Liquidity metrics
    amm_tvl: float = 0.0              # AMM pool total value (stable + PAYTKN×price)
    lp_paytkn_depth: float = 0.0      # PAYTKN in AMM pool
    user_stable_total: float = 0.0    # sum of all user wallet stable balances
    user_staked_usd: float = 0.0      # sum of all user staked PAYTKN × price
    merchant_stable_total: float = 0.0
    merchant_paytkn_usd: float = 0.0  # merchant PAYTKN holdings × price
    system_tvl: float = 0.0           # full TVL: treasury + AMM + user staked + merchant PAYTKN


class Economy:
    """Manages all global state and processes entity actions."""

    def __init__(self, cfg: SimConfig) -> None:
        self.cfg = cfg
        self.rules: AntiGamingRules = cfg.rules

        # --- AMM pool ($10M raise → 10M PAYTKN + $10M stable) ---
        self._lp_paytkn: float = cfg.initial_lp_paytkn
        self._lp_stable: float = cfg.initial_lp_stable

        # --- Token supply ---
        self.total_supply: float = cfg.initial_supply
        self._total_staked: float = 0.0          # user staking (PAYTKN locked)
        self._merchant_staked: float = 0.0       # merchant staking pool (PAYTKN)

        # --- Treasury (operational reserve, separate from AMM) ---
        self.treasury_stable: float = cfg.initial_treasury_stable

        # --- Reward pools ---
        # Reward pool starts at 0: funded entirely by per-payment mint (5%/yr cap).
        # No genesis seed — pool grows organically as payments flow through the system.
        # Staking rewards come from treasury_paytkn directly (not reward pool).
        # Reward pool is used only for cashback (Tx Reward Engine).
        self._reward_pool: float = 0.0
        self.treasury_paytkn: float = cfg.initial_treasury_paytkn          # 2M PAYTKN
        self._merchant_staking_pool: float = 0.0 # merchant staking yields (stable USD)

        # --- Agent lever state (defaults = midpoints of bounds) ---
        self.current_mint_factor:         float = 1.0     # 1× adaptive rate
        self.current_burn_rate:           float = 0.0015  # 0.15%/day treasury burn
        self.current_reward_alloc:        float = 0.40    # 40% of fees → user reward pool
        self.current_cashback_base_rate:  float = 0.003   # 0.3% base cashback (fees are primary)
        self.current_merchant_pool_alloc: float = 0.12    # 12% of fees → merchant pool
        self.current_treasury_ratio:      float = 0.65

        # --- Daily accumulators ---
        self._daily_tx_volume:          float = 0.0
        self._daily_payment_count:      int   = 0
        self._daily_burn:               float = 0.0
        self._daily_mint:               float = 0.0
        self._daily_fees_collected:     float = 0.0   # USD protocol fees
        self._daily_rewards_paid:       float = 0.0
        self._daily_cashback_paid:      float = 0.0
        self._daily_merchant_rewards:   float = 0.0
        self._daily_fees_to_lps:        float = 0.0
        self._daily_swap_volume:        float = 0.0
        self._daily_in_app_volume:      float = 0.0   # stable spent on in-app PAYTKN purchases
        self._daily_dev_fees:           float = 0.0   # team cut (10% of protocol fees)
        # --- Cumulative ---
        self._cumulative_rewards_paid: float = 0.0
        self._cumulative_tx_volume:    float = 0.0
        self._prev_daily_tx_volume:    float = 0.0    # for adaptive mint (growth signal)
        self._prev_daily_rewards:      float = 0.0    # for treasury buyback runway check

        # --- Day ---
        self._day: int = 0
        self._day_open_price: float = cfg.initial_price   # snapshot at start of each day

    # ─────────────────────────────────────────────────────────
    # Properties
    # ─────────────────────────────────────────────────────────

    @property
    def price(self) -> float:
        if self._lp_paytkn <= 0:
            return 0.0
        return self._lp_stable / self._lp_paytkn

    @property
    def total_staked(self) -> float:
        return self._total_staked

    @property
    def merchant_staked(self) -> float:
        return self._merchant_staked

    @property
    def lp_depth_stable(self) -> float:
        return self._lp_stable

    @property
    def reward_pool(self) -> float:
        return self._reward_pool

    @property
    def merchant_staking_pool(self) -> float:
        return self._merchant_staking_pool

    # ─────────────────────────────────────────────────────────
    # AMM — constant product x * y = k
    # 0.3% LP fee stays in pool (grows k for LPs)
    # ─────────────────────────────────────────────────────────

    def execute_buy(self, actor_id: str, stable_amount: float) -> float:
        """Buy PAYTKN with stable. Returns PAYTKN received (after 0.3% LP fee)."""
        stable_amount = max(0.0, stable_amount)
        if stable_amount < 0.001:
            return 0.0
        lp_fee = stable_amount * self.cfg.lp_fee_rate
        net_stable = stable_amount - lp_fee

        k = self._lp_paytkn * self._lp_stable
        self._lp_stable += net_stable
        new_paytkn = k / self._lp_stable
        out = self._lp_paytkn - new_paytkn
        self._lp_paytkn = new_paytkn

        self._daily_swap_volume += stable_amount
        self._daily_fees_to_lps += lp_fee
        return max(0.0, out)

    def execute_sell(self, actor_id: str, paytkn_amount: float) -> float:
        """Sell PAYTKN for stable. Returns stable received (after 0.3% LP fee)."""
        paytkn_amount = max(0.0, paytkn_amount)
        if paytkn_amount < 0.001:
            return 0.0
        lp_fee_paytkn = paytkn_amount * self.cfg.lp_fee_rate
        net_paytkn = paytkn_amount - lp_fee_paytkn

        price_before = self.price
        k = self._lp_paytkn * self._lp_stable
        self._lp_paytkn += net_paytkn
        new_stable = k / self._lp_paytkn
        out = self._lp_stable - new_stable
        self._lp_stable = new_stable

        lp_fee_usd = lp_fee_paytkn * price_before
        self._daily_swap_volume += paytkn_amount * price_before
        self._daily_fees_to_lps += lp_fee_usd
        return max(0.0, out)

    # ─────────────────────────────────────────────────────────
    # Payment processing — full auto-conversion round-trip
    # ─────────────────────────────────────────────────────────

    def process_payment(
        self,
        payer_id: str,
        merchant_id: str,
        amount_usd: float,
        loyalty_score: float = 1.0,
        staking_boost: float = 0.0,
        seniority_boost: float = 0.0,
        invite_boost: float = 0.0,
    ) -> tuple[float, float]:
        """Full payment round-trip through AMM (Jumper/LI.FI style).

        Returns (paytkn_to_merchant, cashback_usd_to_payer).

        Flow:
          1. User stable → PAYTKN via AMM (0.3% LP fee)
          2. Protocol fee (0.5%): team | reward_pool | merchant_pool | treasury
             NO BURN from fees — burn is a separate RL lever
          3. Tx Reward Engine cashback to payer (loyalty × staking × seniority × invite)
          4. Net PAYTKN → merchant wallet_paytkn (merchant decides when to sell)

        Net price impact ≈ 0 (buy is followed later by merchant selling).
        Net treasury income: ~0.5% of payment USD.
        """
        amount_usd = max(0.0, amount_usd)
        if amount_usd < 0.01:
            return 0.0, 0.0

        # 1. Buy PAYTKN for the payment
        paytkn_received = self.execute_buy(payer_id, amount_usd)
        if paytkn_received <= 0:
            return 0.0, 0.0

        # 2. Protocol fee in PAYTKN
        fee_paytkn = paytkn_received * self.cfg.payment_fee_rate
        net_paytkn = paytkn_received - fee_paytkn

        fee_usd = fee_paytkn * self.price   # USD value of protocol fee

        # --- Dynamic dev fee (5–15% of protocol fee) based on treasury stable health ---
        # Healthy treasury → devs take more (treasury can afford it)
        # Stressed treasury → devs take less, more flows to treasury PAYTKN
        treasury_health_score = min(1.0, self.treasury_stable / max(1.0, self.cfg.initial_treasury_stable))
        dynamic_team_rate = 0.05 + 0.10 * treasury_health_score  # 5% → 15%
        team_cut_usd = fee_usd * dynamic_team_rate
        self._daily_dev_fees += team_cut_usd
        self.treasury_stable += team_cut_usd

        # --- Remaining fees: merchant pool + treasury (NO reward_pool from fees) ---
        # Reward pool is funded by per-payment mint only.
        fee_after_team_paytkn = fee_paytkn * (1.0 - dynamic_team_rate)

        merchant_paytkn_share = fee_after_team_paytkn * self.current_merchant_pool_alloc
        treasury_paytkn_share = fee_after_team_paytkn - merchant_paytkn_share

        # Merchant staking pool → PAYTKN valued at price (USD for APY calc)
        self._merchant_staking_pool += merchant_paytkn_share * self.price
        # Treasury → PAYTKN (grows from fees → used for burn, staking rewards, defence)
        self.treasury_paytkn += treasury_paytkn_share

        net_paytkn = max(0.0, paytkn_received - fee_paytkn)

        # 3. Tx Reward Engine cashback (from diagram: loyalty + staking + seniority + invite)
        cashback_paytkn = self._compute_cashback(
            amount_usd, loyalty_score, staking_boost, seniority_boost, invite_boost
        )

        # 4. Per-payment mint (5%/yr cap, split via treasury_ratio lever)
        # Fires on every completed payment — RL sets mint_factor + treasury_ratio to control.
        self._mint_on_payment(amount_usd)

        # 5. Merchant receives net PAYTKN (holds, will sell when they decide)
        # Accumulators
        self._daily_tx_volume       += amount_usd
        self._daily_payment_count   += 1
        self._daily_fees_collected  += fee_usd
        self._cumulative_tx_volume  += amount_usd
        # _daily_cashback_paid accumulated inside _compute_cashback

        return net_paytkn, cashback_paytkn   # (PAYTKN to merchant, PAYTKN cashback to payer)

    def _compute_cashback(
        self,
        amount_usd: float,
        loyalty_score: float,
        staking_boost: float,
        seniority_boost: float,
        invite_boost: float,
    ) -> float:
        """Tx Reward Engine (from diagram).

        cashback = base × loyalty_mult × (1 + staking_boost + seniority_boost + invite_boost)

        All boosts are capped by AntiGamingRules.
        Hard cap: 5% of payment, limited by reward pool.
        """
        r = self.rules
        loyalty_mult   = 0.3 + 0.7 * float(np.clip(loyalty_score, 0.0, 1.0))
        staking_mult   = 1.0 + float(np.clip(staking_boost,   0.0, r.max_cashback_staking_boost))
        seniority_mult = 1.0 + float(np.clip(seniority_boost, 0.0, r.max_cashback_seniority_boost))
        invite_mult    = 1.0 + float(np.clip(invite_boost,    0.0, r.max_cashback_invite_boost))

        cashback = amount_usd * self.current_cashback_base_rate
        cashback *= loyalty_mult * staking_mult * seniority_mult * invite_mult

        # Hard caps
        max_from_pool = self._reward_pool * self.price * 0.005  # max 0.5% of pool value
        max_abs       = amount_usd * 0.05                       # absolute 5% of payment
        cashback = min(cashback, max_from_pool, max_abs)
        cashback = max(0.0, cashback)

        # Deduct from reward pool — cashback paid in PAYTKN (not stable)
        # Return value is PAYTKN amount; caller adds to user.staked (reward for loyalty)
        cashback_paytkn = cashback / max(0.001, self.price)
        cashback_paytkn = min(cashback_paytkn, self._reward_pool)
        self._reward_pool = max(0.0, self._reward_pool - cashback_paytkn)
        # Update cashback tracker in stable-equivalent for metrics
        self._daily_cashback_paid += cashback_paytkn * self.price
        return cashback_paytkn   # PAYTKN amount

    def _mint_on_payment(self, amount_usd: float) -> float:
        """Per-payment mint — fires when each payment completes.

        Why per-payment (not daily):
          - Ties new supply creation directly to real economic activity
          - More payments = more mint = more rewards = virtuous loop
          - RL mint_factor controls aggressiveness; treasury_ratio controls split

        Hard cap: 5%/year (DAILY_CAP_RATE = 5%/365 ≈ 0.0137%/day).
        Adaptive factors: penalised by inflation, reduced if price is falling.
        Split: treasury_ratio → treasury PAYTKN, rest → reward pool (cashback).
        """
        headroom = max(0.0, self.cfg.max_supply - self.total_supply)
        if headroom <= 0:
            return 0.0

        # Daily cap accumulates across all payments in the day
        DAILY_CAP_RATE = 0.000137   # 5%/365
        daily_cap = self.total_supply * DAILY_CAP_RATE
        remaining_cap = max(0.0, daily_cap - self._daily_mint)
        if remaining_cap <= 0:
            return 0.0

        # Base mint: proportional to payment value in PAYTKN
        payment_paytkn = amount_usd / max(0.001, self.price)
        base_mint = payment_paytkn * 0.05   # 5% of payment PAYTKN value

        # Adaptive factors
        inflation_rate    = max(0.0, self.total_supply / self.cfg.initial_supply - 1.0)
        price_ratio       = self.price / max(0.001, self.cfg.initial_price)
        inflation_penalty = max(0.0, 1.0 - inflation_rate * 20)  # penalise >5% inflation
        price_factor      = float(np.clip(price_ratio, 0.3, 1.0))

        effective_mint = base_mint * self.current_mint_factor * inflation_penalty * price_factor
        effective_mint = min(effective_mint, remaining_cap, headroom)
        if effective_mint <= 0:
            return 0.0

        # Split: treasury_ratio to treasury, rest to reward pool
        to_treasury = effective_mint * self.current_treasury_ratio
        to_rewards  = effective_mint - to_treasury

        self.total_supply      += effective_mint
        self.treasury_paytkn   += to_treasury
        self._reward_pool      += to_rewards
        self._daily_mint       += effective_mint
        return effective_mint

    # ─────────────────────────────────────────────────────────
    # In-app PAYTKN purchase (direct from treasury)
    # ─────────────────────────────────────────────────────────

    def execute_in_app_buy(
        self,
        actor_id: str,
        stable_amount: float,
        actor_current_paytkn: float,
    ) -> float:
        """User buys PAYTKN directly from treasury (in-app, not via AMM).

        Advantages over AMM buy:
          - No LP fee (0.3% saved)
          - No price impact / slippage
          - Treasury stable ↑, treasury PAYTKN ↓

        Anti-concentration: purchase is capped so buyer cannot exceed
        max_wallet_pct_of_supply of total circulating supply.

        Returns PAYTKN received (0 if treasury cannot fill the order).
        """
        stable_amount = max(0.0, stable_amount)
        if stable_amount < 0.01 or self.treasury_paytkn <= 0:
            return 0.0

        # Slight discount vs AMM (saves LP fee, no slippage)
        effective_price = self.price * (1.0 - self.rules.in_app_discount_rate)
        effective_price = max(0.001, effective_price)

        paytkn_out = stable_amount / effective_price

        # Anti-concentration cap: buyer cannot hold > 0.5% of supply
        max_allowed = self.total_supply * self.rules.max_wallet_pct_of_supply
        headroom = max(0.0, max_allowed - actor_current_paytkn)
        paytkn_out = min(paytkn_out, headroom)

        # Treasury must have enough PAYTKN to fill
        paytkn_out = min(paytkn_out, self.treasury_paytkn)

        if paytkn_out < 0.001:
            return 0.0

        # Adjust stable paid to match actual PAYTKN delivered
        stable_paid = paytkn_out * effective_price

        self.treasury_paytkn    -= paytkn_out
        self.treasury_stable    += stable_paid
        self._daily_in_app_volume += stable_paid
        return paytkn_out

    # ─────────────────────────────────────────────────────────
    # LP fee distribution
    # ─────────────────────────────────────────────────────────

    def distribute_lp_fees(self, lp_providers: list[LiquidityProvider]) -> float:
        active = [lp for lp in lp_providers if lp.active]
        if not active or self._daily_fees_to_lps == 0.0:
            return 0.0
        for lp in active:
            lp.accumulated_fees += self._daily_fees_to_lps * lp.lp_share
        return self._daily_fees_to_lps

    # ─────────────────────────────────────────────────────────
    # LP depth maintenance
    # ─────────────────────────────────────────────────────────

    def maintain_lp_depth(self) -> float:
        floor = self.rules.min_lp_depth_stable
        deficit = floor - self._lp_stable
        if deficit <= 0:
            return 0.0
        inject = min(deficit, self.treasury_stable * 0.10)
        if inject < 1.0:
            return 0.0
        self.treasury_stable -= inject
        self._lp_stable += inject
        return inject

    # ─────────────────────────────────────────────────────────
    # IL compensation
    # ─────────────────────────────────────────────────────────

    def compensate_il(
        self,
        lp_providers: list[LiquidityProvider],
        current_price: float,
    ) -> float:
        total_paid = 0.0
        for lp in lp_providers:
            if not lp.active:
                continue
            il_frac = lp.compute_il(current_price)
            covered = min(il_frac, self.rules.il_protection_threshold)
            if covered <= 0:
                continue
            comp = covered * lp.total_deposited_value
            comp = min(comp, self.treasury_stable * 0.002)
            if comp < 0.01:
                continue
            self.treasury_stable -= comp
            total_paid += comp
        return total_paid

    # ─────────────────────────────────────────────────────────
    # Staking
    # ─────────────────────────────────────────────────────────

    def record_stake(self, paytkn_amount: float) -> None:
        self._total_staked += paytkn_amount

    def record_unstake(self, paytkn_amount: float) -> None:
        self._total_staked = max(0.0, self._total_staked - paytkn_amount)

    def record_merchant_stake(self, paytkn_amount: float) -> None:
        self._merchant_staked += paytkn_amount

    def record_merchant_unstake(self, paytkn_amount: float) -> None:
        self._merchant_staked = max(0.0, self._merchant_staked - paytkn_amount)

    def distribute_staking_rewards(self) -> float:
        """Distribute user staking rewards directly from treasury PAYTKN. APY is EMERGENT.

        v3.1 design: Treasury pays stakers (not the reward pool).
          - reward_alloc lever controls daily payout rate from treasury
          - reward_alloc [0.20, 0.60] maps to daily_pct [0.04%, 0.12%] of treasury_paytkn
          - Hard cap: treasury must maintain ≥ 100-day runway of rewards
            → max_daily = treasury_paytkn / 100

        actual_apy = (daily_reward / total_staked) × 365
        Returns actual APY for the day.
        """
        if self._total_staked == 0:
            return self.rules.min_staking_apy

        # daily_pct controlled by reward_alloc lever
        # reward_alloc range: [0.20, 0.60] → daily_pct range: [0.0004, 0.0012]
        daily_pct = 0.0004 + (self.current_reward_alloc - 0.20) / 0.40 * 0.0008
        total_daily = self.treasury_paytkn * daily_pct

        # Hard cap: 100-day treasury runway — treasury never depletes faster than 1%/day
        max_daily_for_runway = self.treasury_paytkn / 100.0
        total_daily = min(total_daily, max_daily_for_runway)
        total_daily = max(0.0, total_daily)

        self.treasury_paytkn = max(0.0, self.treasury_paytkn - total_daily)
        self._daily_rewards_paid      += total_daily
        self._cumulative_rewards_paid += total_daily

        actual_apy = (total_daily / max(1.0, self._total_staked)) * 365.0
        return max(self.rules.min_staking_apy, actual_apy)

    def distribute_merchant_staking_rewards(self) -> float:
        """Distribute merchant staking pool yields (epoch-based, but simplified to daily).

        Merchant pool = stable USD accumulated from tx fees.
        Distributes proportionally to merchant staked PAYTKN.
        Returns merchant pool APY.
        """
        if self._merchant_staked == 0 or self._merchant_staking_pool == 0:
            return self.rules.merchant_pool_min_apy

        # Daily yield from merchant pool (10%/day bleed of accumulated pool)
        daily_yield = self._merchant_staking_pool * 0.10
        daily_yield = min(daily_yield, self._merchant_staking_pool)
        self._merchant_staking_pool = max(0.0, self._merchant_staking_pool - daily_yield)
        self._daily_merchant_rewards += daily_yield

        merchant_apy = (daily_yield / max(1.0, self._merchant_staked * self.price)) * 365.0
        return max(self.rules.merchant_pool_min_apy, merchant_apy)

    # ─────────────────────────────────────────────────────────
    # Price corridor defence
    # ─────────────────────────────────────────────────────────

    def defend_price_corridor(self) -> None:
        """Treasury defends the PRICE FLOOR only — not the ceiling.

        Rising price = organic adoption = healthy. We never sell PAYTKN to cap it.
        Falling price below floor = danger. We buy PAYTKN with stable to defend.

        Floor: $0.70 (30% below $1.00 target).
        Ceiling: not defended — price discovery runs free above target.
        Treasury stable is preserved for genuine crash defence only.
        """
        target = self.rules.price_target
        lo = target * (1.0 - self.rules.price_band_pct)
        current = self.price

        # Only defend the floor — spend stable to buy PAYTKN when price crashes
        if current < lo and self.treasury_stable > self.rules.treasury_stable_floor:
            deviation = (lo - current) / lo
            spendable = self.treasury_stable - self.rules.treasury_stable_floor
            buy_usd = min(
                deviation * self._lp_stable * 0.03,
                spendable * 0.05,
            )
            if buy_usd > 100:
                acquired = self.execute_buy("treasury", buy_usd)
                self.treasury_stable -= buy_usd
                self.treasury_paytkn += acquired

    # ─────────────────────────────────────────────────────────
    # Treasury price stabilizer — two-sided market maker
    # ─────────────────────────────────────────────────────────

    def stabilize_price(self) -> tuple[float, float]:
        """Treasury acts as a gentle two-sided price stabilizer.

        Mechanism:
          • Price rose > soft_band today  → treasury SELLS small PAYTKN → gets stable back
          • Price fell > soft_band today  → treasury BUYS  small PAYTKN → spends stable

        This dampens daily volatility without pegging the price.
        Price can still move freely over weeks/months — we only smooth sharp single-day swings.

        Treasury actually PROFITS from this rotation (buys low, sells high) so long-term
        treasury total value grows alongside ecosystem health.

        Hard limits enforced at all times:
          • treasury_stable never below treasury_stable_floor ($500k)
          • treasury_paytkn never below stabilizer_paytkn_floor (500k)
          • max 2% of available treasury per intervention
          • absolute cap of $30k equivalent per day

        Returns (stable_spent_buying, paytkn_sold) — both 0 if no action taken.
        """
        r = self.rules
        if self._day_open_price <= 0:
            return 0.0, 0.0

        current         = self.price
        day_change_pct  = (current - self._day_open_price) / self._day_open_price

        stable_spent  = 0.0
        paytkn_sold   = 0.0

        if day_change_pct > r.stabilizer_soft_band:
            # ── Price rising too fast → sell PAYTKN, collect stable ──────────
            # Guard: if treasury PAYTKN is below the min threshold, do NOT sell.
            # Stabilizer becomes buy-only until treasury PAYTKN recovers.
            if self.treasury_paytkn < r.stabilizer_paytkn_min_threshold:
                return 0.0, 0.0

            excess_move = day_change_pct - r.stabilizer_soft_band

            available_paytkn = max(0.0, self.treasury_paytkn - r.stabilizer_paytkn_floor)
            if available_paytkn < 1.0:
                return 0.0, 0.0

            # Intervention size: proportional to excess move, hard-capped
            sell_paytkn = min(
                excess_move * self._lp_paytkn * 0.02,           # % of pool depth
                available_paytkn * r.stabilizer_max_paytkn_pct, # % of available treasury
                r.stabilizer_abs_cap_usd / max(0.001, current), # absolute USD cap
            )

            if sell_paytkn >= 1.0:
                stable_in = self.execute_sell("treasury_stabilizer", sell_paytkn)
                self.treasury_paytkn -= sell_paytkn
                self.treasury_stable += stable_in
                paytkn_sold = sell_paytkn

        elif day_change_pct < -r.stabilizer_soft_band:
            # ── Price falling too fast → buy PAYTKN, spend stable ────────────
            excess_drop = abs(day_change_pct) - r.stabilizer_soft_band

            spendable_stable = max(0.0, self.treasury_stable - r.treasury_stable_floor)
            if spendable_stable < 1.0:
                return 0.0, 0.0

            # Intervention size: proportional to excess drop, hard-capped
            buy_usd = min(
                excess_drop * self._lp_stable * 0.02,            # % of pool depth
                spendable_stable * r.stabilizer_max_stable_pct,  # % of available stable
                r.stabilizer_abs_cap_usd,                        # absolute USD cap
            )

            if buy_usd >= 1.0:
                paytkn_in = self.execute_buy("treasury_stabilizer", buy_usd)
                self.treasury_stable  -= buy_usd
                self.treasury_paytkn  += paytkn_in
                stable_spent = buy_usd

        return stable_spent, paytkn_sold

    # ─────────────────────────────────────────────────────────
    # Treasury buyback — buyer of last resort
    # ─────────────────────────────────────────────────────────

    def execute_treasury_buyback(self) -> float:
        """Treasury buys PAYTKN from AMM when staking reward runway < 100 days.

        v3.1 design: Dynamic runway-based trigger (not fixed PAYTKN threshold).
        "Treasury must always keep ≥ 100 days of current daily staking rewards."

        When treasury_paytkn / avg_daily_rewards < 100:
          → Treasury converts some stable → PAYTKN via AMM (non-inflationary)
          → Urgency scales buy size: longer below threshold = larger intervention

        Distinct from:
          - stabilize_price(): dampens daily ±3% swings (volatility control)
          - defend_price_corridor(): emergency floor at $0.70 (crash defence)

        Returns stable spent (0 if runway is healthy).
        """
        r = self.rules
        current_price = self.price

        # Runway check: days of staking rewards remaining in treasury
        avg_daily_reward = max(1.0, self._prev_daily_rewards)
        runway = self.treasury_paytkn / avg_daily_reward
        if runway >= 100.0:
            return 0.0   # treasury has enough runway — no buyback needed

        # Don't buy if we don't have enough stable above safety floor
        safe_to_spend = self.treasury_stable - r.treasury_stable_floor - r.treasury_buyback_stable_buffer
        if safe_to_spend < 1_000:
            return 0.0

        # Don't buy into a price bubble — wait for price to cool
        if current_price > r.price_target * 2.0:
            return 0.0

        # Size: proportional to urgency (how far below 100-day runway), hard-capped
        urgency = 1.0 - (runway / 100.0)    # 0 at 100 days, 1.0 at 0 days
        buy_usd = min(
            safe_to_spend * r.treasury_buyback_max_pct * (1.0 + urgency),
            r.treasury_buyback_abs_cap,
            safe_to_spend,
        )

        if buy_usd < 100:
            return 0.0

        paytkn_acquired = self.execute_buy("treasury_buyback", buy_usd)
        self.treasury_stable  -= buy_usd
        self.treasury_paytkn  += paytkn_acquired
        return buy_usd

    # ─────────────────────────────────────────────────────────
    # Adaptive Minting (max 3% annual, inflation/price aware)
    # ─────────────────────────────────────────────────────────

    def execute_daily_mint(self) -> float:
        """v3.1: Daily mint is a NO-OP.

        Minting happens per-payment via _mint_on_payment() (called inside process_payment).
        This ties supply creation directly to real economic activity.
        Kept here for backward compatibility; always returns 0.0.
        """
        return 0.0

    def process_payment_batch(
        self,
        total_usd: float,
        n_payments: int,
        avg_loyalty: float = 1.0,
        avg_staking_boost: float = 0.0,
        avg_seniority_boost: float = 0.0,
        avg_invite_boost: float = 0.0,
    ) -> tuple[float, float]:
        """Process a batch of payments as K=20 representative mini-batches.

        Instead of calling process_payment() n_payments times (too slow for 100k),
        split into K representative payments.  K=20 keeps AMM price impact realistic
        while reducing Python call overhead from O(n_payments) → O(20).

        Returns (total_paytkn_to_merchants, total_cashback_paytkn).
        """
        if total_usd <= 0 or n_payments == 0:
            return 0.0, 0.0

        K         = min(n_payments, 20)
        batch_usd = total_usd / K

        total_to_merchants = 0.0
        total_cashback     = 0.0

        for _ in range(K):
            paytkn_m, cashback = self.process_payment(
                payer_id="_batch",
                merchant_id="_batch",
                amount_usd=batch_usd,
                loyalty_score=avg_loyalty,
                staking_boost=avg_staking_boost,
                seniority_boost=avg_seniority_boost,
                invite_boost=avg_invite_boost,
            )
            total_to_merchants += paytkn_m
            total_cashback     += cashback

        # process_payment counted K representative calls, but real tx count is n_payments.
        # Add the difference so _daily_payment_count reflects actual transaction volume.
        self._daily_payment_count += max(0, n_payments - K)

        return total_to_merchants, total_cashback

    # ─────────────────────────────────────────────────────────
    # Agent-controlled burn (separate from payment fees)
    # ─────────────────────────────────────────────────────────

    def execute_agent_burn(self) -> float:
        """RL agent burns PAYTKN accumulated in treasury from fees.

        Treasury PAYTKN builds up daily from the fee routing (treasury_frac of 0.5% fees).
        $2M stable reserve is for operations (price defence, IL) — NOT touched here.

        Rate = current_burn_rate × treasury_paytkn burned per day.
        Effect: permanent supply reduction → deflationary pressure.
        """
        if self.current_burn_rate <= 0 or self.treasury_paytkn <= 0:
            return 0.0
        rate = min(self.current_burn_rate, self.rules.max_burn_rate)
        burn_paytkn = self.treasury_paytkn * rate
        burn_paytkn = min(burn_paytkn, self.treasury_paytkn)
        if burn_paytkn < 0.001:
            return 0.0
        self._burn(burn_paytkn)
        self.treasury_paytkn -= burn_paytkn
        return burn_paytkn

    # ─────────────────────────────────────────────────────────
    # Treasury overflow rebalancer
    # ─────────────────────────────────────────────────────────

    def rebalance_treasury_overflow(self, initial_stable: float) -> float:
        """If treasury PAYTKN exceeds cap, shift 10% of excess to reward pool.

        Prevents the treasury from hoarding — keeps staking rewards flowing
        when the protocol is accumulating more than it needs for burns/defence.

        Cap = treasury_paytkn_cap_ratio × initial_treasury_paytkn (in PAYTKN terms).
        We compare PAYTKN counts, NOT USD values — otherwise price appreciation alone
        triggers constant dumps, flooding the reward pool and inflating APY.

        Example: initial_treasury_paytkn = 2M, cap_ratio = 1.5 → cap = 3M PAYTKN.
        Overflow only fires if fee routing + mint accumulate >3M in the treasury.
        Only shifts PAYTKN to reward pool — stable reserve is never touched here.
        """
        cap_paytkn = self.cfg.initial_treasury_paytkn * self.rules.treasury_paytkn_cap_ratio
        if self.treasury_paytkn <= cap_paytkn:
            return 0.0

        excess_paytkn = self.treasury_paytkn - cap_paytkn
        shift         = excess_paytkn * 0.10      # gradual — 10% of excess only (was 30% USD)
        shift         = min(shift, self.treasury_paytkn - cap_paytkn)   # never go below cap
        if shift < 0.001:
            return 0.0

        self.treasury_paytkn -= shift
        self._reward_pool    += shift
        return shift

    # ─────────────────────────────────────────────────────────
    # Agent levers
    # ─────────────────────────────────────────────────────────

    def apply_agent_levers(
        self,
        mint_factor: float,
        burn_rate: float,
        reward_alloc: float,
        cashback_base_rate: float,
        merchant_pool_alloc: float,
        treasury_ratio: float,
    ) -> None:
        """Update economy parameters. Floors and caps enforced.

        6 levers matching ActionBounds:
          mint_factor          — adaptive mint multiplier
          burn_rate            — daily burn fraction of treasury PAYTKN
          reward_alloc         — fraction of tx fees → user reward pool
          cashback_base_rate   — base payment cashback fraction (capped low — fees are primary)
          merchant_pool_alloc  — fraction of tx fees → merchant staking pool
          treasury_ratio       — target stable fraction in treasury

        LP bonuses removed: LPs earn from 0.3% swap fees naturally.
        Loans removed: not needed at this stage.
        """
        self.current_mint_factor         = float(np.clip(mint_factor, 0.0, 2.0))
        self.current_burn_rate           = float(np.clip(burn_rate, 0.0, self.rules.max_burn_rate))
        self.current_reward_alloc        = float(np.clip(reward_alloc, 0.0, 1.0))
        self.current_cashback_base_rate  = float(np.clip(cashback_base_rate, 0.0, 0.02))  # hard cap 2%
        # Ensure reward + merchant alloc <= 0.90 (team gets 10%)
        max_merchant = max(0.0, 0.90 - self.current_reward_alloc)
        self.current_merchant_pool_alloc = float(np.clip(merchant_pool_alloc, 0.0, max_merchant))
        self.current_treasury_ratio      = float(np.clip(treasury_ratio, 0.0, 1.0))

    # ─────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────

    def _burn(self, amount: float) -> None:
        amount = max(0.0, amount)
        self.total_supply = max(0.0, self.total_supply - amount)
        self._daily_burn  += amount

    # ─────────────────────────────────────────────────────────
    # Day lifecycle
    # ─────────────────────────────────────────────────────────

    def begin_day(self) -> None:
        self._day_open_price           = self.price              # snapshot for stabilizer
        self._prev_daily_tx_volume     = self._daily_tx_volume   # save for adaptive mint
        self._prev_daily_rewards       = self._daily_rewards_paid  # save for buyback runway check
        self._daily_tx_volume          = 0.0
        self._daily_payment_count      = 0
        self._daily_burn               = 0.0
        self._daily_mint               = 0.0
        self._daily_fees_collected     = 0.0
        self._daily_rewards_paid       = 0.0
        self._daily_cashback_paid      = 0.0
        self._daily_merchant_rewards   = 0.0
        self._daily_fees_to_lps        = 0.0
        self._daily_swap_volume        = 0.0
        self._daily_in_app_volume      = 0.0
        self._daily_dev_fees           = 0.0
        self._day                      += 1

    def end_day(
        self,
        active_users: int,
        active_merchants: int,
        lp_providers: list[LiquidityProvider] | None = None,
        user_stable_total: float = 0.0,
        user_staked_usd: float = 0.0,
        merchant_stable_total: float = 0.0,
        merchant_paytkn_usd: float = 0.0,
    ) -> tuple[EconomyMetrics, float]:
        """Finalise day. Returns (EconomyMetrics, actual_apy).

        Order (matches diagram):
          1. Adaptive mint (tops up reward pool)
          2. Agent-controlled burn (from treasury PAYTKN)
          3. Price corridor defence
          4. LP fee distribution (0.3% swap fees — no treasury bonus needed)
          5. LP depth maintenance (treasury auto-inject)
          6. IL compensation
          7. User staking rewards (emergent APY)
          8. Merchant staking pool rewards
        """
        lp_providers = lp_providers or []

        self.execute_daily_mint()
        self.execute_agent_burn()
        self.rebalance_treasury_overflow(self.cfg.initial_treasury_stable)
        self.execute_treasury_buyback()  # buyer-of-last-resort — replenish PAYTKN when depleting
        self.defend_price_corridor()     # emergency floor ($0.70) — large crash defence
        self.stabilize_price()           # daily volatility damper — gentle two-sided rotation
        self.distribute_lp_fees(lp_providers)
        self.maintain_lp_depth()
        # IL compensation removed — AI agent maintains price stability (USP),
        # so IL is negligible. LPs already earn 0.3% swap fees on every trade.
        actual_apy = self.distribute_staking_rewards()
        merchant_apy = self.distribute_merchant_staking_rewards()

        active_lps = [lp for lp in lp_providers if lp.active]
        avg_il = (
            float(np.mean([lp.compute_il(self.price) for lp in active_lps]))
            if active_lps else 0.0
        )

        amm_tvl    = self._lp_stable + self._lp_paytkn * self.price
        system_tvl = (
            self.treasury_stable
            + self.treasury_paytkn * self.price
            + amm_tvl
            + user_staked_usd
            + merchant_paytkn_usd
        )

        metrics = EconomyMetrics(
            day=self._day,
            price=self.price,
            total_supply=self.total_supply,
            total_staked=self._total_staked,
            treasury_paytkn=self.treasury_paytkn,
            treasury_stable=self.treasury_stable,
            daily_tx_volume=self._daily_tx_volume,
            daily_payment_count=self._daily_payment_count,
            daily_burn=self._daily_burn,
            daily_mint=self._daily_mint,
            daily_fees_collected=self._daily_fees_collected,
            daily_rewards_paid=self._daily_rewards_paid,
            daily_cashback_paid=self._daily_cashback_paid,
            daily_merchant_rewards=self._daily_merchant_rewards,
            active_users=active_users,
            active_merchants=active_merchants,
            lp_depth_stable=self._lp_stable,
            lp_provider_count=len(active_lps),
            avg_il=avg_il,
            actual_apy=actual_apy,
            merchant_pool_apy=merchant_apy,
            daily_fees_to_lps=self._daily_fees_to_lps,
            cumulative_rewards_paid=self._cumulative_rewards_paid,
            cumulative_tx_volume=self._cumulative_tx_volume,
            merchant_staking_pool=self._merchant_staking_pool,
            daily_in_app_volume=self._daily_in_app_volume,
            daily_dev_fees=self._daily_dev_fees,
            amm_tvl=amm_tvl,
            lp_paytkn_depth=self._lp_paytkn,
            user_stable_total=user_stable_total,
            user_staked_usd=user_staked_usd,
            merchant_stable_total=merchant_stable_total,
            merchant_paytkn_usd=merchant_paytkn_usd,
            system_tvl=system_tvl,
        )
        return metrics, actual_apy
