from chainenv.config import ActionBounds, SimConfig, RewardWeights, AntiGamingRules, map_action


def test_action_bounds_v3():
    b = ActionBounds()
    assert b.mint_factor          == (0.0,   2.0)
    assert b.burn_rate            == (0.0,   0.0005)
    assert b.reward_alloc         == (0.20,  0.60)
    assert b.cashback_base_rate   == (0.001, 0.010)   # capped at 1% — fees are primary
    assert b.merchant_pool_alloc  == (0.05,  0.25)
    assert b.treasury_ratio       == (0.30,  0.90)   # midpoint 0.60 = fixed 60/40 static split
    assert not hasattr(b, "lp_bonus_rate")             # removed — LPs earn from swap fees


def test_action_bounds_has_6_levers():
    """6 levers: LP bonus and loans removed."""
    b = ActionBounds()
    fields = [f for f in vars(b) if not f.startswith('_')]
    assert len(fields) == 6


def test_reward_weights_positive_sum():
    """Positive weight components should sum to 1.0."""
    w = RewardWeights()
    total = (w.treasury_health + w.user_growth + w.stability
             + w.tx_volume + w.apy_signal + w.lp_depth + w.price_growth)
    assert abs(total - 1.0) < 1e-6


def test_reward_weights_treasury_health_primary():
    """Treasury health is the primary objective."""
    w = RewardWeights()
    assert w.treasury_health >= w.user_growth
    assert w.treasury_health >= w.stability
    assert w.treasury_health >= w.tx_volume
    assert w.treasury_health >= w.lp_depth
    assert w.treasury_health >= w.price_growth


def test_sim_config_defaults_v3():
    c = SimConfig()
    # v3.1: 1000 users, 100 merchants (realistic launch scale)
    assert c.initial_users == 1_000
    assert c.initial_merchants == 100
    assert c.episode_days == 180
    assert c.initial_supply == 12_000_000   # 10M AMM + 2M treasury
    assert c.max_supply == 100_000_000      # 88M left to mint
    assert c.initial_supply < c.max_supply


def test_sim_config_amm_seeded_by_raise():
    """AMM seeded with full $10M raise → price = $1.00 at genesis."""
    c = SimConfig()
    assert c.initial_lp_paytkn == 10_000_000
    assert c.initial_lp_stable == 10_000_000
    assert c.initial_lp_paytkn == c.initial_lp_stable  # 1:1 ratio → $1.00


def test_sim_config_payment_fee():
    c = SimConfig()
    assert c.payment_fee_rate == 0.005   # 0.5% protocol fee
    assert c.lp_fee_rate == 0.003        # 0.3% LP fee
    assert c.team_fee_share == 0.10      # 10% to team


def test_sim_config_treasury_separate_from_amm():
    c = SimConfig()
    assert c.initial_treasury_paytkn == 2_000_000     # 2M PAYTKN at genesis
    assert c.initial_treasury_stable == 2_000_000     # $2M stable operational reserve


def test_sim_config_lp_fields():
    c = SimConfig()
    assert c.initial_lp_providers == 10
    assert c.lp_fee_rate == 0.003


def test_anti_gaming_rules_v3():
    r = AntiGamingRules()
    # v3: lower floors than v2 (emergent APY model)
    assert r.min_staking_apy == 0.03          # 3% floor
    assert r.max_burn_rate == 0.0005          # max 0.05%/day treasury burn
    assert r.min_lp_depth_stable == 2_000_000  # $2M LP depth floor
    assert r.il_protection_threshold == 0.05
    assert r.lp_risk_premium == 0.02
    assert r.opportunity_cost_rate == 0.03    # 3% merchant opportunity cost


def test_anti_gaming_rules_tx_reward_engine_caps():
    """Tx Reward Engine multiplier caps exist."""
    r = AntiGamingRules()
    assert r.max_cashback_loyalty_boost   == 1.00
    assert r.max_cashback_staking_boost   == 0.50
    assert r.max_cashback_seniority_boost == 0.30
    assert r.max_cashback_invite_boost    == 0.20


def test_anti_gaming_rules_merchant_pool():
    r = AntiGamingRules()
    assert r.merchant_pool_min_apy == 0.02   # 2% minimum merchant pool APY


def test_map_action():
    assert abs(map_action(-1.0, 0.0, 0.05) - 0.0)   < 1e-6
    assert abs(map_action(1.0,  0.0, 0.05) - 0.05)  < 1e-6
    assert abs(map_action(0.0,  0.0, 0.05) - 0.025) < 1e-6
    assert abs(map_action(-5.0, 0.0, 0.05) - 0.0)   < 1e-6   # clipped
