"""Web3 contract interface — single source of truth for all on-chain calls."""
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account
from config import settings, ADDRESSES, load_abi

# ── Provider ──────────────────────────────────────────────────────────
w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

# ── Deployer account (operator wallet) ───────────────────────────────
account = Account.from_key(settings.private_key)

# ── Contracts ─────────────────────────────────────────────────────────
token = w3.eth.contract(
    address=Web3.to_checksum_address(ADDRESSES["token"]),
    abi=load_abi("PaytknToken"),
)
staking = w3.eth.contract(
    address=Web3.to_checksum_address(ADDRESSES["staking"]),
    abi=load_abi("PaytknStaking"),
)
merchant_staking = w3.eth.contract(
    address=Web3.to_checksum_address(ADDRESSES["merchantStaking"]),
    abi=load_abi("MerchantStaking"),
)
reward_engine = w3.eth.contract(
    address=Web3.to_checksum_address(ADDRESSES["rewardEngine"]),
    abi=load_abi("RewardEngine"),
)
treasury = w3.eth.contract(
    address=Web3.to_checksum_address(ADDRESSES["treasury"]),
    abi=load_abi("PaytknTreasury"),
)


def send_tx(fn, value_wei: int = 0) -> str:
    """Build, sign, and send a contract transaction. Returns tx hash."""
    nonce = w3.eth.get_transaction_count(account.address)
    tx = fn.build_transaction({
        "from":     account.address,
        "nonce":    nonce,
        "gas":      500_000,
        "gasPrice": w3.eth.gas_price,
        "value":    value_wei,
        "chainId":  settings.chain_id,
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt["status"] != 1:
        raise RuntimeError(f"Transaction reverted: {tx_hash.hex()}")
    return tx_hash.hex()
