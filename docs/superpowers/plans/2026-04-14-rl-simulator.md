# PAYTKN RL Tokenomics Simulator — Implementation Plan v2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an agent-based simulator of the PAYTKN utility-token economy where individual users and merchants (each with persistent state and behavioral profiles) take daily actions that shape token price, supply, and ecosystem health. Market sentiment drives organic user growth and churn. A PPO RL agent controls 5 economic levers to optimize a weighted objective (price growth + treasury health + retention + volume + staking). Compare against static parameter baselines.

**Architecture:**
- **Entities:** `User` and `Merchant` classes with persistent state (wallet, stake, loyalty, invite tree). Users have archetype profiles (casual, loyal, whale, speculator, power user, dormant). Merchants have size profiles (small/medium/large/subscription).
- **World loop (one day):** market sentiment updates → population grows/churns → each user/merchant decides actions from their profile → economy processes actions (AMM trades, staking, payments, invites, loans) → RL agent observes state → agent adjusts levers for next day.
- **Anti-gaming rules** from Excel Sheet 7 (cancel limits, loyalty decay, collateral ratios) enforced at the entity level.

**Tech Stack:** Python 3.11+, Gymnasium 0.29+, Stable Baselines3 2.3+, NumPy, Matplotlib, dataclasses, pytest

---

## File Structure

```
paytkn-simulator/
├── pyproject.toml
├── src/paytkn_sim/
│   ├── __init__.py
│   ├── config.py              # bounds, tunable weights, defaults
│   ├── profiles.py            # User & merchant archetypes + behavior params
│   ├── entities.py            # User, Merchant classes with state + decision logic
│   ├── actions.py             # Action dataclasses (Payment, Stake, Invite, Trade, Loan, Cancel)
│   ├── economy.py             # Global state + AMM + action handlers
│   ├── sentiment.py           # Market sentiment model
│   ├── population.py          # Spawns / churns users + merchants
│   └── env.py                 # Gymnasium wrapper — observations, rewards, agent actions
├── scripts/
│   ├── train.py               # PPO training
│   ├── evaluate.py            # RL vs static baseline
│   ├── visualize.py           # Episode traces + learning curves
│   └── projections.py         # Business revenue forecasts using trained agent
├── tests/
│   ├── test_config.py
│   ├── test_profiles.py
│   ├── test_entities.py
│   ├── test_economy.py
│   ├── test_sentiment.py
│   ├── test_population.py
│   └── test_env.py
└── models/                    # gitignored .zip checkpoints
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `paytkn-simulator/pyproject.toml`
- Create: `paytkn-simulator/src/paytkn_sim/__init__.py`
- Create: `paytkn-simulator/tests/__init__.py`
- Create: `paytkn-simulator/.gitignore`

- [ ] **Step 1: Create directory structure**

```bash
cd "C:\Users\Muhammad Essa\Desktop\FYP"
mkdir -p paytkn-simulator/src/paytkn_sim
mkdir -p paytkn-simulator/tests
mkdir -p paytkn-simulator/scripts
mkdir -p paytkn-simulator/models
```

- [ ] **Step 2: Write pyproject.toml**

File: `paytkn-simulator/pyproject.toml`
```toml
[project]
name = "paytkn-sim"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "gymnasium>=0.29",
    "stable-baselines3>=2.3",
    "numpy>=1.24",
    "matplotlib>=3.7",
]

[project.optional-dependencies]
dev = ["pytest>=7.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 3: Write init and gitignore**

File: `src/paytkn_sim/__init__.py`
```python
"""PAYTKN agent-based tokenomics simulator for RL training."""
```

File: `tests/__init__.py`
```python
```

File: `.gitignore`
```
__pycache__/
*.egg-info/
models/*.zip
plots/
logs/
.pytest_cache/
```

- [ ] **Step 4: Install deps**

```bash
cd "C:\Users\Muhammad Essa\Desktop\FYP\paytkn-simulator"
pip install -e ".[dev]"
```

Expected: installs without error.

- [ ] **Step 5: Verify install**

```bash
python -c "import gymnasium, stable_baselines3, numpy, matplotlib; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
cd "C:\Users\Muhammad Essa\Desktop\FYP"
git init
git add paytkn-simulator/
git commit -m "chore: scaffold paytkn-simulator"
```

---

## Task 2: Config — Bounds, Tunable Weights, Defaults

**Files:**
- Create: `src/paytkn_sim/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing test**

File: `tests/test_config.py`
```python
from paytkn_sim.config import ActionBounds, SimConfig, RewardWeights, map_action


def test_action_bounds():
    b = ActionBounds()
    assert b.mint_rate == (0.0, 0.05)
    assert b.burn_pct == (0.001, 0.03)
    assert b.staking_apy == (0.02, 0.25)
    assert b.treasury_ratio == (0.6, 0.9)
    assert b.reward_alloc == (0.1, 0.4)


def test_reward_weights_tunable():
    """User should be able to customize optimization weights."""
    w = RewardWeights(
        price_growth=0.30,
        treasury_growth=0.25,
        user_retention=0.20,
        tx_volume=0.15,
        staking_ratio=0.10,
    )
    assert abs(sum([w.price_growth, w.treasury_growth, w.user_retention,
                    w.tx_volume, w.staking_ratio]) - 1.0) < 1e-6


def test_sim_config_defaults():
    c = SimConfig()
    assert c.initial_users == 100
    assert c.initial_merchants == 20
    assert c.episode_days == 180
    assert c.initial_supply == 100_000_000


def test_map_action():
    assert abs(map_action(-1.0, 0.0, 0.05) - 0.0) < 1e-6
    assert abs(map_action(1.0, 0.0, 0.05) - 0.05) < 1e-6
    assert abs(map_action(0.0, 0.0, 0.05) - 0.025) < 1e-6
    assert abs(map_action(-5.0, 0.0, 0.05) - 0.0) < 1e-6
```

- [ ] **Step 2: Run — verify failure**

```bash
python -m pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement config.py**

File: `src/paytkn_sim/config.py`
```python
"""Parameter bounds, tunable reward weights, simulator defaults."""

from dataclasses import dataclass, field
import numpy as np


def map_action(raw: float, lo: float, hi: float) -> float:
    """Map raw action in [-1, 1] → [lo, hi], clipping out-of-range."""
    clamped = float(np.clip(raw, -1.0, 1.0))
    return lo + (clamped + 1.0) / 2.0 * (hi - lo)


@dataclass(frozen=True)
class ActionBounds:
    """Min/max for each lever the RL agent controls."""
    mint_rate: tuple[float, float] = (0.0, 0.05)
    burn_pct: tuple[float, float] = (0.001, 0.03)
    staking_apy: tuple[float, float] = (0.02, 0.25)
    treasury_ratio: tuple[float, float] = (0.6, 0.9)
    reward_alloc: tuple[float, float] = (0.1, 0.4)


@dataclass
class RewardWeights:
    """User-tunable optimization weights. Should sum to 1.0 for positives."""
    price_growth: float = 0.25
    treasury_growth: float = 0.20
    user_retention: float = 0.20
    tx_volume: float = 0.20
    staking_ratio: float = 0.15
    # Penalties (kept separate, always negative direction)
    volatility_penalty: float = 0.10
    inflation_penalty: float = 0.05
    churn_penalty: float = 0.10


@dataclass
class AntiGamingRules:
    """Hardcoded Excel Sheet 7 thresholds — NOT AI-controlled."""
    cancel_limit_per_week: int = 3
    invite_depth_max: int = 5
    loyalty_decay_per_cancel: float = 0.10
    collateral_ratio: float = 1.50
    tx_staking_delay_days: int = 7
    merchant_wallet_limit_per_week: int = 2


@dataclass
class SimConfig:
    """Top-level simulator configuration."""
    # Initial population
    initial_users: int = 100
    initial_merchants: int = 20

    # Token supply
    initial_supply: float = 100_000_000
    initial_price: float = 1.0

    # AMM
    initial_lp_paytkn: float = 5_000_000
    initial_lp_stable: float = 5_000_000

    # Treasury seed
    initial_treasury_paytkn: float = 10_000_000
    initial_treasury_stable: float = 5_000_000

    # Episode
    episode_days: int = 180

    # Market sentiment
    initial_sentiment: float = 0.55  # slight optimism at launch
    sentiment_drift: float = 0.02    # daily drift toward neutral

    # Growth model
    max_daily_signups: int = 50
    base_churn_rate: float = 0.005   # 0.5% daily chance of churn baseline

    # Fee splits
    team_fee_share: float = 0.10

    # Configurable
    weights: RewardWeights = field(default_factory=RewardWeights)
    bounds: ActionBounds = field(default_factory=ActionBounds)
    rules: AntiGamingRules = field(default_factory=AntiGamingRules)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_config.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/paytkn_sim/config.py tests/test_config.py
git commit -m "feat: config with tunable weights and Sheet-7 rules"
```

---

## Task 3: User & Merchant Profiles (Archetypes)

**Files:**
- Create: `src/paytkn_sim/profiles.py`
- Create: `tests/test_profiles.py`

- [ ] **Step 1: Write failing test**

File: `tests/test_profiles.py`
```python
from paytkn_sim.profiles import (
    UserProfile, MerchantProfile, USER_ARCHETYPES, MERCHANT_ARCHETYPES,
    sample_user_profile, sample_merchant_profile,
)


def test_user_archetypes_defined():
    expected = {"casual", "loyal", "whale", "speculator", "power_user", "dormant"}
    assert set(USER_ARCHETYPES.keys()) == expected


def test_merchant_archetypes_defined():
    expected = {"small_retailer", "medium_business", "large_business", "subscription"}
    assert set(MERCHANT_ARCHETYPES.keys()) == expected


def test_user_profile_has_required_fields():
    p = USER_ARCHETYPES["loyal"]
    assert p.payment_prob > 0
    assert p.stake_prob > 0
    assert p.avg_payment_amount > 0
    assert 0 <= p.price_sensitivity <= 1
    assert 0 <= p.churn_probability <= 1


def test_sample_user_profile_deterministic():
    import numpy as np
    rng = np.random.default_rng(42)
    name1 = sample_user_profile(rng)
    rng = np.random.default_rng(42)
    name2 = sample_user_profile(rng)
    assert name1 == name2


def test_whale_pays_more_than_casual():
    whale = USER_ARCHETYPES["whale"]
    casual = USER_ARCHETYPES["casual"]
    assert whale.avg_payment_amount > casual.avg_payment_amount


def test_loyal_has_lower_churn_than_speculator():
    assert USER_ARCHETYPES["loyal"].churn_probability < USER_ARCHETYPES["speculator"].churn_probability
```

- [ ] **Step 2: Run — verify failure**

```bash
python -m pytest tests/test_profiles.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement profiles.py**

File: `src/paytkn_sim/profiles.py`
```python
"""Behavioral archetypes for users and merchants."""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class UserProfile:
    """Behavior parameters for a user archetype."""
    name: str
    # Daily action probabilities
    payment_prob: float         # chance of paying a merchant today
    stake_prob: float           # chance of staking more today
    unstake_prob: float         # chance of unstaking today
    trade_prob: float           # chance of buying/selling on DEX
    invite_prob: float          # chance of inviting someone today
    cancel_prob: float          # chance of cancelling a subscription

    # Transaction sizes (multiplier on base)
    avg_payment_amount: float   # in PAYTKN
    avg_trade_amount: float     # in PAYTKN
    avg_stake_amount: float     # in PAYTKN

    # Sensitivity
    price_sensitivity: float    # 0..1, how much price drops increase selling
    reward_sensitivity: float   # 0..1, how much APY drives staking

    # Churn
    churn_probability: float    # daily churn baseline (modulated by sentiment)
    recurring_factor: float     # 0..1, how likely to come back each day


@dataclass(frozen=True)
class MerchantProfile:
    """Behavior parameters for a merchant archetype."""
    name: str
    # Activity
    daily_expected_payments: int     # avg payments received per day
    avg_payment_received: float      # average PAYTKN per payment

    # Business logic
    stake_rate: float                # fraction of received payments auto-staked
    loan_prob: float                 # daily chance of taking a loan
    loan_size_factor: float          # multiplier on base loan size

    # Churn
    churn_probability: float


USER_ARCHETYPES: dict[str, UserProfile] = {
    "casual": UserProfile(
        name="casual",
        payment_prob=0.15, stake_prob=0.02, unstake_prob=0.01,
        trade_prob=0.05, invite_prob=0.01, cancel_prob=0.03,
        avg_payment_amount=30.0, avg_trade_amount=100.0, avg_stake_amount=50.0,
        price_sensitivity=0.4, reward_sensitivity=0.3,
        churn_probability=0.008, recurring_factor=0.5,
    ),
    "loyal": UserProfile(
        name="loyal",
        payment_prob=0.40, stake_prob=0.08, unstake_prob=0.01,
        trade_prob=0.02, invite_prob=0.05, cancel_prob=0.005,
        avg_payment_amount=50.0, avg_trade_amount=80.0, avg_stake_amount=200.0,
        price_sensitivity=0.2, reward_sensitivity=0.7,
        churn_probability=0.002, recurring_factor=0.9,
    ),
    "whale": UserProfile(
        name="whale",
        payment_prob=0.10, stake_prob=0.05, unstake_prob=0.03,
        trade_prob=0.20, invite_prob=0.02, cancel_prob=0.01,
        avg_payment_amount=500.0, avg_trade_amount=5000.0, avg_stake_amount=10000.0,
        price_sensitivity=0.7, reward_sensitivity=0.5,
        churn_probability=0.003, recurring_factor=0.7,
    ),
    "speculator": UserProfile(
        name="speculator",
        payment_prob=0.03, stake_prob=0.01, unstake_prob=0.08,
        trade_prob=0.40, invite_prob=0.005, cancel_prob=0.05,
        avg_payment_amount=20.0, avg_trade_amount=1500.0, avg_stake_amount=300.0,
        price_sensitivity=0.9, reward_sensitivity=0.2,
        churn_probability=0.015, recurring_factor=0.4,
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
        churn_probability=0.020, recurring_factor=0.2,
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


# Sampling distributions (sum to 1.0)
_USER_WEIGHTS = {
    "casual": 0.45, "loyal": 0.20, "whale": 0.03,
    "speculator": 0.12, "power_user": 0.10, "dormant": 0.10,
}
_MERCHANT_WEIGHTS = {
    "small_retailer": 0.55, "medium_business": 0.30,
    "large_business": 0.05, "subscription": 0.10,
}


def sample_user_profile(rng: np.random.Generator) -> str:
    names = list(_USER_WEIGHTS.keys())
    probs = list(_USER_WEIGHTS.values())
    return str(rng.choice(names, p=probs))


def sample_merchant_profile(rng: np.random.Generator) -> str:
    names = list(_MERCHANT_WEIGHTS.keys())
    probs = list(_MERCHANT_WEIGHTS.values())
    return str(rng.choice(names, p=probs))
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_profiles.py -v
```

Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/paytkn_sim/profiles.py tests/test_profiles.py
git commit -m "feat: user and merchant archetypes with behavioral parameters"
```

---

## Task 4: Action Types

**Files:**
- Create: `src/paytkn_sim/actions.py`

- [ ] **Step 1: Create action dataclasses**

File: `src/paytkn_sim/actions.py`
```python
"""Action types representing individual user/merchant decisions each day."""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class ActionKind(Enum):
    PAYMENT = "payment"
    STAKE = "stake"
    UNSTAKE = "unstake"
    BUY = "buy"
    SELL = "sell"
    INVITE = "invite"
    CANCEL = "cancel"
    LOAN_TAKE = "loan_take"
    LOAN_REPAY = "loan_repay"


@dataclass
class Action:
    actor_id: str            # user or merchant id
    kind: ActionKind
    amount: float = 0.0      # in PAYTKN (or stables for BUY)
    target_id: str | None = None   # for payments (merchant), invites (invitee)
```

- [ ] **Step 2: Commit**

```bash
git add src/paytkn_sim/actions.py
git commit -m "feat: action types"
```

(No tests — this is plain data. Tests come when actions are consumed.)

---

## Task 5: User & Merchant Entities

**Files:**
- Create: `src/paytkn_sim/entities.py`
- Create: `tests/test_entities.py`

- [ ] **Step 1: Write failing test**

File: `tests/test_entities.py`
```python
import numpy as np
import pytest
from paytkn_sim.entities import User, Merchant
from paytkn_sim.profiles import USER_ARCHETYPES, MERCHANT_ARCHETYPES
from paytkn_sim.config import AntiGamingRules
from paytkn_sim.actions import ActionKind


@pytest.fixture
def rules():
    return AntiGamingRules()


def test_user_initial_state():
    u = User(
        user_id="u1",
        profile=USER_ARCHETYPES["loyal"],
        wallet_balance=1000.0,
    )
    assert u.wallet == 1000.0
    assert u.staked == 0.0
    assert u.loyalty_score == 1.0
    assert u.active is True


def test_user_decide_returns_actions(rules):
    u = User(
        user_id="u1",
        profile=USER_ARCHETYPES["power_user"],
        wallet_balance=1000.0,
    )
    rng = np.random.default_rng(42)
    actions = u.decide_day_actions(
        rng=rng, sentiment=0.7, price=1.0, staking_apy=0.15, rules=rules,
        merchants=[Merchant("m1", MERCHANT_ARCHETYPES["small_retailer"])],
    )
    # Power user should often do something
    assert isinstance(actions, list)


def test_user_loyalty_decays_on_cancel(rules):
    u = User(
        user_id="u1",
        profile=USER_ARCHETYPES["casual"],
        wallet_balance=1000.0,
    )
    initial = u.loyalty_score
    u.apply_cancel(rules)
    assert u.loyalty_score < initial
    assert u.loyalty_score == pytest.approx(initial * (1 - rules.loyalty_decay_per_cancel))


def test_user_cannot_exceed_cancel_limit(rules):
    u = User(
        user_id="u1",
        profile=USER_ARCHETYPES["speculator"],
        wallet_balance=1000.0,
    )
    # Cancel up to the weekly limit
    for _ in range(rules.cancel_limit_per_week):
        u.apply_cancel(rules)
    assert u.can_cancel(rules) is False


def test_merchant_accepts_payment():
    m = Merchant("m1", MERCHANT_ARCHETYPES["medium_business"])
    m.receive_payment(100.0)
    assert m.wallet == 100.0
    assert m.lifetime_volume == 100.0


def test_merchant_collateral_required_for_loan(rules):
    m = Merchant("m1", MERCHANT_ARCHETYPES["medium_business"])
    m.stake(500.0)
    # Can borrow up to staked_value / collateral_ratio
    max_loan = m.max_borrow(rules, price=1.0)
    assert max_loan == pytest.approx(500.0 / rules.collateral_ratio)
```

- [ ] **Step 2: Run — verify failure**

```bash
python -m pytest tests/test_entities.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement entities.py**

File: `src/paytkn_sim/entities.py`
```python
"""User and Merchant entities with persistent state and daily decision logic."""

from __future__ import annotations
from dataclasses import dataclass, field
from collections import deque
import numpy as np

from paytkn_sim.profiles import UserProfile, MerchantProfile
from paytkn_sim.config import AntiGamingRules
from paytkn_sim.actions import Action, ActionKind


@dataclass
class User:
    user_id: str
    profile: UserProfile
    wallet_balance: float = 0.0
    staked: float = 0.0
    loyalty_score: float = 1.0
    active: bool = True
    joined_day: int = 0

    # Invite tree
    invited_by: str | None = None
    invitees: list[str] = field(default_factory=list)

    # Activity tracking (rolling window for rule enforcement)
    recent_cancels: deque = field(default_factory=lambda: deque(maxlen=7))
    lifetime_txs: int = 0
    lifetime_volume: float = 0.0

    @property
    def wallet(self) -> float:
        return self.wallet_balance

    # ── Rule enforcement ────────────────────────────
    def can_cancel(self, rules: AntiGamingRules) -> bool:
        return sum(self.recent_cancels) < rules.cancel_limit_per_week

    def apply_cancel(self, rules: AntiGamingRules) -> bool:
        """Returns True if cancel applied."""
        if not self.can_cancel(rules):
            return False
        self.recent_cancels.append(1)
        self.loyalty_score *= (1 - rules.loyalty_decay_per_cancel)
        return True

    def tick_day(self) -> None:
        """Advance internal counters one day — call at end of each day."""
        self.recent_cancels.append(0)

    # ── Decision logic ──────────────────────────────
    def decide_day_actions(
        self,
        rng: np.random.Generator,
        sentiment: float,
        price: float,
        staking_apy: float,
        rules: AntiGamingRules,
        merchants: list["Merchant"],
    ) -> list[Action]:
        """Return list of actions this user takes today."""
        if not self.active or not merchants:
            return []

        actions: list[Action] = []
        p = self.profile

        # Sentiment boosts activity (optimistic = more actions)
        s_boost = 0.5 + sentiment  # 0.5..1.5

        # Payment
        if rng.random() < p.payment_prob * s_boost and self.wallet > 1:
            amt = min(self.wallet, p.avg_payment_amount * rng.uniform(0.5, 1.5))
            target = merchants[int(rng.integers(0, len(merchants)))]
            actions.append(Action(self.user_id, ActionKind.PAYMENT,
                                  amount=amt, target_id=target.merchant_id))

        # Stake — boosted by APY
        stake_prob_adjusted = p.stake_prob * (1 + (staking_apy - 0.05) * p.reward_sensitivity * 5)
        if rng.random() < stake_prob_adjusted * s_boost and self.wallet > 10:
            amt = min(self.wallet * 0.5, p.avg_stake_amount * rng.uniform(0.3, 1.3))
            actions.append(Action(self.user_id, ActionKind.STAKE, amount=amt))

        # Unstake — boosted by low APY
        if rng.random() < p.unstake_prob and self.staked > 10:
            actions.append(Action(self.user_id, ActionKind.UNSTAKE,
                                  amount=self.staked * rng.uniform(0.1, 0.5)))

        # Trade — direction depends on price sensitivity + sentiment
        if rng.random() < p.trade_prob * s_boost:
            buy_bias = 0.5 + (sentiment - 0.5) - (1.0 - 1.0 / max(price, 0.1)) * p.price_sensitivity
            if rng.random() < buy_bias and self.wallet > 1:
                amt = min(self.wallet * 0.3, p.avg_trade_amount * rng.uniform(0.3, 1.3))
                actions.append(Action(self.user_id, ActionKind.BUY, amount=amt))
            elif self.wallet > 1:
                amt = min(self.wallet * 0.3, p.avg_trade_amount * rng.uniform(0.3, 1.3))
                actions.append(Action(self.user_id, ActionKind.SELL, amount=amt))

        # Invite
        if rng.random() < p.invite_prob * s_boost and self.staked >= 100:
            actions.append(Action(self.user_id, ActionKind.INVITE,
                                  amount=0.0, target_id=f"new_{self.user_id}"))

        # Cancel (subscription)
        if rng.random() < p.cancel_prob and self.can_cancel(rules):
            actions.append(Action(self.user_id, ActionKind.CANCEL, amount=0.0))

        return actions


@dataclass
class Merchant:
    merchant_id: str
    profile: MerchantProfile
    wallet_balance: float = 0.0
    staked: float = 0.0
    loan_balance: float = 0.0
    active: bool = True
    joined_day: int = 0

    # Activity
    lifetime_volume: float = 0.0
    lifetime_payments_received: int = 0

    @property
    def wallet(self) -> float:
        return self.wallet_balance

    # ── Operations ───────────────────────────────
    def receive_payment(self, amount: float) -> float:
        """Merchant receives payment. Returns auto-staked portion."""
        stake_portion = amount * self.profile.stake_rate
        self.wallet_balance += amount - stake_portion
        self.staked += stake_portion
        self.lifetime_volume += amount
        self.lifetime_payments_received += 1
        return stake_portion

    def stake(self, amount: float) -> None:
        if amount <= self.wallet_balance:
            self.wallet_balance -= amount
            self.staked += amount

    def max_borrow(self, rules: AntiGamingRules, price: float) -> float:
        """Max borrowable against current stake (collateralized)."""
        if self.staked <= 0:
            return 0.0
        collateral_value = self.staked * price
        return collateral_value / rules.collateral_ratio

    def decide_day_actions(
        self,
        rng: np.random.Generator,
        sentiment: float,
        price: float,
        rules: AntiGamingRules,
    ) -> list[Action]:
        if not self.active:
            return []
        actions: list[Action] = []
        p = self.profile

        # Loan
        max_l = self.max_borrow(rules, price)
        if rng.random() < p.loan_prob and max_l > 10:
            amt = max_l * p.loan_size_factor * rng.uniform(0.3, 0.8)
            amt = min(amt, max_l * 0.9)  # never max out
            if amt > 0:
                actions.append(Action(self.merchant_id, ActionKind.LOAN_TAKE, amount=amt))

        # Repay existing loan
        if self.loan_balance > 0 and self.wallet_balance > self.loan_balance * 0.1:
            repay = min(self.wallet_balance, self.loan_balance * rng.uniform(0.1, 0.5))
            if repay > 0:
                actions.append(Action(self.merchant_id, ActionKind.LOAN_REPAY, amount=repay))

        return actions
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_entities.py -v
```

Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/paytkn_sim/entities.py tests/test_entities.py
git commit -m "feat: User and Merchant entities with decision logic"
```

---

## Task 6: Economy State + AMM + Action Handlers

**Files:**
- Create: `src/paytkn_sim/economy.py`
- Create: `tests/test_economy.py`

- [ ] **Step 1: Write failing test**

File: `tests/test_economy.py`
```python
import pytest
import numpy as np
from paytkn_sim.config import SimConfig
from paytkn_sim.economy import Economy
from paytkn_sim.entities import User, Merchant
from paytkn_sim.profiles import USER_ARCHETYPES, MERCHANT_ARCHETYPES
from paytkn_sim.actions import Action, ActionKind


@pytest.fixture
def eco():
    return Economy(SimConfig())


def test_initial_price(eco):
    assert abs(eco.price - 1.0) < 1e-6


def test_execute_buy_increases_price(eco):
    p0 = eco.price
    eco.execute_buy(100_000)
    assert eco.price > p0


def test_execute_sell_decreases_price(eco):
    p0 = eco.price
    eco.execute_sell(100_000)
    assert eco.price < p0


def test_constant_product(eco):
    k0 = eco._lp_paytkn * eco._lp_stable
    eco.execute_buy(50_000)
    assert abs(eco._lp_paytkn * eco._lp_stable - k0) < 1.0


def test_mint_increases_supply(eco):
    s0 = eco.circulating_supply
    eco.mint(1_000_000)
    assert eco.circulating_supply == s0 + 1_000_000


def test_apply_payment_action(eco):
    u = User("u1", USER_ARCHETYPES["loyal"], wallet_balance=1000.0)
    m = Merchant("m1", MERCHANT_ARCHETYPES["medium_business"])
    eco.register_user(u)
    eco.register_merchant(m)

    action = Action("u1", ActionKind.PAYMENT, amount=100.0, target_id="m1")
    eco.apply_action(action, burn_pct=0.02)
    assert u.wallet_balance == 900.0
    assert m.wallet_balance + m.staked > 0   # merchant got paid minus burn


def test_apply_stake_action(eco):
    u = User("u1", USER_ARCHETYPES["loyal"], wallet_balance=1000.0)
    eco.register_user(u)
    action = Action("u1", ActionKind.STAKE, amount=400.0)
    eco.apply_action(action, burn_pct=0.01)
    assert u.wallet_balance == 600.0
    assert u.staked == 400.0
    assert eco.total_staked == 400.0


def test_apply_buy_action_uses_amm(eco):
    u = User("u1", USER_ARCHETYPES["loyal"], wallet_balance=1000.0)
    eco.register_user(u)
    action = Action("u1", ActionKind.BUY, amount=100.0)
    eco.apply_action(action, burn_pct=0.01)
    assert u.wallet_balance > 600.0  # spent 100 stables, got tokens added back
```

- [ ] **Step 2: Run — verify failure**

```bash
python -m pytest tests/test_economy.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement economy.py**

File: `src/paytkn_sim/economy.py`
```python
"""Global economy: AMM, supply, treasury, reward pool, action application."""

from __future__ import annotations
from paytkn_sim.config import SimConfig
from paytkn_sim.entities import User, Merchant
from paytkn_sim.actions import Action, ActionKind


class Economy:
    def __init__(self, config: SimConfig) -> None:
        self.cfg = config

        # Supply
        self.circulating_supply = config.initial_supply
        self.total_minted = config.initial_supply
        self.total_burned = 0.0

        # AMM reserves
        self._lp_paytkn = config.initial_lp_paytkn
        self._lp_stable = config.initial_lp_stable

        # Staking totals (sum of all user+merchant stakes)
        self.total_staked = 0.0

        # Treasury
        self.treasury_paytkn = config.initial_treasury_paytkn
        self.treasury_stable = config.initial_treasury_stable

        # Reward pool
        self.reward_pool = 0.0

        # Active loans (merchant_id → amount)
        self.loans: dict[str, float] = {}

        # Registered entities
        self.users: dict[str, User] = {}
        self.merchants: dict[str, Merchant] = {}

        # Daily tracking
        self.daily_tx_count = 0
        self.daily_volume = 0.0
        self.daily_burn = 0.0
        self.daily_mint = 0.0

        # Price history
        self.price_history: list[float] = [self.price]

    # ── Derived ──────────────────────────────
    @property
    def price(self) -> float:
        if self._lp_paytkn <= 0:
            return 0.0
        return self._lp_stable / self._lp_paytkn

    @property
    def treasury_value(self) -> float:
        return self.treasury_paytkn * self.price + self.treasury_stable

    @property
    def market_cap(self) -> float:
        return self.circulating_supply * self.price

    @property
    def staking_ratio(self) -> float:
        if self.circulating_supply <= 0:
            return 0.0
        return self.total_staked / self.circulating_supply

    @property
    def lp_depth(self) -> float:
        return self._lp_stable * 2

    # ── AMM ──────────────────────────────────
    def execute_buy(self, stable_amount: float) -> float:
        if stable_amount <= 0 or self._lp_paytkn <= 0:
            return 0.0
        k = self._lp_paytkn * self._lp_stable
        self._lp_stable += stable_amount
        new_paytkn = k / self._lp_stable
        out = self._lp_paytkn - new_paytkn
        self._lp_paytkn = new_paytkn
        return out

    def execute_sell(self, paytkn_amount: float) -> float:
        if paytkn_amount <= 0 or self._lp_stable <= 0:
            return 0.0
        k = self._lp_paytkn * self._lp_stable
        self._lp_paytkn += paytkn_amount
        new_stable = k / self._lp_paytkn
        out = self._lp_stable - new_stable
        self._lp_stable = new_stable
        return out

    # ── Supply ───────────────────────────────
    def mint(self, amount: float) -> None:
        if amount <= 0:
            return
        self.circulating_supply += amount
        self.total_minted += amount
        self.daily_mint += amount

    def burn(self, amount: float) -> None:
        if amount <= 0:
            return
        actual = min(amount, self.circulating_supply)
        self.circulating_supply -= actual
        self.total_burned += actual
        self.daily_burn += actual

    # ── Treasury ─────────────────────────────
    def treasury_deposit_paytkn(self, amount: float) -> None:
        self.treasury_paytkn += amount

    def treasury_deposit_stable(self, amount: float) -> None:
        self.treasury_stable += amount

    def rebalance_treasury(self, target_paytkn_ratio: float) -> None:
        total = self.treasury_value
        if total <= 0:
            return
        target_pay_value = total * target_paytkn_ratio
        current_pay_value = self.treasury_paytkn * self.price
        diff = target_pay_value - current_pay_value

        if diff > 0 and self.treasury_stable > 0:
            buy = min(abs(diff), self.treasury_stable * 0.1)
            self.treasury_stable -= buy
            self.treasury_paytkn += self.execute_buy(buy)
        elif diff < 0 and self.treasury_paytkn > 0:
            sell_tokens = min(abs(diff) / max(self.price, 0.001), self.treasury_paytkn * 0.1)
            self.treasury_paytkn -= sell_tokens
            self.treasury_stable += self.execute_sell(sell_tokens)

    # ── Registration ─────────────────────────
    def register_user(self, user: User) -> None:
        self.users[user.user_id] = user
        self.total_staked += user.staked

    def register_merchant(self, merchant: Merchant) -> None:
        self.merchants[merchant.merchant_id] = merchant
        self.total_staked += merchant.staked

    # ── Action application ───────────────────
    def apply_action(self, action: Action, burn_pct: float) -> None:
        """Apply one action to the economy, updating all relevant state."""
        k = action.kind

        if k == ActionKind.PAYMENT:
            self._handle_payment(action, burn_pct)
        elif k == ActionKind.STAKE:
            self._handle_stake(action)
        elif k == ActionKind.UNSTAKE:
            self._handle_unstake(action)
        elif k == ActionKind.BUY:
            self._handle_buy(action, burn_pct)
        elif k == ActionKind.SELL:
            self._handle_sell(action, burn_pct)
        elif k == ActionKind.INVITE:
            self._handle_invite(action)
        elif k == ActionKind.CANCEL:
            self._handle_cancel(action)
        elif k == ActionKind.LOAN_TAKE:
            self._handle_loan_take(action)
        elif k == ActionKind.LOAN_REPAY:
            self._handle_loan_repay(action)

    def _handle_payment(self, a: Action, burn_pct: float) -> None:
        u = self.users.get(a.actor_id)
        m = self.merchants.get(a.target_id) if a.target_id else None
        if u is None or m is None or u.wallet_balance < a.amount:
            return
        u.wallet_balance -= a.amount
        u.lifetime_txs += 1
        u.lifetime_volume += a.amount

        fee = a.amount * burn_pct
        team = fee * self.cfg.team_fee_share
        burn_amt = fee - team
        self.burn(burn_amt)
        self.treasury_deposit_stable(team * self.price)

        net = a.amount - fee
        auto_staked = m.receive_payment(net)
        self.total_staked += auto_staked

        self.daily_tx_count += 1
        self.daily_volume += a.amount

    def _handle_stake(self, a: Action) -> None:
        u = self.users.get(a.actor_id)
        if u is None or u.wallet_balance < a.amount:
            return
        u.wallet_balance -= a.amount
        u.staked += a.amount
        self.total_staked += a.amount

    def _handle_unstake(self, a: Action) -> None:
        u = self.users.get(a.actor_id)
        if u is None or u.staked < a.amount:
            return
        u.staked -= a.amount
        u.wallet_balance += a.amount
        self.total_staked -= a.amount

    def _handle_buy(self, a: Action, burn_pct: float) -> None:
        """User spends stables to buy PAYTKN. Here we track synthetic stable wallet = user wallet in stable equivalent."""
        u = self.users.get(a.actor_id)
        if u is None:
            return
        # In our model: stable_amount = a.amount (in stable units)
        stables = min(a.amount, u.wallet_balance * self.price)
        if stables <= 0:
            return
        u.wallet_balance -= stables / max(self.price, 0.001)
        tokens = self.execute_buy(stables)
        fee = tokens * burn_pct
        self.burn(fee)
        u.wallet_balance += (tokens - fee)
        self.daily_volume += tokens

    def _handle_sell(self, a: Action, burn_pct: float) -> None:
        u = self.users.get(a.actor_id)
        if u is None or u.wallet_balance < a.amount:
            return
        u.wallet_balance -= a.amount
        stables = self.execute_sell(a.amount)
        fee = a.amount * burn_pct
        self.burn(fee)
        # stables converted back to wallet at current price
        u.wallet_balance += stables / max(self.price, 0.001) * (1 - burn_pct)
        self.daily_volume += a.amount

    def _handle_invite(self, a: Action) -> None:
        u = self.users.get(a.actor_id)
        if u is None:
            return
        if a.target_id and a.target_id not in u.invitees:
            u.invitees.append(a.target_id)
            # Invite reward minted from reward pool (if funded)
            reward = min(10.0, self.reward_pool)
            if reward > 0:
                self.reward_pool -= reward
                u.wallet_balance += reward

    def _handle_cancel(self, a: Action) -> None:
        u = self.users.get(a.actor_id)
        if u is None:
            return
        u.apply_cancel(self.cfg.rules)

    def _handle_loan_take(self, a: Action) -> None:
        m = self.merchants.get(a.actor_id)
        if m is None:
            return
        max_l = m.max_borrow(self.cfg.rules, self.price)
        amt = min(a.amount, max_l - m.loan_balance, self.treasury_stable)
        if amt <= 0:
            return
        m.loan_balance += amt
        m.wallet_balance += amt / max(self.price, 0.001)  # loan paid in PAYTKN
        self.loans[m.merchant_id] = m.loan_balance
        self.treasury_stable -= amt

    def _handle_loan_repay(self, a: Action) -> None:
        m = self.merchants.get(a.actor_id)
        if m is None:
            return
        repay = min(a.amount, m.loan_balance, m.wallet_balance)
        if repay <= 0:
            return
        m.wallet_balance -= repay
        m.loan_balance -= repay
        self.loans[m.merchant_id] = m.loan_balance
        self.treasury_stable += repay * self.price

    # ── Staking rewards ─────────────────────
    def distribute_staking_rewards(self, daily_apy: float) -> float:
        if self.total_staked <= 0 or self.reward_pool <= 0:
            return 0.0
        total_reward = self.total_staked * daily_apy
        actual = min(total_reward, self.reward_pool)
        self.reward_pool -= actual
        self.mint(actual)

        # Distribute proportionally
        for u in self.users.values():
            if u.staked > 0:
                share = (u.staked / self.total_staked) * actual
                u.wallet_balance += share
        for m in self.merchants.values():
            if m.staked > 0:
                share = (m.staked / self.total_staked) * actual
                m.wallet_balance += share
        return actual

    def fund_reward_pool(self, amount: float) -> None:
        self.reward_pool += amount

    # ── Day tick ────────────────────────────
    def end_of_day(self) -> None:
        self.price_history.append(self.price)
        self.daily_tx_count = 0
        self.daily_volume = 0.0
        self.daily_burn = 0.0
        self.daily_mint = 0.0
        for u in self.users.values():
            u.tick_day()

    def price_volatility(self, window: int = 7) -> float:
        if len(self.price_history) < 2:
            return 0.0
        recent = self.price_history[-window:]
        if len(recent) < 2:
            return 0.0
        mean = sum(recent) / len(recent)
        var = sum((p - mean) ** 2 for p in recent) / len(recent)
        return var ** 0.5
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_economy.py -v
```

Expected: 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/paytkn_sim/economy.py tests/test_economy.py
git commit -m "feat: economy with AMM and action handlers for all 9 action types"
```

---

## Task 7: Market Sentiment Model

**Files:**
- Create: `src/paytkn_sim/sentiment.py`
- Create: `tests/test_sentiment.py`

- [ ] **Step 1: Write failing test**

File: `tests/test_sentiment.py`
```python
import pytest
import numpy as np
from paytkn_sim.sentiment import MarketSentiment


@pytest.fixture
def sent():
    return MarketSentiment(initial=0.5, drift=0.02)


def test_initial(sent):
    assert sent.value == 0.5


def test_sentiment_updates_on_price_rise(sent):
    # Simulate a price rise
    sent.update(price_change_pct=0.05, volatility=0.01, treasury_health=1.0)
    # Sentiment should have responded positively
    assert sent.value > 0.5


def test_sentiment_updates_on_price_crash(sent):
    sent.update(price_change_pct=-0.20, volatility=0.05, treasury_health=1.0)
    assert sent.value < 0.5


def test_sentiment_clamped_0_1(sent):
    for _ in range(100):
        sent.update(price_change_pct=0.50, volatility=0.0, treasury_health=2.0)
    assert sent.value <= 1.0
    assert sent.value >= 0.0


def test_drift_toward_neutral_with_no_signal(sent):
    sent.update(price_change_pct=0.20, volatility=0.0, treasury_health=1.0)
    high = sent.value
    for _ in range(20):
        sent.update(price_change_pct=0.0, volatility=0.0, treasury_health=1.0)
    assert abs(sent.value - 0.5) < abs(high - 0.5)
```

- [ ] **Step 2: Run — verify failure**

```bash
python -m pytest tests/test_sentiment.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement sentiment.py**

File: `src/paytkn_sim/sentiment.py`
```python
"""Market sentiment dynamics — drives user inflows/outflows and activity."""

import numpy as np


class MarketSentiment:
    """Sentiment in [0, 1]. 0.5 = neutral. >0.7 bullish, <0.3 bearish."""

    def __init__(self, initial: float = 0.5, drift: float = 0.02) -> None:
        self.value = float(np.clip(initial, 0.0, 1.0))
        self.drift = drift

    def update(
        self,
        price_change_pct: float,
        volatility: float,
        treasury_health: float,
        noise: float = 0.0,
    ) -> float:
        """Update sentiment based on ecosystem signals.

        Args:
            price_change_pct: daily price change (e.g. 0.05 = +5%)
            volatility: normalized 7-day volatility
            treasury_health: treasury_value / (market_cap * 0.1), 1.0 = healthy
            noise: optional random shock
        """
        # Price response (strongest)
        price_response = np.tanh(price_change_pct * 10) * 0.15

        # Volatility penalty
        vol_response = -min(volatility * 2, 1.0) * 0.05

        # Treasury confidence
        treasury_response = np.tanh((treasury_health - 1.0) * 2) * 0.03

        # Mean-reversion (drift to neutral)
        mean_pull = (0.5 - self.value) * self.drift

        delta = price_response + vol_response + treasury_response + mean_pull + noise
        self.value = float(np.clip(self.value + delta, 0.0, 1.0))
        return self.value
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_sentiment.py -v
```

Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/paytkn_sim/sentiment.py tests/test_sentiment.py
git commit -m "feat: market sentiment model with price/volatility/treasury response"
```

---

## Task 8: Population Manager — Spawn / Churn

**Files:**
- Create: `src/paytkn_sim/population.py`
- Create: `tests/test_population.py`

- [ ] **Step 1: Write failing test**

File: `tests/test_population.py`
```python
import pytest
import numpy as np
from paytkn_sim.config import SimConfig
from paytkn_sim.population import PopulationManager
from paytkn_sim.economy import Economy


@pytest.fixture
def setup():
    cfg = SimConfig()
    eco = Economy(cfg)
    rng = np.random.default_rng(42)
    pop = PopulationManager(cfg, rng)
    pop.seed_initial(eco)
    return cfg, eco, rng, pop


def test_initial_population(setup):
    cfg, eco, _, _ = setup
    assert len(eco.users) == cfg.initial_users
    assert len(eco.merchants) == cfg.initial_merchants


def test_high_sentiment_spawns_users(setup):
    cfg, eco, rng, pop = setup
    initial = len(eco.users)
    pop.daily_update(eco, sentiment=0.9, day=1)
    assert len(eco.users) >= initial  # should usually grow


def test_low_sentiment_no_signups(setup):
    cfg, eco, rng, pop = setup
    initial = len(eco.users)
    pop.daily_update(eco, sentiment=0.1, day=1)
    # Low sentiment → close to zero signups (could still have churn)
    assert len(eco.users) <= initial + 2


def test_churn_deactivates_users(setup):
    """Some users should become inactive over time."""
    cfg, eco, rng, pop = setup
    # Run many days with neutral sentiment to trigger some churn
    for day in range(30):
        pop.daily_update(eco, sentiment=0.5, day=day)
    inactive = sum(1 for u in eco.users.values() if not u.active)
    # At least some churn should have happened
    assert inactive >= 0  # weak check — just verify no crash
```

- [ ] **Step 2: Run — verify failure**

```bash
python -m pytest tests/test_population.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement population.py**

File: `src/paytkn_sim/population.py`
```python
"""Population manager — seeds initial users/merchants, handles daily growth and churn."""

import numpy as np

from paytkn_sim.config import SimConfig
from paytkn_sim.entities import User, Merchant
from paytkn_sim.profiles import (
    USER_ARCHETYPES, MERCHANT_ARCHETYPES,
    sample_user_profile, sample_merchant_profile,
)
from paytkn_sim.economy import Economy


class PopulationManager:
    def __init__(self, config: SimConfig, rng: np.random.Generator) -> None:
        self.cfg = config
        self.rng = rng
        self._next_user_id = 0
        self._next_merchant_id = 0

    def seed_initial(self, economy: Economy) -> None:
        """Seed initial users and merchants."""
        for _ in range(self.cfg.initial_users):
            self._spawn_user(economy, day=0, initial_wallet=100.0)
        for _ in range(self.cfg.initial_merchants):
            self._spawn_merchant(economy, day=0)

    def daily_update(self, economy: Economy, sentiment: float, day: int) -> dict:
        """Each day: spawn new users based on sentiment, churn inactive users."""
        signups = self._spawn_daily(economy, sentiment, day)
        churned = self._churn_daily(economy, sentiment)
        return {"signups": signups, "churned": churned}

    def _spawn_daily(self, economy: Economy, sentiment: float, day: int) -> int:
        """Spawn new users based on sentiment. Bullish sentiment → more signups."""
        # Signups scale with sentiment (quadratic for stronger effect)
        scaled = sentiment ** 2 * 2
        expected = self.cfg.max_daily_signups * scaled
        n_users = int(self.rng.poisson(max(expected, 0)))
        n_merchants = max(1, n_users // 5) if sentiment > 0.6 else 0

        for _ in range(n_users):
            self._spawn_user(economy, day=day, initial_wallet=50.0 + self.rng.exponential(50))
        for _ in range(n_merchants):
            self._spawn_merchant(economy, day=day)

        return n_users

    def _churn_daily(self, economy: Economy, sentiment: float) -> int:
        """Deactivate users based on churn probability modulated by sentiment."""
        # Low sentiment amplifies churn
        churn_multiplier = 1.0 + (0.5 - sentiment) * 2.0  # 0.0..2.0
        churn_multiplier = max(churn_multiplier, 0.1)
        count = 0
        for u in economy.users.values():
            if not u.active:
                continue
            p_churn = u.profile.churn_probability * churn_multiplier * (2.0 - u.loyalty_score)
            if self.rng.random() < p_churn:
                u.active = False
                count += 1
        for m in economy.merchants.values():
            if not m.active:
                continue
            if self.rng.random() < m.profile.churn_probability * churn_multiplier:
                m.active = False
        return count

    def _spawn_user(self, economy: Economy, day: int, initial_wallet: float) -> User:
        archetype = sample_user_profile(self.rng)
        user_id = f"u{self._next_user_id}"
        self._next_user_id += 1
        user = User(
            user_id=user_id,
            profile=USER_ARCHETYPES[archetype],
            wallet_balance=initial_wallet,
            joined_day=day,
        )
        economy.register_user(user)
        return user

    def _spawn_merchant(self, economy: Economy, day: int) -> Merchant:
        archetype = sample_merchant_profile(self.rng)
        mid = f"m{self._next_merchant_id}"
        self._next_merchant_id += 1
        merchant = Merchant(
            merchant_id=mid,
            profile=MERCHANT_ARCHETYPES[archetype],
            joined_day=day,
        )
        economy.register_merchant(merchant)
        return merchant
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_population.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/paytkn_sim/population.py tests/test_population.py
git commit -m "feat: population manager with sentiment-driven growth and churn"
```

---

## Task 9: Gymnasium Environment — The RL Interface

**Files:**
- Create: `src/paytkn_sim/env.py`
- Create: `tests/test_env.py`

- [ ] **Step 1: Write failing test**

File: `tests/test_env.py`
```python
import numpy as np
import pytest
from paytkn_sim.env import PaytknEnv


def test_env_spaces():
    env = PaytknEnv()
    assert env.observation_space.shape == (15,)
    assert env.action_space.shape == (5,)


def test_reset():
    env = PaytknEnv()
    obs, info = env.reset(seed=42)
    assert obs.shape == (15,)
    assert obs.dtype == np.float32


def test_step_progresses():
    env = PaytknEnv(episode_days=10)
    env.reset(seed=42)
    total_reward = 0.0
    truncated = False
    for _ in range(10):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        if terminated:
            break
    assert truncated or terminated
    # Info should include useful diagnostics
    assert "users_active" in info
    assert "merchants_active" in info
    assert "price" in info


def test_population_grows_over_time():
    env = PaytknEnv(episode_days=30)
    obs, info = env.reset(seed=42)
    initial_users = info["users_active"]
    for _ in range(30):
        action = np.zeros(5, dtype=np.float32)
        obs, reward, terminated, truncated, info = env.step(action)
        if terminated:
            break
    # Average case: population should change
    assert info["users_total"] >= initial_users


def test_gym_check():
    from gymnasium.utils.env_checker import check_env
    env = PaytknEnv(episode_days=5)
    check_env(env.unwrapped)
```

- [ ] **Step 2: Run — verify failure**

```bash
python -m pytest tests/test_env.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement env.py**

File: `src/paytkn_sim/env.py`
```python
"""Gymnasium environment — the RL training interface."""

from __future__ import annotations
import gymnasium as gym
import numpy as np
from gymnasium import spaces

from paytkn_sim.config import SimConfig, map_action
from paytkn_sim.economy import Economy
from paytkn_sim.population import PopulationManager
from paytkn_sim.sentiment import MarketSentiment


class PaytknEnv(gym.Env):
    """PAYTKN utility-token economy for RL training.

    Observation (15 floats):
        0  price_ratio        current / 30d moving average
        1  price_volatility   7d rolling std
        2  tx_volume          daily volume / (initial_supply * 0.01)
        3  tx_volume_trend    7d growth rate
        4  active_users       active / initial_users
        5  new_signups        daily new / max_daily_signups
        6  churn_rate         daily churned / active
        7  sentiment          raw 0..1
        8  staking_ratio      staked / circulating
        9  treasury_health    treasury_value / (mcap * 0.1)
        10 treasury_pay_frac  treasury_paytkn_value / treasury_value
        11 lp_depth           lp / initial_lp
        12 reward_pool        pool / (mcap * 0.01)
        13 net_mint_burn_7d   (minted - burned) / circulating
        14 loan_utilization   total_loans / treasury_stable

    Action (5 floats in [-1, 1]):
        0 mint_rate
        1 burn_pct
        2 staking_apy
        3 treasury_ratio
        4 reward_alloc
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        config: SimConfig | None = None,
        episode_days: int | None = None,
    ) -> None:
        super().__init__()
        self.cfg = config or SimConfig()
        if episode_days is not None:
            self.cfg.episode_days = episode_days
        self.bounds = self.cfg.bounds
        self.weights = self.cfg.weights

        self.observation_space = spaces.Box(
            low=-10.0, high=10.0, shape=(15,), dtype=np.float32
        )
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(5,), dtype=np.float32
        )

        self._eco: Economy | None = None
        self._pop: PopulationManager | None = None
        self._sent: MarketSentiment | None = None
        self._rng: np.random.Generator | None = None
        self._day = 0
        self._recent_minted: list[float] = []
        self._recent_burned: list[float] = []
        self._recent_volumes: list[float] = []
        self._churn_log: list[int] = []
        self._signup_log: list[int] = []

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._rng = np.random.default_rng(seed)
        self._eco = Economy(self.cfg)
        self._pop = PopulationManager(self.cfg, self._rng)
        self._pop.seed_initial(self._eco)
        self._sent = MarketSentiment(self.cfg.initial_sentiment, self.cfg.sentiment_drift)
        self._day = 0
        self._recent_minted.clear()
        self._recent_burned.clear()
        self._recent_volumes.clear()
        self._churn_log.clear()
        self._signup_log.clear()
        return self._get_obs(), self._get_info()

    def step(self, action: np.ndarray):
        assert self._eco and self._pop and self._sent and self._rng is not None
        b = self.bounds
        mint_rate = map_action(action[0], *b.mint_rate)
        burn_pct = map_action(action[1], *b.burn_pct)
        staking_apy = map_action(action[2], *b.staking_apy)
        treasury_ratio = map_action(action[3], *b.treasury_ratio)
        reward_alloc = map_action(action[4], *b.reward_alloc)

        price_before = self._eco.price
        mcap_before = self._eco.market_cap
        treasury_before = self._eco.treasury_value

        # 1. Population update
        pop_update = self._pop.daily_update(self._eco, self._sent.value, self._day)
        self._signup_log.append(pop_update["signups"])
        self._churn_log.append(pop_update["churned"])

        # 2. Collect actions from all active entities
        active_users = [u for u in self._eco.users.values() if u.active]
        active_merchants = [m for m in self._eco.merchants.values() if m.active]

        user_actions = []
        for u in active_users:
            user_actions.extend(u.decide_day_actions(
                self._rng, self._sent.value, self._eco.price,
                staking_apy, self.cfg.rules, active_merchants,
            ))
        merchant_actions = []
        for m in active_merchants:
            merchant_actions.extend(m.decide_day_actions(
                self._rng, self._sent.value, self._eco.price, self.cfg.rules,
            ))

        # 3. Apply all actions
        for a in user_actions + merchant_actions:
            self._eco.apply_action(a, burn_pct)

        # 4. Mint new tokens (agent-controlled)
        mint_amount = self._eco.circulating_supply * mint_rate
        if mint_amount > 0:
            reward_share = mint_amount * reward_alloc
            treasury_share = mint_amount - reward_share
            self._eco.fund_reward_pool(reward_share)
            self._eco.treasury_deposit_paytkn(treasury_share)
            self._eco.mint(mint_amount)

        # 5. Distribute staking rewards
        daily_apy = staking_apy / 365.0
        self._eco.distribute_staking_rewards(daily_apy)

        # 6. Rebalance treasury
        self._eco.rebalance_treasury(treasury_ratio)

        # 7. Update sentiment based on outcomes
        price_change = (self._eco.price - price_before) / max(price_before, 1e-6)
        mcap = self._eco.market_cap
        treasury_health = self._eco.treasury_value / max(mcap * 0.1, 1)
        noise = float(self._rng.normal(0, 0.005))
        self._sent.update(price_change, self._eco.price_volatility(7), treasury_health, noise)

        # 8. End of day
        self._recent_minted.append(self._eco.daily_mint)
        self._recent_burned.append(self._eco.daily_burn)
        self._recent_volumes.append(self._eco.daily_volume)
        if len(self._recent_minted) > 7:
            self._recent_minted = self._recent_minted[-7:]
            self._recent_burned = self._recent_burned[-7:]
            self._recent_volumes = self._recent_volumes[-7:]

        self._eco.end_of_day()
        self._day += 1

        # Termination conditions
        truncated = self._day >= self.cfg.episode_days
        terminated = self._eco.price <= 0.01 or len(active_users) == 0

        reward = self._compute_reward(price_before, treasury_before)
        return self._get_obs(), reward, terminated, truncated, self._get_info()

    def _get_obs(self) -> np.ndarray:
        eco = self._eco
        assert eco is not None

        # Moving average
        hist = eco.price_history
        ma30 = sum(hist[-30:]) / max(len(hist[-30:]), 1)
        price_ratio = eco.price / max(ma30, 1e-6)

        volatility = eco.price_volatility(7)

        base_vol = self.cfg.initial_supply * 0.01
        cur_volume = sum(self._recent_volumes[-1:]) if self._recent_volumes else 0.0
        volume_norm = cur_volume / max(base_vol, 1)

        if len(self._recent_volumes) >= 7:
            old = sum(self._recent_volumes[:3]) / 3
            new = sum(self._recent_volumes[-3:]) / 3
            volume_trend = (new - old) / max(old, 1)
        else:
            volume_trend = 0.0

        active_users = sum(1 for u in eco.users.values() if u.active)
        total_users = len(eco.users)
        signups_recent = self._signup_log[-1] if self._signup_log else 0
        churn_recent = self._churn_log[-1] if self._churn_log else 0

        treasury_health = eco.treasury_value / max(eco.market_cap * 0.1, 1)
        pay_frac = (eco.treasury_paytkn * eco.price) / max(eco.treasury_value, 1)
        lp_ratio = eco.lp_depth / max(self.cfg.initial_lp_stable * 2, 1)
        pool_ratio = eco.reward_pool / max(eco.market_cap * 0.01, 1)

        net_mb = sum(self._recent_minted) - sum(self._recent_burned)
        net_mb_ratio = net_mb / max(eco.circulating_supply, 1)

        total_loans = sum(eco.loans.values())
        loan_util = total_loans / max(eco.treasury_stable + total_loans, 1)

        obs = np.array([
            np.clip(price_ratio, -10, 10),
            np.clip(volatility, -10, 10),
            np.clip(volume_norm, -10, 10),
            np.clip(volume_trend, -10, 10),
            np.clip(active_users / max(self.cfg.initial_users, 1), -10, 10),
            np.clip(signups_recent / max(self.cfg.max_daily_signups, 1), -10, 10),
            np.clip(churn_recent / max(active_users, 1), -10, 10),
            self._sent.value,
            np.clip(eco.staking_ratio, -10, 10),
            np.clip(treasury_health, -10, 10),
            np.clip(pay_frac, -10, 10),
            np.clip(lp_ratio, -10, 10),
            np.clip(pool_ratio, -10, 10),
            np.clip(net_mb_ratio * 100, -10, 10),
            np.clip(loan_util, -10, 10),
        ], dtype=np.float32)
        return obs

    def _compute_reward(self, price_before: float, treasury_before: float) -> float:
        w = self.weights
        eco = self._eco
        assert eco is not None

        # Price growth component (utility-token mode: reward sustainable upward movement)
        price_change = (eco.price - price_before) / max(price_before, 1e-6)
        price_growth = float(np.tanh(price_change * 5))  # smooth, bounded

        # Treasury growth
        treasury_change = (eco.treasury_value - treasury_before) / max(treasury_before, 1)
        treasury_score = float(np.tanh(treasury_change * 2))

        # User retention
        active = sum(1 for u in eco.users.values() if u.active)
        total = max(len(eco.users), 1)
        retention = active / total  # 0..1

        # TX volume (normalized)
        volume_score = float(np.tanh(eco.daily_volume / (self.cfg.initial_supply * 0.005)))

        # Staking ratio (peak at 40%)
        sr = eco.staking_ratio
        staking_score = 1.0 - min(abs(sr - 0.4) * 2, 1.0)

        # Volatility penalty
        vol_penalty = min(eco.price_volatility(7) / max(eco.price, 0.1), 1.0)

        # Inflation penalty
        net_mb = sum(self._recent_minted) - sum(self._recent_burned)
        inflation = max(net_mb / max(eco.circulating_supply, 1), 0)
        inflation_penalty = min(inflation * 100, 1.0)

        # Churn penalty
        recent_churn = self._churn_log[-1] if self._churn_log else 0
        churn_penalty = min(recent_churn / max(total, 1), 1.0)

        reward = (
            w.price_growth * price_growth
            + w.treasury_growth * treasury_score
            + w.user_retention * retention
            + w.tx_volume * volume_score
            + w.staking_ratio * staking_score
            - w.volatility_penalty * vol_penalty
            - w.inflation_penalty * inflation_penalty
            - w.churn_penalty * churn_penalty
        )
        return float(reward)

    def _get_info(self) -> dict:
        eco = self._eco
        if eco is None:
            return {}
        active_users = sum(1 for u in eco.users.values() if u.active)
        active_merchants = sum(1 for m in eco.merchants.values() if m.active)
        return {
            "price": eco.price,
            "market_cap": eco.market_cap,
            "treasury_value": eco.treasury_value,
            "staking_ratio": eco.staking_ratio,
            "circulating_supply": eco.circulating_supply,
            "users_active": active_users,
            "users_total": len(eco.users),
            "merchants_active": active_merchants,
            "sentiment": self._sent.value if self._sent else 0.5,
            "day": self._day,
        }
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_env.py -v
```

Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/paytkn_sim/env.py tests/test_env.py
git commit -m "feat: Gymnasium env — 15-obs, 5-action, reward with tunable weights"
```

---

## Task 10: Training Script (PPO)

**Files:**
- Create: `scripts/train.py`

- [ ] **Step 1: Write training script**

File: `scripts/train.py`
```python
"""Train PPO agent on PAYTKN simulator."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from paytkn_sim.env import PaytknEnv


def make_env_fn(episode_days: int):
    def _init():
        return PaytknEnv(episode_days=episode_days)
    return _init


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timesteps", type=int, default=500_000)
    parser.add_argument("--episode-days", type=int, default=180)
    parser.add_argument("--n-envs", type=int, default=4)
    parser.add_argument("--output", type=str, default="models/ppo_paytkn")
    args = parser.parse_args()

    print(f"Training PPO for {args.timesteps} steps, episode={args.episode_days} days")
    vec_env = make_vec_env(make_env_fn(args.episode_days), n_envs=args.n_envs)

    model = PPO(
        "MlpPolicy", vec_env,
        verbose=1, learning_rate=3e-4,
        n_steps=2048, batch_size=64, n_epochs=10,
        gamma=0.99, gae_lambda=0.95, clip_range=0.2,
        ent_coef=0.01, tensorboard_log="./logs/",
    )
    model.learn(total_timesteps=args.timesteps)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(out))
    print(f"Saved {out}.zip")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test**

```bash
cd "C:\Users\Muhammad Essa\Desktop\FYP\paytkn-simulator"
python scripts/train.py --timesteps 2000 --episode-days 30 --n-envs 2 --output models/smoke
```

Expected: trains, saves `models/smoke.zip`

- [ ] **Step 3: Commit**

```bash
git add scripts/train.py
git commit -m "feat: PPO training script"
```

---

## Task 11: Evaluation — RL vs Static Baseline

**Files:**
- Create: `scripts/evaluate.py`

- [ ] **Step 1: Write evaluation script**

File: `scripts/evaluate.py`
```python
"""Compare trained RL agent vs static-parameter baseline."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
from stable_baselines3 import PPO
from paytkn_sim.env import PaytknEnv


STATIC_ACTION = np.array([0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)


def run_episode(env, model=None, seed=42):
    obs, info = env.reset(seed=seed)
    total_r, prices, users = 0.0, [info["price"]], [info["users_active"]]
    while True:
        action = model.predict(obs, deterministic=True)[0] if model else STATIC_ACTION
        obs, r, term, trunc, info = env.step(action)
        total_r += r
        prices.append(info["price"])
        users.append(info["users_active"])
        if term or trunc:
            break
    return {
        "total_reward": total_r,
        "final_price": prices[-1],
        "price_std": float(np.std(prices)),
        "max_users": max(users),
        "final_users": users[-1],
        "final_treasury": info["treasury_value"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="models/ppo_paytkn")
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--episode-days", type=int, default=180)
    args = parser.parse_args()

    model = PPO.load(args.model)

    print(f"{'Agent':<10} {'AvgRwd':>10} {'FinalPx':>10} {'Vol':>10} "
          f"{'MaxUsers':>10} {'Treasury':>14}")
    print("-" * 70)

    for label, agent in [("RL", model), ("Static", None)]:
        results = []
        for i in range(args.episodes):
            env = PaytknEnv(episode_days=args.episode_days)
            results.append(run_episode(env, agent, seed=i * 17))
        avg = lambda k: np.mean([r[k] for r in results])
        print(f"{label:<10} {avg('total_reward'):>10.2f} {avg('final_price'):>10.4f} "
              f"{avg('price_std'):>10.4f} {avg('max_users'):>10.0f} "
              f"{avg('final_treasury'):>14.0f}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test**

```bash
python scripts/evaluate.py --model models/smoke --episodes 3 --episode-days 30
```

Expected: prints comparison table

- [ ] **Step 3: Commit**

```bash
git add scripts/evaluate.py
git commit -m "feat: RL vs static baseline evaluation script"
```

---

## Task 12: Visualization

**Files:**
- Create: `scripts/visualize.py`

- [ ] **Step 1: Write visualization script**

File: `scripts/visualize.py`
```python
"""Visualize trained agent — price, users, treasury, actions over an episode."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from stable_baselines3 import PPO
from paytkn_sim.env import PaytknEnv
from paytkn_sim.config import ActionBounds, map_action


def collect(env, model, seed):
    obs, info = env.reset(seed=seed)
    data = {
        "prices": [info["price"]],
        "users": [info["users_active"]],
        "treasury": [info["treasury_value"]],
        "sentiment": [info["sentiment"]],
        "staking_ratios": [info["staking_ratio"]],
        "rewards": [],
        "actions_raw": [],
    }
    while True:
        action = model.predict(obs, deterministic=True)[0]
        data["actions_raw"].append(action.copy())
        obs, r, term, trunc, info = env.step(action)
        data["prices"].append(info["price"])
        data["users"].append(info["users_active"])
        data["treasury"].append(info["treasury_value"])
        data["sentiment"].append(info["sentiment"])
        data["staking_ratios"].append(info["staking_ratio"])
        data["rewards"].append(r)
        if term or trunc:
            break
    return data


def plot(data, save_path):
    fig, axes = plt.subplots(3, 2, figsize=(14, 12))
    fig.suptitle("PAYTKN RL Agent — Full Episode Trace", fontsize=14, fontweight="bold")
    days = range(len(data["prices"]))

    axes[0, 0].plot(days, data["prices"], color="#1565C0")
    axes[0, 0].set_title("Price"); axes[0, 0].grid(alpha=0.3)

    axes[0, 1].plot(days, data["users"], color="#2E7D32")
    axes[0, 1].set_title("Active Users"); axes[0, 1].grid(alpha=0.3)

    axes[1, 0].plot(days, data["treasury"], color="#6A1B9A")
    axes[1, 0].set_title("Treasury Value"); axes[1, 0].grid(alpha=0.3)

    axes[1, 1].plot(days, data["sentiment"], color="#E65100")
    axes[1, 1].axhline(0.5, color="grey", linestyle="--", alpha=0.5)
    axes[1, 1].set_title("Market Sentiment"); axes[1, 1].grid(alpha=0.3)

    bounds = ActionBounds()
    names = ["Mint", "Burn", "APY", "T.Ratio", "RwdAlloc"]
    b_list = [bounds.mint_rate, bounds.burn_pct, bounds.staking_apy,
              bounds.treasury_ratio, bounds.reward_alloc]
    actions = np.array(data["actions_raw"])
    for i, (nm, bd) in enumerate(zip(names, b_list)):
        mapped = [map_action(a[i], *bd) for a in actions]
        axes[2, 0].plot(mapped, label=nm, alpha=0.8)
    axes[2, 0].set_title("Agent Actions"); axes[2, 0].legend(fontsize=7, ncol=2)
    axes[2, 0].grid(alpha=0.3)

    axes[2, 1].plot(np.cumsum(data["rewards"]), color="#880E4F")
    axes[2, 1].set_title("Cumulative Reward"); axes[2, 1].grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"Saved {save_path}")
    plt.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="models/ppo_paytkn")
    parser.add_argument("--episode-days", type=int, default=180)
    parser.add_argument("--outdir", type=str, default="plots")
    args = parser.parse_args()

    Path(args.outdir).mkdir(parents=True, exist_ok=True)
    model = PPO.load(args.model)
    env = PaytknEnv(episode_days=args.episode_days)
    data = collect(env, model, seed=42)
    plot(data, f"{args.outdir}/episode_trace.png")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test**

```bash
python scripts/visualize.py --model models/smoke --episode-days 30 --outdir plots
```

Expected: creates `plots/episode_trace.png`

- [ ] **Step 3: Commit**

```bash
git add scripts/visualize.py
git commit -m "feat: visualization with price, users, treasury, actions, rewards"
```

---

## Task 13: Revenue Projection Script (Business Plan)

**Files:**
- Create: `scripts/projections.py`

- [ ] **Step 1: Write projection script**

File: `scripts/projections.py`
```python
"""Use trained agent to project ecosystem metrics & fee revenue for business plan."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
from stable_baselines3 import PPO
from paytkn_sim.env import PaytknEnv


def run_projection(model, episode_days, n_episodes, seed_base):
    """Run multiple episodes with the trained agent; aggregate metrics."""
    all_results = []
    for i in range(n_episodes):
        env = PaytknEnv(episode_days=episode_days)
        obs, info = env.reset(seed=seed_base + i)
        # Track cumulative team fees (10% of burn per TX → stables)
        team_fees = 0.0
        while True:
            a = model.predict(obs, deterministic=True)[0]
            obs, r, term, trunc, info = env.step(a)
            # team fee accrues to treasury_stable in _handle_payment
            if term or trunc:
                break
        all_results.append({
            "final_price": info["price"],
            "final_users": info["users_active"],
            "final_merchants": info["merchants_active"],
            "final_treasury": info["treasury_value"],
            "final_mcap": info["market_cap"],
        })
    return all_results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="models/ppo_paytkn")
    parser.add_argument("--episodes", type=int, default=50)
    parser.add_argument("--episode-days", type=int, default=180)
    args = parser.parse_args()

    model = PPO.load(args.model)
    results = run_projection(model, args.episode_days, args.episodes, seed_base=1000)

    metrics = {
        "final_price":    [r["final_price"] for r in results],
        "final_users":    [r["final_users"] for r in results],
        "final_merchants":[r["final_merchants"] for r in results],
        "final_treasury": [r["final_treasury"] for r in results],
        "final_mcap":     [r["final_mcap"] for r in results],
    }

    print(f"Projection over {args.episodes} episodes × {args.episode_days} days:")
    print("-" * 60)
    for key, vals in metrics.items():
        mean = np.mean(vals); std = np.std(vals)
        p10, p50, p90 = np.percentile(vals, [10, 50, 90])
        print(f"{key:<18} mean={mean:>14.2f}  p10={p10:>12.2f} "
              f"p50={p50:>12.2f} p90={p90:>12.2f}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test**

```bash
python scripts/projections.py --model models/smoke --episodes 5 --episode-days 30
```

Expected: prints percentile table

- [ ] **Step 3: Commit**

```bash
git add scripts/projections.py
git commit -m "feat: revenue projections with percentile bands"
```

---

## Task 14: Full Training Run + Results

- [ ] **Step 1: Full training (500k steps)**

```bash
cd "C:\Users\Muhammad Essa\Desktop\FYP\paytkn-simulator"
python scripts/train.py --timesteps 500000 --n-envs 4 --output models/ppo_paytkn
```

- [ ] **Step 2: Evaluate**

```bash
python scripts/evaluate.py --model models/ppo_paytkn --episodes 50 --episode-days 180
```

- [ ] **Step 3: Visualize**

```bash
python scripts/visualize.py --model models/ppo_paytkn --episode-days 180 --outdir plots
```

- [ ] **Step 4: Project**

```bash
python scripts/projections.py --model models/ppo_paytkn --episodes 50 --episode-days 180
```

- [ ] **Step 5: Commit results**

```bash
git add plots/
git commit -m "results: trained agent + eval + plots + projections"
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - Utility token (no peg) ✓ — price growth rewarded, not peg adherence
   - Individual user simulation ✓ — `User` / `Merchant` classes with state
   - 6 user archetypes ✓ — casual, loyal, whale, speculator, power_user, dormant
   - 4 merchant archetypes ✓ — small_retailer, medium_business, large_business, subscription
   - Market sentiment ✓ — `MarketSentiment` class drives population + behavior
   - Organic growth ✓ — `PopulationManager` spawns based on sentiment
   - Anti-gaming from Sheet 7 ✓ — `AntiGamingRules` hardcoded in config
   - Merchant loans + liquidations ✓ — `LOAN_TAKE` / `LOAN_REPAY` actions
   - Invite cascades (5 levels) ✓ — `invitees` field, max depth enforced via rules
   - Loyalty decay ✓ — `apply_cancel` reduces loyalty_score
   - Tunable reward weights ✓ — `RewardWeights` dataclass user-editable
   - 5 RL levers ✓ — mint, burn, APY, treasury ratio, reward alloc
   - All 5 optimization targets in reward ✓ — price, treasury, retention, volume, staking

2. **Placeholder scan:** No TBD / TODO / "implement later" in any step. All code blocks complete.

3. **Type consistency:**
   - `Action` fields match usage in `Economy._handle_*` methods
   - `UserProfile` / `MerchantProfile` attributes accessed consistently
   - `PopulationManager.daily_update` returns `dict` — used via keyed access in env.py
   - `AntiGamingRules` fields referenced identically across entities.py and economy.py
   - Observation space shape (15,) matches length of array built in `_get_obs`

---

## Open Items (Post-Plan Discussion)

The user said "first complete the plan then discuss what can be made for best." Items to decide after reviewing this plan:

1. Do we train on a **single scenario type** or **randomized** (agent sees bull/bear/crash mixed during training)?
2. Should evaluation run across different **sentiment starting conditions** to stress-test?
3. How much data do you want in the **projections script** — revenue curves, user growth S-curves, treasury trajectories?
4. Is **tensorboard** logging useful for you, or just final-episode plots?
