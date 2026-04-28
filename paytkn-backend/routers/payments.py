"""Payment processing endpoints."""
import hashlib, time as _time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from web3 import Web3
from contracts import treasury, reward_engine, send_tx, w3, account

router = APIRouter(prefix="/payments", tags=["Payments"])


class PaymentRequest(BaseModel):
    user_address:     str
    merchant_address: str
    amount_eth:       float  # payment amount in ETH (stand-in for stable)


def _record_payment(req: PaymentRequest, tx_hash: str, cashback: float, cashback_bps: int, on_chain: bool):
    """Record payment into the demo history for dashboard display."""
    try:
        from routers.demo import payment_history
        usd_val = round(req.amount_eth * 3100, 2)
        payment_history.insert(0, {
            "id":       tx_hash,
            "type":     "payment",
            "desc":     f"Payment → {req.merchant_address[:8]}…{req.merchant_address[-4:]}",
            "amount":   f"-${usd_val:,.2f}",
            "paytkn":   f"+{cashback:.4f} PAYTKN",
            "time":     "just now",
            "status":   "confirmed" if on_chain else "confirmed (sim)",
            "currency": "ETH",
            "cashback_bps": cashback_bps,
            "tx_hash":  tx_hash,
        })
    except Exception:
        pass  # Never let recording break the payment response


@router.post("/process")
def process_payment(req: PaymentRequest):
    """
    Simulate a PAYTKN payment.
    Treasury receives 0.5% fee, mints cashback to user, routes fees.
    """
    try:
        user     = Web3.to_checksum_address(req.user_address)
        merchant = Web3.to_checksum_address(req.merchant_address)
        amount   = Web3.to_wei(req.amount_eth, "ether")

        tx = send_tx(
            treasury.functions.processPayment(user, merchant),
            value_wei=amount,
        )

        # Get cashback estimate from RewardEngine
        params = treasury.functions.getProtocolState().call()
        token_params = None
        try:
            from contracts import token
            token_params = token.functions.getParameters().call()
            cashback_bps = token_params[3]
        except:
            cashback_bps = 50

        price = treasury.functions.paytknPriceUsd().call()

        cashback_paytkn = round(req.amount_eth * cashback_bps / 10000 * 1e8 / price, 4)
        _record_payment(req, tx, cashback_paytkn, cashback_bps, on_chain=True)
        return {
            "status":        "success",
            "tx_hash":       tx,
            "payment_eth":   req.amount_eth,
            "fee_eth":       round(req.amount_eth * 0.005, 6),
            "cashback_bps":  cashback_bps,
            "cashback_paytkn": cashback_paytkn,
            "estimated_cashback_paytkn": cashback_paytkn,
            "basescan": f"https://sepolia.basescan.org/tx/{tx}",
        }
    except Exception as e:
        # Simulation fallback — still record so dashboards update
        fake_hash = "0x" + hashlib.sha256(f"pay{req.user_address}{_time.time()}".encode()).hexdigest()
        cashback_bps = 50
        cashback_paytkn = round(req.amount_eth * cashback_bps / 10000 * 3100, 4)
        _record_payment(req, fake_hash, cashback_paytkn, cashback_bps, on_chain=False)
        return {
            "status":        "simulated",
            "tx_hash":       fake_hash,
            "payment_eth":   req.amount_eth,
            "fee_eth":       round(req.amount_eth * 0.005, 6),
            "cashback_bps":  cashback_bps,
            "cashback_paytkn": cashback_paytkn,
            "estimated_cashback_paytkn": cashback_paytkn,
            "note":          f"Payment simulated (on-chain error: {str(e)[:60]})",
        }


@router.get("/stats")
def payment_stats():
    state = treasury.functions.getProtocolState().call()
    return {
        "total_payments":   state[7],
        "total_fees_eth":   Web3.from_wei(state[8], "ether"),
        "merchant_pool_paytkn": Web3.from_wei(state[9], "ether"),
    }
