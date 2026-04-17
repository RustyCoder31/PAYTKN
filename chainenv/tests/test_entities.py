import numpy as np
import pytest
from chainenv.entities import User, Merchant
from chainenv.profiles import USER_ARCHETYPES, MERCHANT_ARCHETYPES
from chainenv.config import AntiGamingRules
from chainenv.actions import ActionKind


@pytest.fixture
def rules():
    return AntiGamingRules()


def test_user_initial_state():
    u = User(user_id="u1", profile=USER_ARCHETYPES["loyal"], wallet_balance=1000.0)
    assert u.wallet == 1000.0
    assert u.staked == 0.0
    assert u.loyalty_score == 1.0
    assert u.active is True


def test_user_decide_returns_list(rules):
    u = User(user_id="u1", profile=USER_ARCHETYPES["power_user"], wallet_balance=1000.0)
    rng = np.random.default_rng(42)
    actions = u.decide_day_actions(
        rng=rng, sentiment=0.7, price=1.0, staking_apy=0.15, rules=rules,
        merchants=[Merchant("m1", MERCHANT_ARCHETYPES["small_retailer"])],
    )
    assert isinstance(actions, list)


def test_user_loyalty_decays_on_cancel(rules):
    u = User(user_id="u1", profile=USER_ARCHETYPES["casual"], wallet_balance=1000.0)
    initial = u.loyalty_score
    u.apply_cancel(rules)
    assert u.loyalty_score < initial
    assert u.loyalty_score == pytest.approx(initial * (1 - rules.loyalty_decay_per_cancel))


def test_user_cancel_limit_enforced(rules):
    u = User(user_id="u1", profile=USER_ARCHETYPES["speculator"], wallet_balance=1000.0)
    for _ in range(rules.cancel_limit_per_week):
        u.apply_cancel(rules)
    assert u.can_cancel(rules) is False


def test_user_weekly_reset_restores_cancels(rules):
    u = User(user_id="u1", profile=USER_ARCHETYPES["speculator"], wallet_balance=1000.0)
    for _ in range(rules.cancel_limit_per_week):
        u.apply_cancel(rules)
    u.weekly_reset()
    assert u.can_cancel(rules) is True


def test_merchant_accepts_payment():
    m = Merchant("m1", MERCHANT_ARCHETYPES["medium_business"])
    m.receive_payment(100.0)
    assert m.wallet == 100.0
    assert m.lifetime_volume == 100.0


def test_merchant_collateral_for_loan(rules):
    m = Merchant("m1", MERCHANT_ARCHETYPES["medium_business"])
    m.receive_payment(500.0)   # fund wallet first — can't stake what you don't have
    m.stake(500.0)
    max_loan = m.max_borrow(rules, price=1.0)
    assert max_loan == pytest.approx(500.0 / rules.collateral_ratio)


def test_merchant_stake_moves_wallet(rules):
    m = Merchant("m1", MERCHANT_ARCHETYPES["small_retailer"])
    m.receive_payment(200.0)
    m.stake(100.0)
    assert m.wallet == pytest.approx(100.0)
    assert m.staked == pytest.approx(100.0)


def test_user_invite_tree_depth_enforced(rules):
    """Invite tree must not exceed Sheet-7 max depth (5 levels)."""
    u = User(user_id="u0", profile=USER_ARCHETYPES["power_user"], wallet_balance=500.0)
    # Simulate a full invite chain of depth 5
    u.invite_depth = rules.invite_depth_max
    assert u.can_invite(rules) is False
