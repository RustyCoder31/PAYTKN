import pytest
import numpy as np
from chainenv.economy import Economy
from chainenv.config import SimConfig, AntiGamingRules


@pytest.fixture
def economy():
    return Economy(SimConfig())


def test_initial_price_is_one(economy):
    """AMM starts balanced so price = $1.00."""
    assert economy.price == pytest.approx(1.0)


def test_amm_initial_scale():
    """AMM seeded with 10M/10M for deep liquidity (price stability)."""
    eco = Economy(SimConfig())
    cfg = SimConfig()
    assert eco._lp_paytkn == cfg.initial_lp_paytkn == 10_000_000
    assert eco._lp_stable  == cfg.initial_lp_stable  == 10_000_000


def test_buy_raises_price(economy):
    price_before = economy.price
    economy.execute_buy("u1", stable_amount=10_000.0)
    assert economy.price > price_before


def test_sell_lowers_price(economy):
    price_before = economy.price
    economy.execute_sell("u1", paytkn_amount=10_000.0)
    assert economy.price < price_before


def test_buy_with_lp_fee_less_paytkn_out(economy):
    """LP fee means buyer receives slightly less than fee-free math."""
    k = economy._lp_paytkn * economy._lp_stable
    stable_in = 5_000.0
    no_fee_out = economy._lp_paytkn - k / (economy._lp_stable + stable_in)
    out_with_fee = economy.execute_buy("u1", stable_amount=stable_in)
    assert out_with_fee < no_fee_out


def test_payment_routes_fees_not_to_burn(economy):
    """v3.1: no burn from payment fees. Fees → team (dynamic%) + merchant pool + treasury."""
    burn_before = economy._daily_burn
    treasury_before = economy.treasury_paytkn
    economy.process_payment(payer_id="u1", merchant_id="m1", amount_usd=1000.0)
    # No new burn from fees
    assert economy._daily_burn == burn_before
    # Treasury PAYTKN grows from fee routing (fees → treasury) + per-payment mint
    assert economy.treasury_paytkn > treasury_before


def test_payment_routes_to_merchant_staking_pool(economy):
    """Part of tx fee goes to merchant staking pool."""
    pool_before = economy._merchant_staking_pool
    economy.process_payment(payer_id="u1", merchant_id="m1", amount_usd=1000.0)
    assert economy._merchant_staking_pool > pool_before


def test_payment_returns_paytkn_not_stable(economy):
    """process_payment returns (paytkn_to_merchant, cashback_usd)."""
    paytkn_to_merchant, cashback = economy.process_payment("u1", "m1", 1000.0)
    assert isinstance(paytkn_to_merchant, float)
    assert isinstance(cashback, float)
    assert paytkn_to_merchant > 0.0   # merchant gets PAYTKN
    assert cashback >= 0.0


def test_dynamic_cashback_loyalty_scaling(economy):
    """Higher loyalty → higher cashback (via Tx Reward Engine)."""
    economy._reward_pool = 100_000.0   # ensure pool is full
    _, cb_low  = economy.process_payment("u1", "m1", 100.0, loyalty_score=0.1)
    economy._reward_pool = 100_000.0   # reset pool
    _, cb_high = economy.process_payment("u2", "m1", 100.0, loyalty_score=1.0)
    assert cb_high > cb_low


def test_dynamic_cashback_staking_boost(economy):
    """Higher staking boost → higher cashback."""
    economy._reward_pool = 100_000.0
    _, cb_no_stake  = economy.process_payment("u1", "m1", 100.0, staking_boost=0.0)
    economy._reward_pool = 100_000.0
    _, cb_max_stake = economy.process_payment("u2", "m1", 100.0, staking_boost=0.5)
    assert cb_max_stake > cb_no_stake


def test_agent_burn_buyback_and_burn(economy):
    """execute_agent_burn burns PAYTKN accumulated in treasury from fees.
    Treasury earns PAYTKN from fee routing over time; seed 10k for test.
    """
    economy.treasury_paytkn = 10_000.0   # simulate fees earned
    supply_before  = economy.total_supply
    economy.current_burn_rate = 0.001
    burned = economy.execute_agent_burn()
    assert burned > 0.0                            # PAYTKN burned
    assert economy.treasury_paytkn < 10_000.0     # treasury PAYTKN reduced
    assert economy.total_supply < supply_before    # supply reduced


def test_agent_burn_zero_when_treasury_empty(economy):
    """No burn if treasury PAYTKN is zero."""
    economy.treasury_paytkn = 0.0
    burned = economy.execute_agent_burn()
    assert burned == 0.0


def test_agent_burn_zero_when_rate_zero(economy):
    economy.current_burn_rate = 0.0
    burned = economy.execute_agent_burn()
    assert burned == 0.0


def test_staking_reward_returns_actual_apy(economy):
    """distribute_staking_rewards returns actual APY (float), pays from treasury."""
    economy._total_staked = 100_000.0
    economy.treasury_paytkn = 2_000_000.0   # ensure treasury has PAYTKN to pay from
    actual_apy = economy.distribute_staking_rewards()
    assert isinstance(actual_apy, float)
    assert actual_apy >= 0.0
    assert economy.treasury_paytkn < 2_000_000.0   # treasury depleted by rewards


def test_staking_reward_self_sustaining_loop(economy):
    """Fewer stakers → higher APY (same treasury payout / fewer stakers).

    Treasury payout is fixed by daily_pct × treasury_paytkn.
    More stakers dilute the same payout → lower APY per staker.
    """
    TREASURY = 2_000_000.0

    economy.treasury_paytkn = TREASURY
    economy._total_staked = 100_000.0
    apy_high_stakers = economy.distribute_staking_rewards()

    economy.treasury_paytkn = TREASURY   # reset treasury for fair comparison
    economy._total_staked = 5_000.0
    apy_low_stakers = economy.distribute_staking_rewards()

    assert apy_low_stakers > apy_high_stakers


def test_merchant_staking_pool_distributes_yield(economy):
    """Merchant staking pool pays out yield when merchants are staked."""
    economy._merchant_staking_pool = 10_000.0
    economy._merchant_staked = 5_000.0
    apy = economy.distribute_merchant_staking_rewards()
    assert isinstance(apy, float)
    assert apy >= economy.rules.merchant_pool_min_apy
    assert economy._merchant_staking_pool < 10_000.0   # pool decreased


def test_merchant_pool_returns_min_apy_when_empty(economy):
    economy._merchant_staking_pool = 0.0
    economy._merchant_staked = 0.0
    apy = economy.distribute_merchant_staking_rewards()
    assert apy == economy.rules.merchant_pool_min_apy


def test_max_supply_cap_enforced(economy):
    """Per-payment minting must stop when total_supply hits max_supply."""
    cfg = SimConfig()
    economy.total_supply = cfg.max_supply - 1.0
    economy.current_mint_factor = 2.0
    minted = economy._mint_on_payment(amount_usd=10_000.0)
    assert minted <= 1.0 + 1e-6
    assert economy.total_supply <= cfg.max_supply + 1e-6


def test_max_supply_no_mint_at_cap(economy):
    """No per-payment mint when supply is at max cap."""
    economy.total_supply = SimConfig().max_supply
    economy.current_mint_factor = 2.0
    minted = economy._mint_on_payment(amount_usd=10_000.0)
    assert minted == 0.0


def test_adaptive_mint_reduces_with_inflation(economy):
    """Per-payment adaptive mint produces less when already inflated."""
    economy.current_mint_factor = 1.0

    # Not inflated
    economy.total_supply = SimConfig().initial_supply
    economy._daily_mint = 0.0   # reset daily cap accumulator
    mint1 = economy._mint_on_payment(amount_usd=1_000.0)

    # Heavily inflated (supply doubled) — reset daily cap too
    economy.total_supply = SimConfig().initial_supply * 2.0
    economy._daily_mint = 0.0
    mint2 = economy._mint_on_payment(amount_usd=1_000.0)

    assert mint1 > mint2   # more inflation → less minting


def test_daily_mint_is_noop(economy):
    """execute_daily_mint() returns 0 in v3.1 — minting is per-payment only."""
    supply_before = economy.total_supply
    economy.current_mint_factor = 2.0
    minted = economy.execute_daily_mint()
    assert minted == 0.0
    assert economy.total_supply == supply_before


def test_apply_agent_levers_6_params(economy):
    """apply_agent_levers accepts 6 parameters (v3.1 — LP bonus + loans removed)."""
    economy.apply_agent_levers(
        mint_factor=1.5,
        burn_rate=0.0005,
        reward_alloc=0.45,
        cashback_base_rate=0.008,
        merchant_pool_alloc=0.15,
        treasury_ratio=0.70,
    )
    assert economy.current_mint_factor == pytest.approx(1.5)
    assert economy.current_burn_rate   == pytest.approx(0.0005)  # capped at max_burn_rate
    assert economy.current_reward_alloc == pytest.approx(0.45)
    assert economy.current_cashback_base_rate == pytest.approx(0.008)
    assert not hasattr(economy, "current_lp_bonus_rate")   # removed


def test_apply_agent_levers_caps_enforced(economy):
    """Anti-gaming caps on burn, mint, and cashback."""
    economy.apply_agent_levers(
        mint_factor=10.0,     # way above cap
        burn_rate=0.99,       # way above max
        reward_alloc=0.5,
        cashback_base_rate=0.99,  # way above cap
        merchant_pool_alloc=0.10,
        treasury_ratio=0.70,
    )
    assert economy.current_mint_factor <= 2.0
    assert economy.current_burn_rate <= economy.rules.max_burn_rate
    assert economy.current_cashback_base_rate <= 0.02   # hard cap


def test_lp_depth_maintenance_injects_from_treasury(economy):
    """Treasury auto-injects into pool when depth falls below floor."""
    economy._lp_stable = 100_000.0
    treasury_before = economy.treasury_stable
    injected = economy.maintain_lp_depth()
    assert injected > 0.0
    assert economy._lp_stable > 100_000.0
    assert economy.treasury_stable < treasury_before


def test_end_day_returns_tuple(economy):
    """end_day must return (EconomyMetrics, float)."""
    economy.begin_day()
    result = economy.end_day(active_users=50, active_merchants=10)
    assert isinstance(result, tuple)
    assert len(result) == 2
    metrics, actual_apy = result
    assert isinstance(actual_apy, float)
    assert metrics.day == 1


def test_price_corridor_defence_buys_below_floor(economy):
    """Treasury buys when price < $0.70."""
    # Drain PAYTKN from pool to crash price
    economy.execute_sell("test", paytkn_amount=5_000_000.0)
    price_after_crash = economy.price
    if price_after_crash < 0.70:
        treasury_before = economy.treasury_stable
        economy.defend_price_corridor()
        # Treasury spent stable to buy and raise price
        assert economy.treasury_stable <= treasury_before


def test_end_day_includes_merchant_pool_apy(economy):
    """EconomyMetrics includes merchant_pool_apy."""
    economy.begin_day()
    metrics, apy = economy.end_day(active_users=10, active_merchants=5)
    assert hasattr(metrics, "merchant_pool_apy")
    assert hasattr(metrics, "merchant_staking_pool")
