"""
Demo data seeder — creates realistic transaction history for FYP presentation.
Provides /demo/seed, /demo/history/{address}, /demo/economy endpoints.
Payment history is also appended to by payments.py on each real payment.
"""
import hashlib, random, time
from fastapi import APIRouter

router = APIRouter(prefix="/demo", tags=["Demo"])

# ── Shared in-memory stores (mutated by payments.py too) ─────────────────────
payment_history: list = []

staking_positions: list = [
    {"id": "stake_1", "amount": 500,  "lock_days": 90,  "apy_pct": 12.0, "rewards_earned": 12.5,  "locked_until": "Jul 26, 2026", "status": "locked"},
    {"id": "stake_2", "amount": 1000, "lock_days": 180, "apy_pct": 25.0, "rewards_earned": 27.3,  "locked_until": "Oct 24, 2026", "status": "locked"},
    {"id": "stake_3", "amount": 200,  "lock_days": 0,   "apy_pct": 5.0,  "rewards_earned": 2.1,   "locked_until": None,           "status": "flexible"},
]

referrals: list = [
    {"level": 1, "address": "0xABCD…1234", "joined": "14d ago", "earned": 5.0},
    {"level": 1, "address": "0xEF12…5678", "joined": "22d ago", "earned": 5.0},
    {"level": 1, "address": "0x9876…ABCD", "joined": "31d ago", "earned": 5.0},
    {"level": 2, "address": "0x5432…EF90", "joined": "25d ago", "earned": 2.0},
    {"level": 3, "address": "0x1234…CDEF", "joined": "38d ago", "earned": 0.5},
]

seeded: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────
def _fake_hash(seed: str) -> str:
    return "0x" + hashlib.sha256(f"{seed}{random.random()}".encode()).hexdigest()


def _time_ago(hours: float) -> str:
    if hours < 1:
        return f"{int(hours * 60)}m ago"
    if hours < 24:
        return f"{int(hours)}h ago"
    return f"{int(hours / 24)}d ago"


# ── Seed template ─────────────────────────────────────────────────────────────
_SEED_TRANSACTIONS = [
    {"type": "payment",  "desc": 'TechMart Store — MacBook Pro 14"', "amount": "-$1,299",     "paytkn": "+9.74 PAYTKN",  "hours_ago": 2,   "currency": "ETH"},
    {"type": "staking",  "desc": "Stake PAYTKN — 90 day lock",        "amount": "-500 PAYTKN", "paytkn": "Staking",       "hours_ago": 26,  "currency": "PAYTKN"},
    {"type": "rewards",  "desc": "Epoch 14 staking reward",           "amount": "",            "paytkn": "+12.5 PAYTKN",  "hours_ago": 50,  "currency": None},
    {"type": "payment",  "desc": "TechMart Store — AirPods Pro 2nd",  "amount": "-$249",       "paytkn": "+1.87 PAYTKN",  "hours_ago": 74,  "currency": "USDC"},
    {"type": "rewards",  "desc": "Referral reward — Level 1 invite",  "amount": "",            "paytkn": "+5.0 PAYTKN",   "hours_ago": 98,  "currency": None},
    {"type": "staking",  "desc": "Unstake PAYTKN — flexible lock",    "amount": "+200 PAYTKN", "paytkn": "",              "hours_ago": 122, "currency": "PAYTKN"},
    {"type": "trading",  "desc": "Buy PAYTKN on DEX (Uniswap v3)",   "amount": "-0.01 ETH",   "paytkn": "+31 PAYTKN",    "hours_ago": 146, "currency": "ETH"},
    {"type": "payment",  "desc": "TechMart Store — Sony WH-1000XM5",  "amount": "-$349",       "paytkn": "+2.62 PAYTKN",  "hours_ago": 170, "currency": "BNB"},
    {"type": "rewards",  "desc": "Epoch 13 staking reward",           "amount": "",            "paytkn": "+11.2 PAYTKN",  "hours_ago": 218, "currency": None},
    {"type": "payment",  "desc": "TechMart Pro — Monthly subscription","amount": "-$9.99",      "paytkn": "+0.075 PAYTKN", "hours_ago": 266, "currency": "USDC"},
    {"type": "rewards",  "desc": "Cashback — RL Agent Epoch 12",      "amount": "",            "paytkn": "+0.262 PAYTKN", "hours_ago": 290, "currency": None},
    {"type": "staking",  "desc": "Stake PAYTKN — 30 day lock",        "amount": "-200 PAYTKN", "paytkn": "Staking",       "hours_ago": 314, "currency": "PAYTKN"},
    {"type": "payment",  "desc": "TechMart Store — Mechanical Keyboard","amount": "-$159",     "paytkn": "+1.19 PAYTKN",  "hours_ago": 338, "currency": "MATIC"},
    {"type": "rewards",  "desc": "Epoch 12 staking reward",           "amount": "",            "paytkn": "+9.8 PAYTKN",   "hours_ago": 386, "currency": None},
    {"type": "trading",  "desc": "Initial PAYTKN purchase",           "amount": "-0.05 ETH",   "paytkn": "+155 PAYTKN",   "hours_ago": 720, "currency": "ETH"},
]


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.post("/seed")
def seed_demo():
    """Populate in-memory stores with realistic demo economy data."""
    global payment_history, seeded

    payment_history.clear()
    payment_history.extend([
        {
            "id":     _fake_hash(f"tx{i}"),
            "type":   tx["type"],
            "desc":   tx["desc"],
            "amount": tx["amount"],
            "paytkn": tx["paytkn"],
            "time":   _time_ago(tx["hours_ago"]),
            "status": "confirmed",
            "currency": tx.get("currency"),
        }
        for i, tx in enumerate(_SEED_TRANSACTIONS)
    ])
    seeded = True

    return {
        "status": "seeded",
        "transactions": len(payment_history),
        "staking_positions": len(staking_positions),
        "referrals": len(referrals),
    }


@router.get("/history/{address}")
def get_history(address: str):
    """Return transaction history + staking positions for an address."""
    return {
        "history":           payment_history,
        "staking_positions": staking_positions,
        "referrals":         referrals,
        "seeded":            seeded,
    }


@router.get("/economy")
def economy():
    """Economy-level stats for the main dashboard."""
    pay_txs = [t for t in payment_history if t["type"] == "payment"]
    return {
        "total_transactions":    len(payment_history),
        "payment_count":         len(pay_txs),
        "total_volume_usd":      1907.98 + len(pay_txs) * 50,
        "total_cashback_paytkn": 47.55 + len(pay_txs) * 0.5,
        "unique_users":          3,
        "active_subscriptions":  2,
        "seeded":                seeded,
    }
