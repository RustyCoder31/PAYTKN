"""RL Agent endpoints — observe chain state, push parameter updates.
   Includes in-memory simulation fallback so the demo works even if a
   specific on-chain tx reverts (bounds mismatch, gas spike, etc.).
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from contracts import token, treasury, send_tx

router = APIRouter(prefix="/agent", tags=["RL Agent"])

# ── In-memory parameter cache (used as fallback / simulation) ────────────────
_params_cache: dict = {
    "mint_factor":        100,
    "burn_rate_bps":      2,
    "reward_alloc_bps":   3000,
    "cashback_base_bps":  50,
    "merchant_alloc_bps": 1000,
    "treasury_ratio_bps": 6000,
}

# ── RL model server state (updated by model server via /agent/model-status) ──
_model_status: dict = {
    "connected":     False,
    "model_path":    None,
    "step_count":    0,
    "last_action":   None,
    "last_reward":   None,
    "running":       False,
}


class AgentAction(BaseModel):
    mint_factor:        int = Field(..., ge=1,   le=200)
    burn_rate_bps:      int = Field(..., ge=0,   le=5)
    reward_alloc_bps:   int = Field(..., ge=1000, le=6000)
    cashback_base_bps:  int = Field(..., ge=10,  le=100)
    merchant_alloc_bps: int = Field(..., ge=100, le=2500)
    treasury_ratio_bps: int = Field(..., ge=1000, le=9000)


class ModelStatus(BaseModel):
    connected:   bool
    model_path:  str | None = None
    step_count:  int = 0
    last_action: dict | None = None
    last_reward: float | None = None
    running:     bool = False


@router.get("/observe")
def observe():
    """Return current on-chain state formatted as RL agent observation."""
    try:
        state  = treasury.functions.getProtocolState().call()
        params = token.functions.getParameters().call()
        supply = token.functions.totalSupply().call()
        price  = treasury.functions.paytknPriceUsd().call()

        on_chain_params = {
            "mint_factor":        params[0],
            "burn_rate_bps":      params[1],
            "reward_alloc_bps":   params[2],
            "cashback_base_bps":  params[3],
            "merchant_alloc_bps": params[4],
            "treasury_ratio_bps": params[5],
        }
        _params_cache.update(on_chain_params)

        return {
            "token_price":           price / 1e8,
            "treasury_stable_ratio": state[0] / 1e18,
            "treasury_paytkn":       state[1] / 1e18,
            "staking_ratio":         state[2] / max(supply, 1),
            "reward_pool":           state[3] / 1e18,
            "current_apy_bps":       state[4],
            "total_supply":          supply / 1e18,
            "total_payments":        state[7],
            "total_fees_eth":        state[8] / 1e18,
            "merchant_pool":         state[9] / 1e18,
            "payment_volume_usd":    state[7] * 50,   # mock volume
            "current_params":        on_chain_params,
            "model_status":          _model_status,
        }
    except Exception as e:
        # Return cached params if chain is unreachable
        return {
            "token_price":           1.00,
            "treasury_stable_ratio": 0.5,
            "staking_ratio":         0.08,
            "reward_pool":           50000,
            "current_apy_bps":       800,
            "total_supply":          12_000_000,
            "total_payments":        47,
            "payment_volume_usd":    2350,
            "current_params":        _params_cache,
            "model_status":          _model_status,
            "_source":               "cache",
            "_error":                str(e),
        }


@router.post("/update-params")
def update_params(action: AgentAction):
    """Push new economic parameters on-chain. Falls back to sim if tx reverts."""
    action_dict = action.model_dump()

    # Try on-chain first
    try:
        tx = send_tx(token.functions.updateParameters(
            action.mint_factor,
            action.burn_rate_bps,
            action.reward_alloc_bps,
            action.cashback_base_bps,
            action.merchant_alloc_bps,
            action.treasury_ratio_bps,
        ))
        _params_cache.update(action_dict)
        return {
            "status":    "on_chain",
            "tx_hash":   tx,
            "params":    action_dict,
            "basescan":  f"https://sepolia.basescan.org/tx/{tx}",
        }
    except Exception as chain_err:
        # Simulation fallback — update cache, return simulated tx hash
        _params_cache.update(action_dict)
        import hashlib, time
        fake_hash = "0x" + hashlib.sha256(
            f"{action_dict}{time.time()}".encode()
        ).hexdigest()
        return {
            "status":    "simulated",
            "tx_hash":   fake_hash,
            "params":    action_dict,
            "note":      "Parameters updated in simulation (on-chain tx failed: " + str(chain_err)[:80] + ")",
        }


@router.post("/burn")
def trigger_burn():
    """Agent triggers daily treasury burn."""
    try:
        tx = send_tx(treasury.functions.executeDailyBurn())
        return {"status": "on_chain", "tx_hash": tx,
                "basescan": f"https://sepolia.basescan.org/tx/{tx}"}
    except Exception as e:
        import hashlib, time
        fake = "0x" + hashlib.sha256(f"burn{time.time()}".encode()).hexdigest()
        return {"status": "simulated", "tx_hash": fake,
                "paytkn_burned": round(_params_cache["burn_rate_bps"] * 120000 / 10000, 2),
                "note": str(e)[:80]}


@router.post("/mint")
def trigger_mint(amount_paytkn: float):
    """Agent triggers adaptive mint."""
    try:
        amount_wei = int(amount_paytkn * 1e18)
        tx = send_tx(treasury.functions.executeMint(amount_wei))
        return {"status": "on_chain", "tx_hash": tx, "paytkn_minted": amount_paytkn,
                "basescan": f"https://sepolia.basescan.org/tx/{tx}"}
    except Exception as e:
        import hashlib, time
        fake = "0x" + hashlib.sha256(f"mint{time.time()}".encode()).hexdigest()
        return {"status": "simulated", "tx_hash": fake,
                "paytkn_minted": amount_paytkn, "note": str(e)[:80]}


@router.get("/params")
def get_params():
    """Return current cached parameters (used by frontend when on-chain read fails)."""
    return {"params": _params_cache, "model_status": _model_status}


@router.post("/model-status")
def update_model_status(status: ModelStatus):
    """Called by the RL model server to report its state."""
    _model_status.update(status.model_dump())
    return {"acknowledged": True}
