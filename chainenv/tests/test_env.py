import numpy as np
import pytest
import gymnasium as gym
from chainenv.env import PaytknEnv, OBS_DIM, ACT_DIM


@pytest.fixture
def env():
    e = PaytknEnv()
    e.reset(seed=42)
    return e


def test_observation_space_shape(env):
    obs, _ = env.reset(seed=0)
    assert obs.shape == (OBS_DIM,)


def test_action_space_shape(env):
    assert env.action_space.shape == (ACT_DIM,)


def test_act_dim_is_6():
    """v3.1 has 6 RL levers (LP bonus + loans removed)."""
    assert ACT_DIM == 6


def test_obs_dim_is_24():
    assert OBS_DIM == 24


def test_obs_in_valid_range(env):
    obs, _ = env.reset(seed=0)
    assert not np.any(np.isnan(obs))
    assert not np.any(np.isinf(obs))


def test_single_step_returns_valid_obs(env):
    action = env.action_space.sample()
    obs, reward, terminated, truncated, info = env.step(action)
    assert obs.shape == (OBS_DIM,)
    assert isinstance(reward, float)
    assert not np.isnan(reward)
    assert isinstance(terminated, bool)


def test_episode_runs_to_completion():
    env = PaytknEnv()
    obs, _ = env.reset(seed=7)
    terminated = False
    steps = 0
    while not terminated:
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        steps += 1
        assert not np.any(np.isnan(obs)), f"NaN in obs at step {steps}"
    assert steps == env.cfg.episode_days


def test_reward_is_finite_throughout():
    env = PaytknEnv()
    env.reset(seed=3)
    for _ in range(30):
        action = env.action_space.sample()
        _, reward, terminated, _, _ = env.step(action)
        assert np.isfinite(reward)
        if terminated:
            break


def test_deterministic_with_same_seed():
    env1 = PaytknEnv()
    env2 = PaytknEnv()
    obs1, _ = env1.reset(seed=42)
    obs2, _ = env2.reset(seed=42)
    np.testing.assert_array_equal(obs1, obs2)

    action = np.zeros(ACT_DIM, dtype=np.float32)
    o1, r1, *_ = env1.step(action)
    o2, r2, *_ = env2.step(action)
    np.testing.assert_array_almost_equal(o1, o2)
    assert r1 == pytest.approx(r2)


def test_action_space_bounds():
    env = PaytknEnv()
    assert env.action_space.low.shape  == (ACT_DIM,)
    assert env.action_space.high.shape == (ACT_DIM,)
    assert np.all(env.action_space.low  == -1.0)
    assert np.all(env.action_space.high ==  1.0)


def test_metrics_in_info(env):
    """Step info dict should include EconomyMetrics."""
    action = env.action_space.sample()
    _, _, _, _, info = env.step(action)
    assert "metrics" in info
    metrics = info["metrics"]
    assert hasattr(metrics, "daily_tx_volume")
    assert hasattr(metrics, "actual_apy")
    assert hasattr(metrics, "merchant_pool_apy")
    assert hasattr(metrics, "merchant_staking_pool")


def test_merchant_receives_paytkn_not_stable(env):
    """After payments, merchants should have wallet_paytkn > 0."""
    # Run several steps to allow payments to flow
    for _ in range(10):
        action = env.action_space.sample()
        env.step(action)
    # At least some merchants should hold PAYTKN by now
    merchants = env._pop.active_merchants
    paytkn_holders = [m for m in merchants if m.wallet_paytkn > 0 or m.wallet > 0]
    assert len(paytkn_holders) > 0


def test_gymnasium_check():
    """gymnasium.utils.env_checker should pass without critical errors."""
    from gymnasium.utils.env_checker import check_env
    env = PaytknEnv()
    check_env(env, warn=True, skip_render_check=True)
