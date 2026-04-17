from chainenv.profiles import (
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
    assert USER_ARCHETYPES["whale"].avg_payment_amount > USER_ARCHETYPES["casual"].avg_payment_amount


def test_loyal_has_lower_churn_than_speculator():
    assert USER_ARCHETYPES["loyal"].churn_probability < USER_ARCHETYPES["speculator"].churn_probability


def test_sampling_weights_sum_to_one():
    from chainenv.profiles import _USER_WEIGHTS, _MERCHANT_WEIGHTS
    assert abs(sum(_USER_WEIGHTS.values()) - 1.0) < 1e-6
    assert abs(sum(_MERCHANT_WEIGHTS.values()) - 1.0) < 1e-6
