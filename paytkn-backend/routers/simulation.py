"""
PAYTKN Full Agent-Based Economy Simulation
============================================
• 100 initial users (6 archetypes) + 20 initial merchants (4 archetypes)
• Each 30-second tick represents ONE simulated day
• AMM constant-product price discovery (x·y = k)
• Proper treasury seeding: 10M PAYTKN + 5M stable
• Population model: sentiment-driven growth, archetype-driven churn
• Anti-gaming rules: cancel limits, loyalty decay, collateral ratios
• RL agent syncs every day to update protocol parameters
"""
from __future__ import annotations

import math
import random
import time
import threading
from dataclasses import dataclass, field
from collections import deque
from fastapi import APIRouter

router = APIRouter(prefix="/simulation", tags=["Simulation"])

# ─────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────

@dataclass
class SimConfig:
    initial_users: int = 100
    initial_merchants: int = 20

    # ── Tokenomics (matching original test setup) ─────────────────
    # 12M initial circulating supply; max 100M mintable over time
    initial_supply: float  = 12_000_000.0
    max_supply:     float  = 100_000_000.0
    initial_price:  float  = 1.0

    # AMM: 5M PAYTKN + 5M stable  → price = $1.00 exactly
    # (10M stables-side depth provided by protocol at launch)
    initial_lp_paytkn: float = 5_000_000.0
    initial_lp_stable: float = 5_000_000.0

    # Treasury: 2M PAYTKN + 2M stable  (lean, realistic bootstrap)
    initial_treasury_paytkn: float = 2_000_000.0
    initial_treasury_stable: float = 2_000_000.0

    # Episode
    episode_days: int = 365

    # Market sentiment
    initial_sentiment: float = 0.55
    sentiment_drift: float = 0.02

    # Population
    max_daily_signups: int = 50
    base_churn_rate: float = 0.005   # 0.5% daily baseline

    team_fee_share: float = 0.10

    # Anti-gaming
    cancel_limit_per_week: int = 3
    loyalty_decay_per_cancel: float = 0.10
    collateral_ratio: float = 1.50

CFG = SimConfig()


# ─────────────────────────────────────────────────────────────────
# USER ARCHETYPES
# ─────────────────────────────────────────────────────────────────

USER_ARCHETYPES = {
    # Wallet ranges scaled to 12M supply (~5M in user wallets total across 100 users)
    "casual": {
        "payment_prob": 0.15, "stake_prob": 0.02, "unstake_prob": 0.01,
        "trade_prob": 0.05, "invite_prob": 0.01, "cancel_prob": 0.03,
        "avg_payment": 30.0, "avg_trade": 80.0, "avg_stake": 40.0,
        "price_sensitivity": 0.4, "reward_sensitivity": 0.3,
        "churn_prob": 0.008, "recurring": 0.5,
        "initial_wallet": (100, 600),
        "initial_stake_pct": 0.05,
        "emoji": "👤", "weight": 0.45,
    },
    "loyal": {
        "payment_prob": 0.40, "stake_prob": 0.08, "unstake_prob": 0.01,
        "trade_prob": 0.02, "invite_prob": 0.05, "cancel_prob": 0.005,
        "avg_payment": 50.0, "avg_trade": 60.0, "avg_stake": 150.0,
        "price_sensitivity": 0.2, "reward_sensitivity": 0.7,
        "churn_prob": 0.002, "recurring": 0.9,
        "initial_wallet": (300, 1500),
        "initial_stake_pct": 0.20,
        "emoji": "💎", "weight": 0.20,
    },
    "whale": {
        "payment_prob": 0.10, "stake_prob": 0.05, "unstake_prob": 0.03,
        "trade_prob": 0.20, "invite_prob": 0.02, "cancel_prob": 0.01,
        "avg_payment": 300.0, "avg_trade": 2000.0, "avg_stake": 5000.0,
        "price_sensitivity": 0.7, "reward_sensitivity": 0.5,
        "churn_prob": 0.003, "recurring": 0.7,
        "initial_wallet": (5000, 40000),
        "initial_stake_pct": 0.40,
        "emoji": "🐋", "weight": 0.03,
    },
    "speculator": {
        "payment_prob": 0.03, "stake_prob": 0.01, "unstake_prob": 0.08,
        "trade_prob": 0.40, "invite_prob": 0.005, "cancel_prob": 0.05,
        "avg_payment": 20.0, "avg_trade": 800.0, "avg_stake": 200.0,
        "price_sensitivity": 0.9, "reward_sensitivity": 0.2,
        "churn_prob": 0.015, "recurring": 0.4,
        "initial_wallet": (500, 3000),
        "initial_stake_pct": 0.05,
        "emoji": "📈", "weight": 0.12,
    },
    "power_user": {
        "payment_prob": 0.50, "stake_prob": 0.10, "unstake_prob": 0.02,
        "trade_prob": 0.10, "invite_prob": 0.15, "cancel_prob": 0.01,
        "avg_payment": 60.0, "avg_trade": 150.0, "avg_stake": 300.0,
        "price_sensitivity": 0.3, "reward_sensitivity": 0.6,
        "churn_prob": 0.003, "recurring": 0.85,
        "initial_wallet": (500, 2500),
        "initial_stake_pct": 0.30,
        "emoji": "⚡", "weight": 0.10,
    },
    "dormant": {
        "payment_prob": 0.02, "stake_prob": 0.005, "unstake_prob": 0.005,
        "trade_prob": 0.01, "invite_prob": 0.001, "cancel_prob": 0.01,
        "avg_payment": 10.0, "avg_trade": 30.0, "avg_stake": 10.0,
        "price_sensitivity": 0.1, "reward_sensitivity": 0.1,
        "churn_prob": 0.020, "recurring": 0.2,
        "initial_wallet": (20, 200),
        "initial_stake_pct": 0.01,
        "emoji": "😴", "weight": 0.10,
    },
}

MERCHANT_ARCHETYPES = {
    "small_retailer": {
        "daily_payments": 5, "avg_received": 40.0,
        "stake_rate": 0.30, "loan_prob": 0.005,
        "churn_prob": 0.010, "weight": 0.55,
        "emoji": "🏪",
    },
    "medium_business": {
        "daily_payments": 25, "avg_received": 60.0,
        "stake_rate": 0.50, "loan_prob": 0.015,
        "churn_prob": 0.005, "weight": 0.30,
        "emoji": "🏢",
    },
    "large_business": {
        "daily_payments": 100, "avg_received": 150.0,
        "stake_rate": 0.60, "loan_prob": 0.025,
        "churn_prob": 0.002, "weight": 0.05,
        "emoji": "🏦",
    },
    "subscription": {
        "daily_payments": 50, "avg_received": 12.0,
        "stake_rate": 0.40, "loan_prob": 0.010,
        "churn_prob": 0.004, "weight": 0.10,
        "emoji": "🔄",
    },
}

_ARCHETYPE_NAMES = list(USER_ARCHETYPES.keys())
_ARCHETYPE_WEIGHTS = [USER_ARCHETYPES[k]["weight"] for k in _ARCHETYPE_NAMES]
_MERCHANT_NAMES = list(MERCHANT_ARCHETYPES.keys())
_MERCHANT_WEIGHTS = [MERCHANT_ARCHETYPES[k]["weight"] for k in _MERCHANT_NAMES]


def _sample_archetype() -> str:
    return random.choices(_ARCHETYPE_NAMES, weights=_ARCHETYPE_WEIGHTS, k=1)[0]


def _sample_merchant_type() -> str:
    return random.choices(_MERCHANT_NAMES, weights=_MERCHANT_WEIGHTS, k=1)[0]


# ─────────────────────────────────────────────────────────────────
# ENTITY CLASSES
# ─────────────────────────────────────────────────────────────────

@dataclass
class User:
    uid: str
    archetype: str
    wallet: float
    staked: float = 0.0
    loyalty: float = 1.0
    active: bool = True
    joined_day: int = 0
    lifetime_txs: int = 0
    lifetime_volume: float = 0.0
    cancels_this_week: int = 0
    day_of_last_cancel_reset: int = 0


@dataclass
class Merchant:
    mid: str
    archetype: str
    name: str
    emoji: str
    wallet: float = 0.0
    staked: float = 0.0
    loan_balance: float = 0.0
    active: bool = True
    joined_day: int = 0
    lifetime_volume: float = 0.0
    tx_count: int = 0


@dataclass
class LiquidityProvider:
    """AMM liquidity provider — deposits PAYTKN + stable, earns 0.3% of every swap."""
    lpid: str
    entry_price: float          # PAYTKN price at deposit time (for IL calc)
    paytkn_deposited: float     # initial PAYTKN deposited
    stable_deposited: float     # initial stable deposited
    lp_share: float             # fraction of pool owned (all active LPs sum to 1.0)
    accumulated_fees_usd: float = 0.0
    days_in_pool: int = 0
    active: bool = True

    def compute_il(self, current_price: float) -> float:
        """Impermanent loss fraction vs holding outside AMM."""
        if self.entry_price <= 0:
            return 0.0
        r = current_price / self.entry_price
        return max(0.0, 1.0 - (2.0 * math.sqrt(r)) / (1.0 + r))

    def fee_apy(self) -> float:
        """Annualised fee return based on average daily fees vs initial deposit value."""
        if self.days_in_pool <= 0:
            return 0.0
        deposit_value = self.paytkn_deposited * self.entry_price + self.stable_deposited
        if deposit_value <= 0:
            return 0.0
        daily_avg = self.accumulated_fees_usd / max(1, self.days_in_pool)
        return (daily_avg / deposit_value) * 365.0


_MERCHANT_NAMES_LIST = [
    "TechMart", "CloudDev", "GameZone", "FoodHub", "EduPro", "FitLife",
    "TravelX", "ShopNow", "MediCare", "AutoDrive", "HomeBase", "EcoStore",
    "StyleHub", "CryptoEx", "DataPro", "BioTech", "FinServe", "LogiCo",
    "SecureNet", "GreenCo",
]


# ─────────────────────────────────────────────────────────────────
# AMM + ECONOMY STATE
# ─────────────────────────────────────────────────────────────────

class Economy:
    def __init__(self):
        # AMM reserves (constant product x·y = k)
        self.lp_paytkn = CFG.initial_lp_paytkn
        self.lp_stable = CFG.initial_lp_stable

        # Supply tracking
        self.circulating_supply = CFG.initial_supply
        self.total_minted = CFG.initial_supply
        self.total_burned = 0.0

        # Treasury — properly seeded
        self.treasury_paytkn = CFG.initial_treasury_paytkn
        self.treasury_stable = CFG.initial_treasury_stable

        # Reward pool — seeded from treasury
        self.reward_pool = CFG.initial_treasury_paytkn * 0.05  # 5% of treasury

        # Aggregate stats
        self.total_staked = 0.0
        self.total_payments = 0
        self.total_volume = 0.0
        self.total_cashback = 0.0

        # Daily counters
        self.daily_tx_count = 0
        self.daily_volume = 0.0
        self.daily_burn = 0.0
        self.daily_mint = 0.0
        self.daily_lp_fees = 0.0          # 0.3% of swap volume accumulated today
        self.daily_swap_volume_usd = 0.0  # total swap volume for LP APY calc

        # Price history
        self.price_history: list[float] = [self.price]

    @property
    def price(self) -> float:
        if self.lp_paytkn <= 0:
            return 0.001
        return self.lp_stable / self.lp_paytkn

    @property
    def treasury_value_usd(self) -> float:
        return self.treasury_paytkn * self.price + self.treasury_stable

    @property
    def market_cap(self) -> float:
        return self.circulating_supply * self.price

    @property
    def staking_ratio(self) -> float:
        if self.circulating_supply <= 0:
            return 0.0
        return self.total_staked / self.circulating_supply

    def price_volatility(self, window: int = 7) -> float:
        if len(self.price_history) < 2:
            return 0.0
        recent = self.price_history[-window:]
        if len(recent) < 2:
            return 0.0
        mean = sum(recent) / len(recent)
        var = sum((p - mean) ** 2 for p in recent) / len(recent)
        return var ** 0.5

    # AMM trades
    def amm_buy(self, stable_in: float) -> float:
        """Spend stable to buy PAYTKN. 0.3% LP fee stays in pool. Returns PAYTKN received."""
        if stable_in <= 0 or self.lp_paytkn <= 0:
            return 0.0
        lp_fee = stable_in * 0.003          # 0.3% fee earned by LPs
        net_stable = stable_in - lp_fee     # only net amount participates in swap
        k = self.lp_paytkn * self.lp_stable
        self.lp_stable += net_stable
        new_paytkn = k / self.lp_stable
        out = self.lp_paytkn - new_paytkn
        self.lp_paytkn = new_paytkn
        self.lp_stable += lp_fee            # fee stays in pool, growing k for LPs
        self.daily_lp_fees += lp_fee
        self.daily_swap_volume_usd += stable_in
        return max(0.0, out)

    def amm_sell(self, paytkn_in: float) -> float:
        """Sell PAYTKN for stable. 0.3% LP fee stays in pool. Returns stable received."""
        if paytkn_in <= 0 or self.lp_stable <= 0:
            return 0.0
        lp_fee_paytkn = paytkn_in * 0.003  # 0.3% fee in PAYTKN terms
        net_paytkn = paytkn_in - lp_fee_paytkn
        price_before = self.lp_stable / max(1, self.lp_paytkn)
        k = self.lp_paytkn * self.lp_stable
        self.lp_paytkn += net_paytkn
        new_stable = k / self.lp_paytkn
        out = self.lp_stable - new_stable
        self.lp_stable = new_stable
        self.lp_paytkn += lp_fee_paytkn    # fee stays in pool
        lp_fee_usd = lp_fee_paytkn * price_before
        self.daily_lp_fees += lp_fee_usd
        self.daily_swap_volume_usd += paytkn_in * price_before
        return max(0.0, out)

    def add_lp_liquidity(self, paytkn: float, stable: float) -> None:
        """Add liquidity to AMM pool (new LP deposit)."""
        self.lp_paytkn += max(0.0, paytkn)
        self.lp_stable  += max(0.0, stable)

    def remove_lp_liquidity(self, lp_share: float) -> tuple[float, float]:
        """Remove LP's proportional share from AMM pool. Returns (paytkn, stable)."""
        lp_share = max(0.0, min(1.0, lp_share))
        paytkn_out = self.lp_paytkn * lp_share
        stable_out  = self.lp_stable  * lp_share
        self.lp_paytkn = max(100_000.0, self.lp_paytkn - paytkn_out)
        self.lp_stable  = max(100_000.0, self.lp_stable  - stable_out)
        return paytkn_out, stable_out

    def mint(self, amount: float) -> None:
        if amount <= 0:
            return
        # Hard cap: never exceed 100M total supply
        headroom = max(0.0, CFG.max_supply - self.circulating_supply)
        amount = min(amount, headroom)
        if amount <= 0:
            return
        self.circulating_supply += amount
        self.total_minted += amount
        self.daily_mint += amount
        # Add proportionally to AMM to not shock price
        ratio = amount / max(self.circulating_supply, 1)
        self.lp_paytkn += amount * 0.1  # small fraction to LP

    def burn(self, amount: float) -> None:
        if amount <= 0:
            return
        actual = min(amount, self.circulating_supply * 0.001)  # cap daily burn
        self.circulating_supply -= actual
        self.total_burned += actual
        self.daily_burn += actual
        # Burn removes from AMM too
        self.lp_paytkn = max(1.0, self.lp_paytkn - actual * 0.05)

    def distribute_rewards(self, daily_apy: float, users: dict, merchants: dict) -> float:
        if self.total_staked <= 0:
            return 0.0
        total_reward = self.total_staked * daily_apy / 365.0
        actual = min(total_reward, self.reward_pool)
        if actual <= 0:
            return 0.0
        self.reward_pool -= actual
        # Mint newly distributed rewards
        self.mint(actual)

        for u in users.values():
            if u.active and u.staked > 0:
                share = (u.staked / self.total_staked) * actual
                u.wallet += share
        for m in merchants.values():
            if m.active and m.staked > 0:
                share = (m.staked / self.total_staked) * actual
                m.wallet += share
        return actual

    def end_of_day(self):
        self.price_history.append(self.price)
        if len(self.price_history) > 400:
            self.price_history.pop(0)
        self.daily_tx_count = 0
        self.daily_volume = 0.0
        self.daily_burn = 0.0
        self.daily_mint = 0.0
        self.daily_lp_fees = 0.0
        self.daily_swap_volume_usd = 0.0


# ─────────────────────────────────────────────────────────────────
# SIMULATION STATE
# ─────────────────────────────────────────────────────────────────

@dataclass
class SimState:
    day: int = 0
    running: bool = False
    sentiment: float = CFG.initial_sentiment
    users: dict = field(default_factory=dict)
    merchants: dict = field(default_factory=dict)
    eco: Economy = field(default_factory=Economy)
    _next_uid: int = 0
    _next_mid: int = 0

    # LP providers — physical owners of AMM liquidity
    lp_providers: list = field(default_factory=list)
    _next_lpid: int = 0

    # Historical records
    price_history: list = field(default_factory=list)
    supply_history: list = field(default_factory=list)
    tx_feed: list = field(default_factory=list)
    daily_stats: list = field(default_factory=list)

    # Aggregate totals
    total_payments: int = 0
    total_volume_usd: float = 0.0
    total_cashback: float = 0.0
    total_burned: float = 0.0
    total_minted: float = 0.0
    total_staking_rewards: float = 0.0

    # RL params
    rl_params: dict = field(default_factory=lambda: {
        "mint_factor": 100,
        "burn_rate_bps": 20,
        "reward_alloc_bps": 3000,
        "cashback_base_bps": 50,
        "merchant_alloc_bps": 1000,
        "treasury_ratio_bps": 6000,
        "staking_apy_pct": 12.0,
    })

    def next_uid(self) -> str:
        self._next_uid += 1
        return f"u{self._next_uid:04d}"

    def next_mid(self) -> str:
        self._next_mid += 1
        return f"m{self._next_mid:04d}"

    def next_lpid(self) -> str:
        self._next_lpid += 1
        return f"lp{self._next_lpid:03d}"


def _build_initial_state() -> SimState:
    st = SimState()
    eco = st.eco

    # Spawn initial users
    for _ in range(CFG.initial_users):
        arch_name = _sample_archetype()
        arch = USER_ARCHETYPES[arch_name]
        uid = st.next_uid()
        wallet_lo, wallet_hi = arch["initial_wallet"]
        wallet = random.uniform(wallet_lo, wallet_hi)
        staked = wallet * arch["initial_stake_pct"]
        wallet -= staked
        u = User(uid=uid, archetype=arch_name, wallet=wallet, staked=staked)
        st.users[uid] = u
        eco.total_staked += staked

    # Spawn initial merchants
    for i in range(CFG.initial_merchants):
        arch_name = _sample_merchant_type()
        arch = MERCHANT_ARCHETYPES[arch_name]
        mid = st.next_mid()
        name = _MERCHANT_NAMES_LIST[i % len(_MERCHANT_NAMES_LIST)]
        m = Merchant(mid=mid, archetype=arch_name, name=name, emoji=arch["emoji"])
        m.wallet = random.uniform(500, 5000)
        st.merchants[mid] = m

    # Spawn initial LP providers — 5 LPs collectively own the 5M/5M AMM pool
    # Each LP gets an equal 20% share at launch price $1.00
    N_INITIAL_LPS = 5
    paytkn_per_lp = CFG.initial_lp_paytkn / N_INITIAL_LPS
    stable_per_lp = CFG.initial_lp_stable / N_INITIAL_LPS
    for i in range(N_INITIAL_LPS):
        lp = LiquidityProvider(
            lpid=f"lp{i+1:03d}",
            entry_price=CFG.initial_price,
            paytkn_deposited=paytkn_per_lp,
            stable_deposited=stable_per_lp,
            lp_share=1.0 / N_INITIAL_LPS,
        )
        st.lp_providers.append(lp)
    st._next_lpid = N_INITIAL_LPS

    # Seed price/supply history with some warm-up noise
    for d in range(15):
        eco.price_history.append(eco.price * random.uniform(0.99, 1.01))
        st.price_history.append({
            "day": -15 + d,
            "price": eco.price_history[-1],
            "ts": "init",
        })
        st.supply_history.append({
            "day": -15 + d,
            "supply": eco.circulating_supply,
        })

    return st


# ─────────────────────────────────────────────────────────────────
# GLOBAL STATE
# ─────────────────────────────────────────────────────────────────

_state: SimState = _build_initial_state()
_thread = None
_lock = threading.Lock()
_event_seq = 0   # monotonic counter → guaranteed unique React keys

_EMOJIS_ARCHETYPE = {k: USER_ARCHETYPES[k]["emoji"] for k in USER_ARCHETYPES}


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

def _push_event(etype: str, desc: str, usd: float, ptk: float, color: str = "blue"):
    global _event_seq
    _event_seq += 1
    evt = {
        "id":  _event_seq,   # monotonic — never collides
        "day": _state.day,
        "type": etype,
        "desc": desc,
        "amount_usd": round(usd, 2),
        "paytkn": round(ptk, 4),
        "color": color,
        "ts":  time.strftime("%H:%M:%S"),
    }
    _state.tx_feed.insert(0, evt)
    if len(_state.tx_feed) > 120:
        _state.tx_feed.pop()


# ─────────────────────────────────────────────────────────────────
# LIQUIDITY PROVIDER ENGINE
# ─────────────────────────────────────────────────────────────────

def _renormalize_lp_shares():
    """Ensure all active LP shares sum to exactly 1.0."""
    active = [lp for lp in _state.lp_providers if lp.active]
    total = sum(lp.lp_share for lp in active)
    if total > 0:
        for lp in active:
            lp.lp_share /= total


def _distribute_lp_fees():
    """Credit today's 0.3% swap fees to LPs by their pool share."""
    total_fees = _state.eco.daily_lp_fees
    if total_fees <= 0:
        return
    active = [lp for lp in _state.lp_providers if lp.active]
    for lp in active:
        lp.accumulated_fees_usd += total_fees * lp.lp_share
        lp.days_in_pool += 1


def _process_lp_day(lp: LiquidityProvider):
    """Daily LP decision: exit if IL too high, add more liquidity if yield is great."""
    if not lp.active:
        return
    eco = _state.eco
    price = eco.price
    il = lp.compute_il(price)
    fee_apy = lp.fee_apy()

    # Exit conditions:
    #   • IL > 12%  — position is losing value faster than fees compensate
    #   • IL > 5%  AND fee APY < 2%  AND has been in pool ≥ 7 days
    exit_il = il > 0.12
    exit_yield = (il > 0.05 and fee_apy < 0.02 and lp.days_in_pool >= 7)

    if exit_il or exit_yield:
        paytkn_out, stable_out = eco.remove_lp_liquidity(lp.lp_share)
        lp.active = False
        _renormalize_lp_shares()
        reason = f"IL {il*100:.1f}%" if exit_il else f"low yield {fee_apy*100:.1f}% APY"
        _push_event(
            "lp_exit",
            f"💧 LP {lp.lpid} withdrew — {reason}  (${stable_out:,.0f} + {paytkn_out:,.0f} PTK)",
            stable_out, paytkn_out, "red",
        )
        return

    # Add-more-liquidity: if fee APY is attractive and sentiment is bullish
    if fee_apy > 0.06 and _state.sentiment > 0.55 and lp.days_in_pool >= 3:
        if random.random() < 0.12:   # 12% chance per day when yield is good
            add_stable = lp.stable_deposited * random.uniform(0.05, 0.15)
            add_paytkn = add_stable / max(0.001, price)
            eco.add_lp_liquidity(add_paytkn, add_stable)
            lp.paytkn_deposited += add_paytkn
            lp.stable_deposited += add_stable
            # LP share increases; renormalize after adding
            pool_value = eco.lp_stable + eco.lp_paytkn * price
            added_value = add_stable * 2
            # Dilute everyone proportionally (shares stay relative, just grows pool)
            # No share change needed — same proportional ownership
            _push_event(
                "lp_add",
                f"💰 LP {lp.lpid} added ${add_stable*2:,.0f} liquidity  (APY {fee_apy*100:.1f}%)",
                add_stable, add_paytkn, "teal",
            )


def _maybe_spawn_lp():
    """New LP joins if fee yield is attractive and market is healthy."""
    if _state.day < 5:
        return
    active = [lp for lp in _state.lp_providers if lp.active]
    if len(active) >= 20:
        return  # pool is already crowded

    avg_fee_apy = (
        sum(lp.fee_apy() for lp in active) / len(active) if active else 0.0
    )
    # Base join probability: higher when fee APY is good and sentiment positive
    join_prob = 0.02 + max(0.0, (avg_fee_apy - 0.02) * 0.8) * _state.sentiment
    join_prob = min(join_prob, 0.15)

    if random.random() > join_prob:
        return

    eco = _state.eco
    price = eco.price

    # New LP provides between $100k and $600k equivalent of liquidity
    stable_dep = random.uniform(100_000, 600_000)
    paytkn_dep = stable_dep / max(0.001, price)

    # Compute new share: deposited_value / (pool_value + deposited_value)
    pool_value = eco.lp_stable + eco.lp_paytkn * price
    deposit_value = stable_dep + stable_dep   # both sides
    new_share = deposit_value / (pool_value + deposit_value)
    new_share = max(0.01, min(new_share, 0.40))  # cap any single LP at 40%

    # Scale down existing shares proportionally
    for lp in active:
        lp.lp_share *= (1.0 - new_share)
    _renormalize_lp_shares()  # clean float precision

    eco.add_lp_liquidity(paytkn_dep, stable_dep)

    lpid = _state.next_lpid()
    new_lp = LiquidityProvider(
        lpid=lpid,
        entry_price=price,
        paytkn_deposited=paytkn_dep,
        stable_deposited=stable_dep,
        lp_share=new_share,
    )
    _state.lp_providers.append(new_lp)
    _push_event(
        "lp_join",
        f"🌊 New LP {lpid} joined — ${deposit_value/1000:.0f}K provided  ({new_share*100:.1f}% pool)",
        stable_dep, paytkn_dep, "blue",
    )


# ─────────────────────────────────────────────────────────────────
# SENTIMENT
# ─────────────────────────────────────────────────────────────────

def _update_sentiment(price_change_pct: float, vol: float):
    s = _state.sentiment
    # Price-driven component
    signal = price_change_pct * 2.0  # amplify
    # Volatility penalty
    vol_penalty = vol * 0.5
    # Drift toward neutral
    drift = (0.5 - s) * CFG.sentiment_drift
    # Random noise
    noise = random.gauss(0, 0.01)
    s = max(0.05, min(0.98, s + signal - vol_penalty + drift + noise))
    _state.sentiment = s


# ─────────────────────────────────────────────────────────────────
# POPULATION MODEL
# ─────────────────────────────────────────────────────────────────

def _maybe_spawn_users():
    """Daily user growth driven by sentiment + word-of-mouth."""
    # Base new users + sentiment boost
    base_rate = CFG.initial_users * 0.005  # 0.5% daily base
    sentiment_boost = max(0.0, (_state.sentiment - 0.5) * 3.0)
    # WoM: power users and loyal users invite more
    invite_multiplier = 1.0
    for u in _state.users.values():
        if u.active and u.archetype in ("power_user", "loyal"):
            arch = USER_ARCHETYPES[u.archetype]
            invite_multiplier += arch["invite_prob"] * 0.5

    n_new = int(random.gauss(base_rate * (1 + sentiment_boost) * invite_multiplier, 1))
    n_new = max(0, min(n_new, CFG.max_daily_signups))

    for _ in range(n_new):
        arch_name = _sample_archetype()
        arch = USER_ARCHETYPES[arch_name]
        uid = _state.next_uid()
        wallet_lo, wallet_hi = arch["initial_wallet"]
        wallet = random.uniform(wallet_lo, wallet_hi) * _state.sentiment  # smaller wallet in bearish times
        wallet = max(10.0, wallet)
        staked_pct = arch["initial_stake_pct"] * (1 + _state.sentiment * 0.5)
        staked = wallet * staked_pct
        wallet -= staked
        u = User(uid=uid, archetype=arch_name, wallet=wallet, staked=staked,
                 joined_day=_state.day)
        _state.users[uid] = u
        _state.eco.total_staked += staked

    if n_new > 0:
        _push_event("signup", f"🆕 {n_new} new user{'s' if n_new > 1 else ''} joined  (sentiment {_state.sentiment:.2f})",
                    0, 0, "cyan")


def _maybe_churn_users():
    """Daily user churn driven by price performance, APY, loyalty."""
    eco = _state.eco
    price = eco.price
    vol = eco.price_volatility(7)
    apy = _state.rl_params["staking_apy_pct"] / 100

    churned = []
    for uid, u in _state.users.items():
        if not u.active:
            continue
        arch = USER_ARCHETYPES[u.archetype]
        base_churn = arch["churn_prob"]

        # Price volatility increases churn
        vol_factor = vol * 3.0
        # Bearish sentiment increases churn
        sentiment_factor = max(0.0, (0.5 - _state.sentiment) * 0.8)
        # Good APY decreases churn
        apy_factor = max(0.0, 0.10 - apy) * 0.5
        # Loyalty protects from churn
        loyalty_protection = (1.0 - u.loyalty) * 0.02

        churn_prob = base_churn + vol_factor + sentiment_factor + apy_factor + loyalty_protection
        churn_prob = min(churn_prob, 0.10)  # cap at 10% daily

        if random.random() < churn_prob:
            churned.append(uid)

    for uid in churned:
        u = _state.users[uid]
        u.active = False
        # Return staked tokens to wallet (simulates unstake on exit)
        _state.eco.total_staked = max(0, _state.eco.total_staked - u.staked)
        # Sell pressure from churning users
        if u.wallet > 1:
            _state.eco.amm_sell(u.wallet * 0.5)

    if churned:
        _push_event("churn", f"📤 {len(churned)} user{'s' if len(churned) > 1 else ''} churned",
                    0, 0, "orange")


def _maybe_spawn_merchant():
    """Occasionally add new merchants."""
    if random.random() < 0.05 * _state.sentiment:  # 5% chance on good days
        arch_name = _sample_merchant_type()
        arch = MERCHANT_ARCHETYPES[arch_name]
        mid = _state.next_mid()
        existing_names = {m.name for m in _state.merchants.values()}
        name_pool = [n for n in _MERCHANT_NAMES_LIST if n not in existing_names]
        if not name_pool:
            name_pool = [f"Store{_state._next_mid}"]
        name = random.choice(name_pool)
        m = Merchant(mid=mid, archetype=arch_name, name=name, emoji=arch["emoji"],
                     joined_day=_state.day)
        m.wallet = random.uniform(200, 2000)
        _state.merchants[mid] = m


# ─────────────────────────────────────────────────────────────────
# DAILY ACTIONS — per-user/merchant decision logic
# ─────────────────────────────────────────────────────────────────

def _process_user_day(user: User):
    """Process one day's actions for a single user."""
    if not user.active:
        return

    eco = _state.eco
    arch = USER_ARCHETYPES[user.archetype]
    sentiment = _state.sentiment
    price = eco.price
    apy = _state.rl_params["staking_apy_pct"] / 100
    params = _state.rl_params

    s_boost = 0.5 + sentiment  # 0.5..1.5

    # ── PAYMENT ──────────────────────────────
    if random.random() < arch["payment_prob"] * s_boost and user.wallet > 5:
        active_merchants = [m for m in _state.merchants.values() if m.active]
        if active_merchants:
            merchant = random.choice(active_merchants)
            mprof = MERCHANT_ARCHETYPES[merchant.archetype]
            amt = min(user.wallet * 0.4, arch["avg_payment"] * random.uniform(0.5, 2.0))
            amt = max(1.0, amt)

            burn_pct = params["burn_rate_bps"] / 10_000
            fee = amt * burn_pct
            cashback_pct = params["cashback_base_bps"] / 10_000
            cashback = amt * cashback_pct
            merchant_alloc_pct = params["merchant_alloc_bps"] / 10_000
            treasury_alloc_pct = params["treasury_ratio_bps"] / 10_000

            user.wallet -= amt
            net = amt - fee
            auto_staked = net * mprof["stake_rate"]
            merchant.wallet += net - auto_staked
            merchant.staked += auto_staked
            merchant.lifetime_volume += amt
            merchant.tx_count += 1
            eco.total_staked += auto_staked

            # Fee routing
            treasury_cut = fee * treasury_alloc_pct
            reward_cut = fee * params["reward_alloc_bps"] / 10_000
            burn_cut = fee - treasury_cut - reward_cut
            eco.burn(max(0, burn_cut))
            eco.treasury_stable += treasury_cut * price
            eco.reward_pool += max(0, reward_cut)

            # Cashback to user
            user.wallet += cashback
            eco.total_cashback += cashback

            # Demand pressure → AMM buy
            eco.amm_buy(amt * price * 0.01)

            user.lifetime_txs += 1
            user.lifetime_volume += amt
            _state.total_payments += 1
            _state.total_volume_usd += amt * price
            _state.total_cashback += cashback
            eco.daily_tx_count += 1
            eco.daily_volume += amt

            _push_event(
                "payment",
                f'{arch["emoji"]} →  {merchant.emoji} {merchant.name}  ${amt*price:.2f}',
                amt * price, cashback, "blue",
            )

    # ── STAKE ─────────────────────────────────
    apy_boost = 1 + (apy - 0.05) * arch["reward_sensitivity"] * 5
    stake_prob = arch["stake_prob"] * s_boost * apy_boost
    if random.random() < stake_prob and user.wallet > 20:
        amt = min(user.wallet * 0.5, arch["avg_stake"] * random.uniform(0.3, 1.5))
        amt = max(1.0, amt)
        user.wallet -= amt
        user.staked += amt
        eco.total_staked += amt
        _push_event("staking", f'🔒 {arch["emoji"]} staked {amt:.0f} PAYTKN', 0, amt, "purple")

    # ── UNSTAKE ───────────────────────────────
    elif random.random() < arch["unstake_prob"] and user.staked > 50:
        amt = user.staked * random.uniform(0.1, 0.4)
        user.staked -= amt
        user.wallet += amt
        eco.total_staked = max(0, eco.total_staked - amt)
        eco.amm_sell(amt * 0.15)  # partial sell pressure
        _push_event("staking", f'🔓 {arch["emoji"]} unstaked {amt:.0f} PAYTKN', 0, -amt, "yellow")

    # ── DEX TRADE ─────────────────────────────
    if random.random() < arch["trade_prob"] * s_boost:
        buy_bias = 0.5 + (sentiment - 0.5) * 1.5 - (price - 1.0) * arch["price_sensitivity"] * 2
        if random.random() < buy_bias and user.wallet > 10:
            stable_in = min(user.wallet * 0.2 * price, arch["avg_trade"] * random.uniform(0.2, 1.2))
            ptk_out = eco.amm_buy(stable_in)
            user.wallet += ptk_out
            _push_event("trading", f'📈 {arch["emoji"]} bought {ptk_out:.1f} PAYTKN @ ${price:.4f}',
                        stable_in, ptk_out, "cyan")
        elif user.wallet > 10:
            ptk_in = min(user.wallet * 0.25, arch["avg_trade"] * random.uniform(0.2, 1.2))
            stable_out = eco.amm_sell(ptk_in)
            user.wallet += stable_out / max(price, 0.001) - ptk_in
            _push_event("trading", f'📉 {arch["emoji"]} sold {ptk_in:.1f} PAYTKN @ ${price:.4f}',
                        stable_out, -ptk_in, "orange")

    # ── WEEKLY CANCEL RESET ───────────────────
    if _state.day % 7 == 0:
        user.cancels_this_week = 0

    # ── CANCEL ────────────────────────────────
    if (random.random() < arch["cancel_prob"] and
            user.cancels_this_week < CFG.cancel_limit_per_week):
        user.cancels_this_week += 1
        user.loyalty *= (1 - CFG.loyalty_decay_per_cancel)


def _process_merchant_day(merchant: Merchant):
    """Process one day's business actions for a merchant."""
    if not merchant.active:
        return
    arch = MERCHANT_ARCHETYPES[merchant.archetype]
    eco = _state.eco

    # Auto-generate passive revenue (background B2B payments not tracked per-user)
    passive_payments = random_poisson_like(arch["daily_payments"])
    for _ in range(passive_payments):
        amt = arch["avg_received"] * random.uniform(0.7, 1.5)
        auto_stake = amt * arch["stake_rate"]
        merchant.wallet += amt - auto_stake
        merchant.staked += auto_stake
        eco.total_staked += auto_stake
        merchant.lifetime_volume += amt
        merchant.tx_count += 1

    # Loan logic (collateralized)
    if merchant.staked > 100 and random.random() < arch["loan_prob"]:
        max_loan = merchant.staked / CFG.collateral_ratio
        available = max_loan - merchant.loan_balance
        if available > 10 and eco.treasury_stable > available * 0.3:
            loan_amt = min(available * 0.5, eco.treasury_stable * 0.1)
            merchant.loan_balance += loan_amt
            merchant.wallet += loan_amt / max(eco.price, 0.001)
            eco.treasury_stable -= loan_amt
            _push_event("loan", f'🏦 {merchant.emoji} {merchant.name} took loan ${loan_amt:.0f}',
                        loan_amt, 0, "purple")

    # Repay loan
    if merchant.loan_balance > 0 and merchant.wallet > 10:
        repay = min(merchant.wallet * 0.1, merchant.loan_balance * random.uniform(0.1, 0.4))
        if repay > 0:
            merchant.wallet -= repay
            merchant.loan_balance -= repay
            eco.treasury_stable += repay * eco.price


def random_poisson_like(lam: float) -> int:
    """Simple Poisson approximation."""
    if lam <= 0:
        return 0
    # Box-Muller approximation for large λ
    if lam > 10:
        return max(0, int(random.gauss(lam, math.sqrt(lam))))
    # Direct for small λ
    L = math.exp(-lam)
    k, p = 0, 1.0
    while p > L:
        k += 1
        p *= random.random()
    return k - 1


# Monkey-patch so existing code can call random_poisson_like
def _rpl(lam):
    return random_poisson_like(lam)


# ─────────────────────────────────────────────────────────────────
# RL AGENT SYNC
# ─────────────────────────────────────────────────────────────────

def _sync_rl_params():
    """Fetch latest RL actions from the model server (port 8001)."""
    try:
        import requests
        r = requests.get("http://localhost:8001/status", timeout=2)
        if r.status_code == 200:
            la = r.json().get("last_action")
            if la:
                _state.rl_params.update(la)
                # Derive staking APY from reward_alloc_bps
                _state.rl_params["staking_apy_pct"] = (
                    _state.rl_params.get("reward_alloc_bps", 3000) / 10_000 * 100
                )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────
# PROTOCOL ACTIONS (burn, mint, reward distribution)
# ─────────────────────────────────────────────────────────────────

def _do_protocol_day():
    """Daily protocol mechanics — burn, adaptive mint, reward distribution."""
    eco = _state.eco
    params = _state.rl_params
    price = eco.price

    # Daily burn
    burn_rate = params["burn_rate_bps"] / 10_000
    burn_amt = eco.circulating_supply * burn_rate * 0.001  # damped
    eco.burn(burn_amt)
    _state.total_burned += burn_amt

    # Adaptive mint when price < $0.96 (RL-controlled)
    if price < 0.96:
        mf = params["mint_factor"] / 100
        mint_amt = eco.circulating_supply * mf * 0.00003
        eco.mint(mint_amt)
        _state.total_minted += mint_amt
        _push_event("mint", f'⛏️  Protocol minted {mint_amt:.1f} PAYTKN (price support @ ${price:.4f})',
                    0, mint_amt, "green")

    # Extra burn when price > $1.04 (cooling)
    elif price > 1.04:
        extra_burn = eco.circulating_supply * 0.000015
        eco.burn(extra_burn)
        _state.total_burned += extra_burn
        _push_event("burn", f'🔥 Protocol burned {extra_burn:.1f} PAYTKN (cooling @ ${price:.4f})',
                    0, -extra_burn, "red")

    # Weekly staking reward distribution
    apy = params["staking_apy_pct"] / 100
    active_users = {uid: u for uid, u in _state.users.items() if u.active}
    active_merchants = {mid: m for mid, m in _state.merchants.items() if m.active}
    rewards = eco.distribute_rewards(apy, active_users, active_merchants)
    if rewards > 0:
        _state.total_staking_rewards += rewards
        _push_event("reward", f'🏆 Day {_state.day} — {rewards:.1f} PAYTKN distributed to {eco.total_staked/eco.circulating_supply*100:.1f}% stakers',
                    0, rewards, "green")

    # Treasury rebalance
    if eco.treasury_paytkn > 0 and eco.treasury_stable > 0:
        target_ratio = params["treasury_ratio_bps"] / 10_000
        current_paytkn_value = eco.treasury_paytkn * price
        total = eco.treasury_value_usd
        if total > 0:
            current_ratio = current_paytkn_value / total
            diff = target_ratio - current_ratio
            if abs(diff) > 0.05 and _state.day % 7 == 0:
                # Rebalance weekly
                if diff > 0 and eco.treasury_stable > 100:
                    buy_stable = min(eco.treasury_stable * 0.05, 10_000)
                    eco.treasury_stable -= buy_stable
                    eco.treasury_paytkn += eco.amm_buy(buy_stable)
                elif diff < 0 and eco.treasury_paytkn > 100:
                    sell_tkn = min(eco.treasury_paytkn * 0.05, 10_000)
                    eco.treasury_paytkn -= sell_tkn
                    eco.treasury_stable += eco.amm_sell(sell_tkn)

    # Fund reward pool from treasury periodically
    if _state.day % 30 == 0 and eco.treasury_paytkn > 500_000:
        fund = eco.treasury_paytkn * 0.01
        eco.treasury_paytkn -= fund
        eco.reward_pool += fund
        _push_event("treasury", f'💰 Treasury funded reward pool: {fund:.0f} PAYTKN',
                    0, fund, "amber")


# ─────────────────────────────────────────────────────────────────
# DAILY TICK (one simulated day)
# ─────────────────────────────────────────────────────────────────

def _tick_day():
    with _lock:
        _state.day += 1
        eco = _state.eco
        prev_price = eco.price

        # 1. Sync RL params from model server
        _sync_rl_params()

        # 2. Population: spawn new users + churn
        _maybe_spawn_users()
        _maybe_churn_users()
        _maybe_spawn_merchant()

        # 3. User actions (sample a subset for performance — max 150 per day)
        active_users = [u for u in _state.users.values() if u.active]
        sample_size = min(len(active_users), 150)
        day_users = random.sample(active_users, sample_size)
        for u in day_users:
            try:
                _process_user_day(u)
            except Exception:
                pass

        # 4. Merchant actions
        for m in _state.merchants.values():
            if m.active:
                try:
                    _process_merchant_day(m)
                except Exception:
                    pass

        # 5. Protocol mechanics
        _do_protocol_day()

        # 5b. LP lifecycle — distribute fees, run decisions, attract new LPs
        _distribute_lp_fees()
        for lp in list(_state.lp_providers):
            try:
                _process_lp_day(lp)
            except Exception:
                pass
        _maybe_spawn_lp()

        # 6. Update sentiment
        price_change = (eco.price - prev_price) / max(prev_price, 0.001)
        _update_sentiment(price_change, eco.price_volatility(7))

        # 7. Record history
        eco.end_of_day()
        _state.price_history.append({
            "day": _state.day,
            "price": round(eco.price, 6),
            "ts": time.strftime("%H:%M:%S"),
        })
        if len(_state.price_history) > 400:
            _state.price_history.pop(0)

        active_count = sum(1 for u in _state.users.values() if u.active)
        _state.supply_history.append({
            "day": _state.day,
            "supply": round(eco.circulating_supply, 2),
            "staked": round(eco.total_staked, 2),
            "active_users": active_count,
        })
        if len(_state.supply_history) > 400:
            _state.supply_history.pop(0)

        active_lp_count = sum(1 for lp in _state.lp_providers if lp.active)
        amm_tvl = eco.lp_stable + eco.lp_paytkn * eco.price
        _state.daily_stats.append({
            "day": _state.day,
            "price": round(eco.price, 6),
            "txs": eco.daily_tx_count,
            "volume": round(eco.daily_volume * eco.price, 2),
            "burned": round(eco.daily_burn, 4),
            "minted": round(eco.daily_mint, 4),
            "active_users": active_count,
            "sentiment": round(_state.sentiment, 3),
            "staking_ratio": round(eco.staking_ratio * 100, 2),
            "active_lps": active_lp_count,
            "amm_tvl": round(amm_tvl, 2),
            "daily_lp_fees": round(eco.daily_lp_fees, 2),
        })
        if len(_state.daily_stats) > 180:
            _state.daily_stats.pop(0)


_tick_interval: float = 30.0   # seconds per simulated day — changeable via /simulation/speed

def _loop():
    print(f"[SIM] Agent-based economy simulation started — {_tick_interval:.1f}s = 1 day")
    while _state.running:
        try:
            _tick_day()
        except Exception as e:
            print(f"[SIM] day tick error: {e}")
        # Sleep in 0.05s chunks so speed changes and stops take effect immediately
        elapsed = 0.0
        while _state.running and elapsed < _tick_interval:
            time.sleep(0.05)
            elapsed += 0.05
    print("[SIM] Economy simulation stopped")


# ─────────────────────────────────────────────────────────────────
# SERIALIZATION HELPERS
# ─────────────────────────────────────────────────────────────────

def _serialize_state() -> dict:
    eco = _state.eco
    active_users = {uid: u for uid, u in _state.users.items() if u.active}
    active_merchants = {mid: m for mid, m in _state.merchants.items() if m.active}

    # Top users by wallet + staked
    top_users = sorted(active_users.values(),
                       key=lambda u: u.wallet + u.staked, reverse=True)[:10]

    # Top merchants by lifetime volume
    top_merchants = sorted(active_merchants.values(),
                           key=lambda m: m.lifetime_volume, reverse=True)[:6]

    # Archetype breakdown
    arch_counts: dict[str, int] = {}
    for u in active_users.values():
        arch_counts[u.archetype] = arch_counts.get(u.archetype, 0) + 1

    return {
        # Core economy
        "day": _state.day,
        "running": _state.running,
        "token_price_usd": round(eco.price, 6),
        "price_history": _state.price_history[-120:],
        "supply_history": _state.supply_history[-120:],
        "daily_stats": _state.daily_stats[-60:],

        # Supply
        "total_supply": round(eco.circulating_supply, 2),
        "total_minted": round(eco.total_minted, 2),
        "total_burned": round(_state.total_burned + eco.total_burned, 2),

        # Treasury
        "treasury_paytkn": round(eco.treasury_paytkn, 2),
        "treasury_stable": round(eco.treasury_stable, 2),
        "treasury_value_usd": round(eco.treasury_value_usd, 2),
        # Compat alias — agent page and old consumers expect ETH-denominated treasury
        "treasury_eth": round(eco.treasury_stable / 3100, 6),

        # AMM + LP providers
        "lp_paytkn": round(eco.lp_paytkn, 2),
        "lp_stable": round(eco.lp_stable, 2),
        "lp_depth": round(eco.lp_stable * 2, 2),
        "amm_tvl": round(eco.lp_stable + eco.lp_paytkn * eco.price, 2),
        "active_lp_count": sum(1 for lp in _state.lp_providers if lp.active),
        "total_lp_fees_earned": round(sum(lp.accumulated_fees_usd for lp in _state.lp_providers), 2),
        "lp_providers": [
            {
                "id": lp.lpid,
                "share_pct": round(lp.lp_share * 100, 2),
                "il_pct": round(lp.compute_il(eco.price) * 100, 2),
                "fee_apy_pct": round(lp.fee_apy() * 100, 2),
                "days_in_pool": lp.days_in_pool,
                "fees_earned_usd": round(lp.accumulated_fees_usd, 2),
                "deposit_value_usd": round(
                    lp.paytkn_deposited * lp.entry_price + lp.stable_deposited, 2
                ),
            }
            for lp in _state.lp_providers if lp.active
        ],

        # Staking
        "staking_pool": round(eco.total_staked, 2),
        "reward_pool": round(eco.reward_pool, 2),
        "staking_ratio_pct": round(eco.staking_ratio * 100, 2),
        "current_apy_pct": round(_state.rl_params.get("staking_apy_pct", 12.0), 2),
        "total_staking_rewards": round(_state.total_staking_rewards, 2),

        # Volume stats
        "total_payments": _state.total_payments,
        "total_volume_usd": round(_state.total_volume_usd, 2),
        "total_cashback": round(_state.total_cashback, 2),

        # Population
        "total_users": len(_state.users),
        "active_users": len(active_users),
        "total_merchants": len(_state.merchants),
        "active_merchants": len(active_merchants),
        "sentiment": round(_state.sentiment, 3),
        "archetype_breakdown": arch_counts,

        # Market
        "market_cap": round(eco.market_cap, 2),
        "price_volatility": round(eco.price_volatility(7), 6),

        # Top users
        "top_users": [
            {
                "id": u.uid,
                "archetype": u.archetype,
                "emoji": USER_ARCHETYPES[u.archetype]["emoji"],
                "wallet": round(u.wallet, 2),
                "staked": round(u.staked, 2),
                "txs": u.lifetime_txs,
                "volume": round(u.lifetime_volume, 2),
                "loyalty": round(u.loyalty, 3),
            }
            for u in top_users
        ],

        # Top merchants
        "top_merchants": [
            {
                "id": m.mid,
                "name": m.name,
                "archetype": m.archetype,
                "emoji": m.emoji,
                "wallet": round(m.wallet, 2),
                "staked": round(m.staked, 2),
                "volume": round(m.lifetime_volume, 2),
                "tx_count": m.tx_count,
                "loan_balance": round(m.loan_balance, 2),
            }
            for m in top_merchants
        ],

        # RL params
        "rl_params": _state.rl_params,
        "tx_feed": _state.tx_feed[:60],
    }


# ─────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────

@router.get("/state")
def sim_state():
    with _lock:
        return _serialize_state()


@router.get("/feed")
def sim_feed():
    with _lock:
        return {"events": _state.tx_feed[:60], "day": _state.day}


@router.post("/start")
def start_sim():
    global _thread
    if _state.running:
        return {"status": "already_running", "day": _state.day}
    _state.running = True
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()
    return {"status": "started", "initial_users": len(_state.users),
            "initial_merchants": len(_state.merchants)}


@router.post("/stop")
def stop_sim():
    _state.running = False
    return {"status": "stopping", "day": _state.day}


@router.post("/reset")
def reset_sim():
    global _state, _thread
    was_running = _state.running
    _state.running = False
    time.sleep(0.5)  # let tick thread exit
    with _lock:
        new_st = _build_initial_state()
        # Replace all mutable fields in-place so existing references stay valid
        _state.day = new_st.day
        _state.running = False
        _state.sentiment = new_st.sentiment
        _state.users = new_st.users
        _state.merchants = new_st.merchants
        _state.eco = new_st.eco
        _state._next_uid = new_st._next_uid
        _state._next_mid = new_st._next_mid
        _state.lp_providers = new_st.lp_providers
        _state._next_lpid = new_st._next_lpid
        _state.price_history = new_st.price_history
        _state.supply_history = new_st.supply_history
        _state.tx_feed = new_st.tx_feed
        _state.daily_stats = new_st.daily_stats
        _state.total_payments = 0
        _state.total_volume_usd = 0.0
        _state.total_cashback = 0.0
        _state.total_burned = 0.0
        _state.total_minted = 0.0
        _state.total_staking_rewards = 0.0
        _state.rl_params = new_st.rl_params
    if was_running:
        _state.running = True
        _thread = threading.Thread(target=_loop, daemon=True)
        _thread.start()
    return {
        "status": "reset",
        "users": len(_state.users),
        "merchants": len(_state.merchants),
        "treasury_usd": round(_state.eco.treasury_value_usd, 2),
    }


@router.post("/speed")
def set_speed(seconds_per_day: float = 30.0):
    """Set how many real seconds = 1 simulated day. Min 0.3s, max 60s."""
    global _tick_interval
    _tick_interval = max(0.3, min(60.0, seconds_per_day))
    print(f"[SIM] Speed set to {_tick_interval:.2f}s per day")
    return {"status": "ok", "seconds_per_day": _tick_interval}
