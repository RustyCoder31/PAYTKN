from chainenv.profiles import (
    UserProfile, MerchantProfile, USER_ARCHETYPES, MERCHANT_ARCHETYPES,
    sample_user_profile, sample_merchant_profile,
)


def test_user_archetypes_defined():
    """v3.1: payment-utility archetypes."""
    expected = {"regular_payer", "power_payer", "staker", "inactive", "speculator", "whale"}
    assert set(USER_ARCHETYPES.keys()) == expected


def test_merchant_archetypes_defined():
    expected = {"small_retailer", "medium_business", "large_business", "subscription"}
    assert set(MERCHANT_ARCHETYPES.keys()) == expected


def test_user_profile_has_required_fields():
    p = USER_ARCHETYPES["regular_payer"]
    assert p.payment_prob > 0
    assert p.stake_prob >= 0
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


def test_whale_pays_more_than_regular():
    """Whale has higher average payment than regular user."""
    assert USER_ARCHETYPES["whale"].avg_payment_amount > USER_ARCHETYPES["regular_payer"].avg_payment_amount


def test_power_payer_has_lower_churn_than_speculator():
    assert USER_ARCHETYPES["power_payer"].churn_probability < USER_ARCHETYPES["speculator"].churn_probability


def test_regular_payer_high_payment_prob():
    """Regular payers have high payment probability (core use case)."""
    assert USER_ARCHETYPES["regular_payer"].payment_prob >= 0.60
    assert USER_ARCHETYPES["power_payer"].payment_prob >= 0.80


def test_staker_has_high_stake_prob():
    """Staker archetype prioritises staking over payments."""
    assert USER_ARCHETYPES["staker"].stake_prob >= USER_ARCHETYPES["regular_payer"].stake_prob


def test_speculator_has_high_trade_prob():
    """Speculators primarily trade, not pay."""
    assert USER_ARCHETYPES["speculator"].trade_prob > USER_ARCHETYPES["regular_payer"].trade_prob


def test_sampling_weights_sum_to_one():
    from chainenv.profiles import _USER_WEIGHTS, _MERCHANT_WEIGHTS
    assert abs(sum(_USER_WEIGHTS.values()) - 1.0) < 1e-6
    assert abs(sum(_MERCHANT_WEIGHTS.values()) - 1.0) < 1e-6
