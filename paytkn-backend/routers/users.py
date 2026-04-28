"""User profile endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from web3 import Web3
from contracts import token, reward_engine, send_tx

router = APIRouter(prefix="/users", tags=["Users"])


class RegisterRequest(BaseModel):
    address:    str
    invited_by: str = "0x0000000000000000000000000000000000000000"


@router.post("/register")
def register_user(req: RegisterRequest):
    try:
        user    = Web3.to_checksum_address(req.address)
        inviter = Web3.to_checksum_address(req.invited_by)
        tx = send_tx(reward_engine.functions.registerUser(user, inviter))
        return {"status": "success", "tx_hash": tx, "address": user,
                "basescan": f"https://sepolia.basescan.org/tx/{tx}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{address}/profile")
def get_profile(address: str):
    addr = Web3.to_checksum_address(address)
    try:
        profile = reward_engine.functions.getUserProfile(addr).call()
        boosts  = reward_engine.functions.getUserBoosts(addr).call()
        balance = token.functions.balanceOf(addr).call()

        return {
            "address":           address,
            "registered":        profile[7],
            "balance_paytkn":    Web3.from_wei(balance, "ether"),
            "loyalty_score":     profile[1],
            "loyalty_pct":       round(profile[1] / 100, 1),
            "total_transactions":profile[5],
            "invite_depth":      profile[4],
            "invited_by":        profile[6],
            "boosts": {
                "loyalty_bps":   boosts[0],
                "seniority_bps": boosts[1],
                "invite_bps":    boosts[2],
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{address}/balance")
def get_balance(address: str):
    addr    = Web3.to_checksum_address(address)
    balance = token.functions.balanceOf(addr).call()
    return {
        "address":        address,
        "balance_paytkn": Web3.from_wei(balance, "ether"),
        "balance_wei":    balance,
    }
