from chainenv.config import ActionBounds, SimConfig, RewardWeights, map_action


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
