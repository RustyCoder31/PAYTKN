import numpy as np
import pytest
from chainenv.population import PopulationManager
from chainenv.config import SimConfig


@pytest.fixture
def pop():
    cfg = SimConfig()
    rng = np.random.default_rng(42)
    pm = PopulationManager(cfg, rng)
    pm.seed_initial(initial_price=1.0)
    return pm


def _daily_update(pop, sentiment=0.5, actual_apy=0.08, price=1.0):
    return pop.daily_update(
        sentiment=sentiment,
        actual_apy=actual_apy,
        price=price,
        price_ratio=price / 1.0,
    )


def test_initial_population_count(pop):
    """v3.1: 1000 users, 100 merchants, 10 LP providers."""
    assert len(pop.active_users) == 1_000
    assert len(pop.active_merchants) == 100
    assert len(pop.active_lp_providers) == 10


def test_high_sentiment_grows_population(pop):
    before = len(pop.active_users)
    _daily_update(pop, sentiment=0.9)
    assert len(pop.active_users) > before


def test_low_sentiment_causes_churn(pop):
    total_churned = 0
    for _ in range(30):
        _, churned = _daily_update(pop, sentiment=0.1, actual_apy=0.01)
        total_churned += churned
    assert total_churned > 0


def test_zero_sentiment_minimal_growth(pop):
    new_u, _ = _daily_update(pop, sentiment=0.0)
    # Poisson(0) = 0 expected signups
    assert new_u <= 3


def test_weekly_reset_runs_without_error(pop):
    pop.weekly_reset()   # should not raise


def test_unique_user_ids(pop):
    ids = [u.user_id for u in pop.users]
    assert len(ids) == len(set(ids))


def test_unique_lp_ids(pop):
    ids = [lp.lp_id for lp in pop.lp_providers]
    assert len(ids) == len(set(ids))


def test_lp_providers_have_valid_state(pop):
    for lp in pop.active_lp_providers:
        assert lp.entry_price > 0.0
        assert lp.paytkn_deposited > 0.0
        assert lp.stable_deposited > 0.0
        assert 0.0 < lp.lp_share <= 1.0
        assert lp.active is True


def test_lp_daily_update_runs_without_error(pop):
    exits = pop.daily_update_lp_providers(
        current_price=1.0,
        daily_fees_to_lps=500.0,
        treasury_covers_il=True,
    )
    assert isinstance(exits, int)
    assert exits >= 0


def test_lp_catastrophic_price_crash_causes_exits(pop):
    """Price drop to 5 cents → IL >> 15% threshold → LPs exit."""
    exits = pop.daily_update_lp_providers(
        current_price=0.05,
        daily_fees_to_lps=0.0,
        treasury_covers_il=False,
    )
    assert exits > 0


def test_pressure_churn_uses_apy(pop):
    """Low APY + bad sentiment over many days → user churn via pressure."""
    total_churned = 0
    for _ in range(60):
        _, churned = _daily_update(pop, sentiment=0.3, actual_apy=0.005, price=0.5)
        total_churned += churned
    assert total_churned > 0


def test_users_have_v3_fields(pop):
    """Users have wallet (stable), staked (PAYTKN), loyalty_score."""
    u = pop.active_users[0]
    assert hasattr(u, "wallet")
    assert hasattr(u, "staked")
    assert hasattr(u, "loyalty_score")
    assert hasattr(u, "days_active")
    assert hasattr(u, "lifetime_payments")
    assert u.wallet > 0.0   # seeded with stable wallet


def test_merchants_have_v3_fields(pop):
    """Merchants have wallet_paytkn field for holding PAYTKN."""
    m = pop.active_merchants[0]
    assert hasattr(m, "wallet_paytkn")
    assert hasattr(m, "staked")
    assert hasattr(m, "lifetime_volume")
    assert m.wallet_paytkn == 0.0   # starts empty, earns from payments
