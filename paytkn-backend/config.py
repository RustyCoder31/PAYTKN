import json
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    rpc_url:     str = "https://sepolia.base.org"
    private_key: str = ""
    chain_id:    int = 84532

    model_config = {"env_file": ".env"}


settings = Settings()

# Load deployed contract addresses
_addr_file = Path(__file__).parent / "deployed-addresses.json"
with open(_addr_file) as f:
    ADDRESSES = json.load(f)


def load_abi(name: str) -> list:
    path = Path(__file__).parent / "abis" / f"{name}.json"
    with open(path) as f:
        return json.load(f)["abi"]
