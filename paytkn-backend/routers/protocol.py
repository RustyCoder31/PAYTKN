"""Protocol state endpoints — used by frontend dashboard and RL agent."""
from fastapi import APIRouter
from web3 import Web3
from contracts import token, staking, merchant_staking, treasury, w3, account

router = APIRouter(prefix="/protocol", tags=["Protocol"])


@router.get("/state")
def get_protocol_state():
    """Full protocol snapshot — primary RL agent observation endpoint."""
    state = treasury.functions.getProtocolState().call()
    params = token.functions.getParameters().call()
    supply = token.functions.totalSupply().call()
    price  = treasury.functions.paytknPriceUsd().call()

    return {
        "treasury": {
            "stable_reserve_eth":  Web3.from_wei(state[0], "ether"),
            "paytkn_balance":      Web3.from_wei(state[1], "ether"),
            "stable_floor_ok":     state[0] >= Web3.to_wei(0.001, "ether"),
        },
        "staking": {
            "total_staked":        Web3.from_wei(state[2], "ether"),
            "reward_pool":         Web3.from_wei(state[3], "ether"),
            "current_apy_bps":     state[4],
            "current_apy_pct":     round(state[4] / 100, 2),
        },
        "token": {
            "total_supply":        Web3.from_wei(supply, "ether"),
            "total_minted":        Web3.from_wei(token.functions.totalMinted().call(), "ether"),
            "total_burned":        Web3.from_wei(token.functions.totalBurned().call(), "ether"),
            "total_cashback_paid": Web3.from_wei(token.functions.totalCashbackPaid().call(), "ether"),
            "price_usd":           state[6] / 1e8,
        },
        "payments": {
            "total_processed":     state[7],
            "total_fees_eth":      Web3.from_wei(state[8], "ether"),
            "merchant_pool":       Web3.from_wei(state[9], "ether"),
        },
        "rl_parameters": {
            "mint_factor":         params[0],
            "burn_rate_bps":       params[1],
            "reward_alloc_bps":    params[2],
            "cashback_base_bps":   params[3],
            "merchant_alloc_bps":  params[4],
            "treasury_ratio_bps":  params[5],
            "last_update":         params[6],
        },
        "network": {
            "block":   w3.eth.block_number,
            "chain_id": w3.eth.chain_id,
        }
    }


@router.get("/price")
def get_price():
    price_raw = treasury.functions.paytknPriceUsd().call()
    return {
        "price_usd":     price_raw / 1e8,
        "price_raw":     price_raw,
    }


@router.get("/supply")
def get_supply():
    supply  = token.functions.totalSupply().call()
    minted  = token.functions.totalMinted().call()
    burned  = token.functions.totalBurned().call()
    max_sup = token.functions.MAX_SUPPLY().call()
    return {
        "total_supply":  Web3.from_wei(supply,  "ether"),
        "total_minted":  Web3.from_wei(minted,  "ether"),
        "total_burned":  Web3.from_wei(burned,   "ether"),
        "max_supply":    Web3.from_wei(max_sup,  "ether"),
        "mint_remaining":Web3.from_wei(max_sup - supply, "ether"),
    }
