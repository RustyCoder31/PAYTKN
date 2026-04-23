"""Fetch real historical price data from CoinGecko for 4 tokens.

Usage:
    cd chainenv
    python scripts/fetch_market_data.py

Outputs (one file per token):
    data/celo_daily.json
    data/matic_daily.json
    data/algo_daily.json
    data/btc_daily.json

Each file contains daily close prices + volumes for the configured period.
No API key required (CoinGecko free tier).
"""

from __future__ import annotations
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone


TOKENS = {
    "celo": {
        "id":    "celo",
        "label": "CELO — Payment utility token (closest to PAYTKN)",
        "days":  1825,   # 5 years: Sep 2020 → Sep 2025
    },
    "matic": {
        "id":    "matic-network",
        "label": "MATIC/POL — High growth + 2022 crash",
        "days":  1825,   # 5 years: Apr 2021 → Apr 2026
    },
    "algo": {
        "id":    "algorand",
        "label": "ALGO — Payment focus, survived bear",
        "days":  1825,   # 5 years: Apr 2021 → Apr 2026
    },
    "btc": {
        "id":    "bitcoin",
        "label": "BTC — Best broad market sentiment proxy",
        "days":  1825,   # 5 years: Apr 2020 → Apr 2025
    },
}

BASE_URL = "https://api.coingecko.com/api/v3"


def fetch_market_chart(coin_id: str, days: int, retries: int = 3) -> dict:
    """Fetch daily OHLCV from CoinGecko free API."""
    url = (
        f"{BASE_URL}/coins/{coin_id}/market_chart"
        f"?vs_currency=usd&days={days}&interval=daily"
    )
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "chainenv-research/1.0"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 60 * (attempt + 1)
                print(f"    Rate limited — waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
        except Exception as e:
            if attempt < retries - 1:
                print(f"    Error ({e}) — retrying in 10s...")
                time.sleep(10)
            else:
                raise
    raise RuntimeError(f"Failed after {retries} retries")


def fetch_ohlc(coin_id: str, days: int, retries: int = 3) -> list:
    """Fetch daily OHLC candles from CoinGecko."""
    # CoinGecko OHLC endpoint: returns [timestamp, open, high, low, close]
    # days must be 1, 7, 14, 30, 90, 180, 365, or 'max'
    # For 1825 days we use 'max' and trim to last 1825 days
    url = (
        f"{BASE_URL}/coins/{coin_id}/ohlc"
        f"?vs_currency=usd&days=max"
    )
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "chainenv-research/1.0"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 60 * (attempt + 1)
                print(f"    Rate limited (OHLC) — waiting {wait}s...")
                time.sleep(wait)
            elif e.code == 404:
                return []   # endpoint not available for this coin
            else:
                raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(10)
            else:
                return []
    return []


def process_market_chart(data: dict, days: int) -> dict:
    """Extract and clean daily price/volume series."""
    prices  = data.get("prices",        [])
    volumes = data.get("total_volumes", [])

    # CoinGecko returns one point per day (midnight UTC)
    # Trim to last `days` entries in case API returns more
    prices  = prices[-days:]
    volumes = volumes[-days:]

    close_prices = [p[1] for p in prices]
    vol_values   = [v[1] for v in volumes]
    timestamps   = [p[0] for p in prices]

    dates = [
        datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        for ts in timestamps
    ]

    return {
        "dates":        dates,
        "close_prices": close_prices,
        "volumes":      vol_values,
        "n_days":       len(close_prices),
        "start_date":   dates[0]  if dates else "",
        "end_date":     dates[-1] if dates else "",
        "price_min":    min(close_prices) if close_prices else 0,
        "price_max":    max(close_prices) if close_prices else 0,
        "price_start":  close_prices[0]  if close_prices else 0,
        "price_end":    close_prices[-1] if close_prices else 0,
        "return_pct":   (close_prices[-1] / close_prices[0] - 1) * 100
                        if len(close_prices) >= 2 else 0,
    }


def main():
    os.makedirs("data", exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  ChainEnv — Real Market Data Fetch")
    print(f"  Source: CoinGecko Free API")
    print(f"  Tokens: {', '.join(TOKENS.keys()).upper()}")
    print(f"{'='*60}\n")

    for name, meta in TOKENS.items():
        print(f"[{name.upper()}] {meta['label']}")
        try:
            raw = fetch_market_chart(meta["id"], meta["days"])
            processed = process_market_chart(raw, meta["days"])

            out = {
                "token":        name,
                "coingecko_id": meta["id"],
                "label":        meta["label"],
                **processed,
            }

            path = f"data/{name}_daily.json"
            with open(path, "w") as f:
                json.dump(out, f, indent=2)

            print(f"  Days:        {processed['n_days']}")
            print(f"  Period:      {processed['start_date']} → {processed['end_date']}")
            print(f"  Price range: ${processed['price_min']:.4f} → ${processed['price_max']:.4f}")
            print(f"  Total return:{processed['return_pct']:+.1f}%")
            print(f"  Saved  ->    {path}\n")

        except Exception as e:
            print(f"  ERROR: {e}\n")
            sys.exit(1)

        # Respect CoinGecko free tier rate limit (10-30 req/min)
        if name != list(TOKENS.keys())[-1]:
            print("  Waiting 3s (rate limit)...")
            time.sleep(3)

    print("All tokens fetched successfully.")
    print("Next step: python scripts/historical_eval.py --model models/best_model.zip")


if __name__ == "__main__":
    main()
