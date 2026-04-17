import numpy as np
import pytest
from chainenv.sentiment import MarketSentiment


def test_initial_value_clamped():
    s = MarketSentiment(initial=0.7)
    assert 0.0 <= s.value <= 1.0


def test_price_crash_lowers_sentiment():
    s = MarketSentiment(initial=0.6, rng=np.random.default_rng(0))
    for _ in range(5):
        s.update(price=0.5, price_yesterday=1.0, volatility=0.3,
                 treasury_health=0.5, active_users=80, prev_users=100)
    assert s.value < 0.6


def test_price_surge_raises_sentiment():
    s = MarketSentiment(initial=0.4, rng=np.random.default_rng(0))
    for _ in range(5):
        s.update(price=1.5, price_yesterday=1.0, volatility=0.05,
                 treasury_health=1.5, active_users=120, prev_users=100)
    assert s.value > 0.4


def test_value_always_in_bounds():
    rng = np.random.default_rng(99)
    s = MarketSentiment(initial=0.5, rng=rng)
    for _ in range(200):
        p = float(rng.uniform(0.1, 3.0))
        s.update(price=p, price_yesterday=1.0, volatility=float(rng.uniform(0, 1)),
                 treasury_health=float(rng.uniform(0, 2)),
                 active_users=int(rng.integers(50, 200)),
                 prev_users=100)
        assert 0.0 <= s.value <= 1.0


def test_labels():
    s = MarketSentiment(initial=0.7)
    assert s.is_bull()
    assert s.label() == "bull"
    s.value = 0.3
    assert s.is_bear()
    assert s.label() == "bear"
    s.value = 0.5
    assert s.label() == "neutral"
