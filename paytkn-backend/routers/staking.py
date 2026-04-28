"""Staking endpoints — user staking pool + merchant staking pool."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from web3 import Web3
from contracts import staking, merchant_staking, send_tx

router = APIRouter(prefix="/staking", tags=["Staking"])


@router.get("/stats")
def staking_stats():
    """User staking pool stats."""
    total  = staking.functions.totalStaked().call()
    pool   = staking.functions.rewardPool().call()
    apy    = staking.functions.currentAPY().call()
    stakers = staking.functions.uniqueStakers().call()
    claimed = staking.functions.totalRewardsClaimed().call()

    return {
        "total_staked_paytkn":    Web3.from_wei(total,   "ether"),
        "reward_pool_paytkn":     Web3.from_wei(pool,    "ether"),
        "current_apy_bps":        apy,
        "current_apy_pct":        round(apy / 100, 2),
        "unique_stakers":         stakers,
        "total_rewards_claimed":  Web3.from_wei(claimed, "ether"),
        "lockup_tiers": [
            {"days": 0,   "multiplier": "1.0x", "label": "Flexible"},
            {"days": 30,  "multiplier": "1.2x", "label": "30 Days"},
            {"days": 90,  "multiplier": "1.5x", "label": "90 Days"},
            {"days": 180, "multiplier": "2.0x", "label": "180 Days"},
        ],
    }


@router.get("/user/{address}")
def get_user_stakes(address: str):
    addr = Web3.to_checksum_address(address)
    stakes = staking.functions.getStakes(addr).call()
    result = []
    for i, s in enumerate(stakes):
        if s[0] > 0:
            pending = staking.functions.pendingRewards(addr, i).call()
            result.append({
                "index":      i,
                "amount":     Web3.from_wei(s[0], "ether"),
                "since":      s[1],
                "lockup_end": s[2],
                "multiplier": s[3] / 10000,
                "pending_rewards": Web3.from_wei(pending, "ether"),
            })
    return {"address": address, "stakes": result}


@router.get("/merchant/stats")
def merchant_stats():
    total   = merchant_staking.functions.totalMerchantStaked().call()
    pool    = merchant_staking.functions.merchantRewardPool().call()
    apy     = merchant_staking.functions.currentAPY().call()
    count   = merchant_staking.functions.getMerchantCount().call()
    paid    = merchant_staking.functions.totalRewardsPaid().call()

    return {
        "total_staked_paytkn":   Web3.from_wei(total, "ether"),
        "reward_pool_paytkn":    Web3.from_wei(pool,  "ether"),
        "current_apy_bps":       apy,
        "current_apy_pct":       round(apy / 100, 2),
        "total_merchants":       count,
        "total_rewards_paid":    Web3.from_wei(paid,  "ether"),
        "tiers": [
            {"name": "Bronze",   "min_stake": 0,       "fee_discount": "0%",  "cashback_boost": "0%"},
            {"name": "Silver",   "min_stake": 10000,   "fee_discount": "10%", "cashback_boost": "10%"},
            {"name": "Gold",     "min_stake": 50000,   "fee_discount": "20%", "cashback_boost": "20%"},
            {"name": "Platinum", "min_stake": 200000,  "fee_discount": "30%", "cashback_boost": "30%"},
        ],
    }


@router.get("/merchant/{address}/tier")
def get_merchant_tier(address: str):
    addr = Web3.to_checksum_address(address)
    tier, fee_disc, cashback_boost = merchant_staking.functions.getMerchantTier(addr).call()
    names = ["Bronze", "Silver", "Gold", "Platinum"]
    return {
        "address":          address,
        "tier":             tier,
        "tier_name":        names[tier],
        "fee_discount_bps": fee_disc,
        "cashback_boost_bps": cashback_boost,
    }
