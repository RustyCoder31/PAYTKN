import numpy as np
import pytest
from chainenv.population import PopulationManager
from chainenv.config import SimConfig


@pytest.fixture
def pop():
    cfg = SimConfig()
    rng = np.random.default_rng(42)
    pm = PopulationManager(cfg, rng)
    pm.seed_initial()
    return pm


def test_initial_population_count(pop):
    assert len(pop.active_users) == 100
    assert len(pop.active_merchants) == 20


def test_high_sentiment_grows_population(pop):
    before = len(pop.active_users)
    pop.daily_update(sentiment=0.9)
    assert len(pop.active_users) > before


def test_low_sentiment_causes_churn(pop):
    # Bear market: some users will churn
    total_churned = 0
    for _ in range(30):
        _, churned = pop.daily_update(sentiment=0.1)
        total_churned += churned
    assert total_churned > 0


def test_zero_sentiment_minimal_growth(pop):
    initial = len(pop.active_users)
    new_u, _ = pop.daily_update(sentiment=0.0)
    # Near-zero sentiment: lambda ≈ 0 → near zero new users
    assert new_u <= 3


def test_weekly_reset_runs_without_error(pop):
    pop.weekly_reset()   # should not raise


def test_unique_user_ids(pop):
    ids = [u.user_id for u in pop.users]
    assert len(ids) == len(set(ids))
