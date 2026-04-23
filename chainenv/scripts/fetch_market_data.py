"""Fetch real historical price data via yfinance for 4 tokens.

No API key required. Uses Yahoo Finance (free, reliable).

Usage:
    cd chainenv
    pip install yfinance          # one-time install
    python scripts/fetch_market_data.py

Outputs (one file per token):
    data/celo_daily.json
    data/matic_daily.json
    data/algo_daily.json
    data/btc_daily.json
"""

from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone

try:
    import yfinance as yf
except ImportError:
    print("yfinance not installed. Run:  pip install yfinance")
    sys.exit(1)


TOKENS = {
    "celo": {
        "ticker": "CELO-USD",
        "label":  "CELO — Payment utility token (closest to PAYTKN)",
        "period": "5y",
    },
    "matic": {
        "ticker": "MATIC-USD",
        "label":  "MATIC/POL — High growth + 2022 crash",
        "period": "5y",
    },
    "algo": {
        "ticker": "ALGO-USD",
        "label":  "ALGO — Payment focus, survived bear",
        "period": "5y",
    },
    "btc": {
        "ticker": "BTC-USD",
        "label":  "BTC — Best broad market sentiment proxy",
        "period": "5y",
    },
}


def fetch_token(name: str, cfg: dict) -> dict:
    ticker = cfg["ticker"]
    print(f"  Downloading {ticker} ({cfg['period']})...", end=" ", flush=True)

    tkr  = yf.Ticker(ticker)
    hist = tkr.history(period=cfg["period"], interval="1d", auto_adjust=True)

    if hist.empty:
        raise RuntimeError(f"No data returned for {ticker}")

    # Drop timezone from index so strftime works uniformly
    hist.index = hist.index.tz_localize(None) if hist.index.tz is None else hist.index.tz_convert(None)

    dates        = [d.strftime("%Y-%m-%d") for d in hist.index]
    close_prices = [float(v) for v in hist["Close"]]
    volumes      = [float(v) for v in hist["Volume"]]

    print(f"{len(dates)} days  ({dates[0]} -> {dates[-1]})")

    return {
        "token":   name,
        "ticker":  ticker,
        "label":   cfg["label"],
        "dates":        dates,
        "close_prices": close_prices,
        "volumes":      volumes,
        "n_days":       len(dates),
        "start_date":   dates[0],
        "end_date":     dates[-1],
        "price_min":    float(min(close_prices)),
        "price_max":    float(max(close_prices)),
        "price_start":  close_prices[0],
        "price_end":    close_prices[-1],
        "return_pct":   (close_prices[-1] / close_prices[0] - 1) * 100,
    }


def main():
    os.makedirs("data", exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  ChainEnv — Real Market Data Fetch")
    print(f"  Source: Yahoo Finance (via yfinance)")
    print(f"  Tokens: {', '.join(TOKENS.keys()).upper()}")
    print(f"{'='*60}\n")

    for name, cfg in TOKENS.items():
        print(f"[{name.upper()}] {cfg['label']}")
        try:
            data = fetch_token(name, cfg)

            path = f"data/{name}_daily.json"
            with open(path, "w") as f:
                json.dump(data, f, indent=2)

            print(f"  Price range: ${data['price_min']:.4f} -> ${data['price_max']:.4f}")
            print(f"  Total return: {data['return_pct']:+.1f}%")
            print(f"  Saved -> {path}\n")

        except Exception as e:
            print(f"  ERROR: {e}\n")
            sys.exit(1)

    print("All tokens fetched successfully.")
    print("Next step: python scripts/historical_eval.py --model models/best_model.zip")


if __name__ == "__main__":
    main()
