import pytest
import numpy as np
from chainenv.economy import Economy
from chainenv.config import SimConfig, AntiGamingRules
from chainenv.actions import Action, ActionKind


@pytest.fixture
def economy():
    return Economy(SimConfig())


def test_initial_price_is_one(economy):
    """AMM starts balanced so price = 1.0."""
    assert economy.price == pytest.approx(1.0)


def test_buy_raises_price(economy):
    price_before = economy.price
    economy.execute_buy("u1", stable_amount=10_000.0)
    assert economy.price > price_before


def test_sell_lowers_price(economy):
    price_before = economy.price
    economy.execute_sell("u1", paytkn_amount=10_000.0)
    assert economy.price < price_before


def test_tx_fee_routes_to_treasury(economy):
    treasury_before = economy.treasury_stable
    economy.process_payment(payer_id="u1", merchant_id="m1", amount=1000.0)
    # Some fee should have landed in treasury
    assert economy.treasury_stable > treasury_before or economy.treasury_paytkn > 0


def test_staking_reward_distributes(economy):
    """After an epoch, stakers receive yield."""
    economy._total_staked = 100_000.0
    economy.treasury_paytkn = 50_000.0
    before = economy.treasury_paytkn
    economy.distribute_staking_rewards(staking_apy=0.10, epoch_days=7)
    # Treasury paid out — balance decreases
    assert economy.treasury_paytkn < before


def test_merchant_loan_requires_collateral(economy):
    """Loan approved only if 150% collateral is posted."""
    # No stake → loan denied
    approved = economy.process_loan_take(merchant_id="m1", amount=1000.0,
                                          merchant_staked=0.0, price=1.0)
    assert approved == 0.0

    # Sufficient stake → loan approved
    approved = economy.process_loan_take(merchant_id="m1", amount=1000.0,
                                          merchant_staked=2000.0, price=1.0)
    assert approved == pytest.approx(1000.0)


def test_constant_product_invariant(economy):
    """k = x*y must be preserved after buy and sell."""
    k_before = economy._lp_paytkn * economy._lp_stable
    economy.execute_buy("u1", stable_amount=5000.0)
    k_after = economy._lp_paytkn * economy._lp_stable
    assert k_after == pytest.approx(k_before, rel=1e-6)


def test_apply_agent_levers_updates_state(economy):
    """Agent lever application must update economy parameters."""
    economy.apply_agent_levers(
        mint_rate=0.01, burn_pct=0.015,
        staking_apy=0.12, treasury_ratio=0.75, reward_alloc=0.25,
    )
    assert economy.current_mint_rate == pytest.approx(0.01)
    assert economy.current_burn_pct == pytest.approx(0.015)
    assert economy.current_staking_apy == pytest.approx(0.12)
