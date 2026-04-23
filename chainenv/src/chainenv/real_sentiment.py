"""Real market sentiment converter.

Converts historical token price data into a daily sentiment sequence [0, 1]
using the same signal formula as MarketSentiment.update(), but driven by
real price returns instead of simulated ones.

This allows the ChainEnv simulator to replay real crypto market conditions
(CELO 2020-2025, MATIC 2021-2026, etc.) while keeping the economic simulation
(treasury, AMM, staking, population) fully active and policy-controlled.

Signal formula (mirrors MarketSentiment):
  momentum  = tanh(daily_return × 10)          [40% weight]
  vol_signal = -tanh(7d_volatility × 5)         [30% weight]
  trend      = tanh(30d_return × 3)             [30% weight]
  raw        = 0.40×momentum + 0.30×vol + 0.30×trend
  nudge      = raw × 0.06
  new_value  = prev + nudge + drift×(0.5 - prev) + N(0, 0.008)
"""

from __future__ import annotations
import json
import os
import numpy as np
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# Core converter
# ─────────────────────────────────────────────────────────────

def prices_to_sentiment(
    prices: list[float],
    initial_sentiment: float = 0.5,
    mean_reversion: float = 0.025,
    noise_std: float = 0.008,
    rng_seed: int = 42,
) -> list[float]:
    """Convert daily close prices → daily sentiment sequence.

    Args:
        prices:             Daily close prices (chronological).
        initial_sentiment:  Starting sentiment value [0, 1].
        mean_reversion:     Pull-toward-0.5 strength per day.
        noise_std:          Gaussian noise added each day.
        rng_seed:           For reproducibility.

    Returns:
        List of daily sentiment values in [0, 1], same length as prices.
    """
    n   = len(prices)
    rng = np.random.default_rng(rng_seed)
    seq = np.zeros(n, dtype=np.float64)
    seq[0] = float(np.clip(initial_sentiment, 0.0, 1.0))

    prices_arr = np.array(prices, dtype=np.float64)

    for i in range(1, n):
        p_now  = prices_arr[i]
        p_prev = prices_arr[i - 1]

        # ── Daily return momentum ──────────────────────────────
        daily_ret  = (p_now - p_prev) / (p_prev + 1e-10)
        momentum   = float(np.tanh(daily_ret * 10.0))

        # ── 7-day rolling volatility ──────────────────────────
        win7       = prices_arr[max(0, i - 6) : i + 1]
        vol7       = float(np.std(win7) / (np.mean(win7) + 1e-10))
        vol_signal = -float(np.tanh(vol7 * 5.0))

        # ── 30-day trend ──────────────────────────────────────
        p_30ago    = prices_arr[max(0, i - 30)]
        trend_ret  = (p_now - p_30ago) / (p_30ago + 1e-10)
        trend      = float(np.tanh(trend_ret * 3.0))

        # ── Composite signal ──────────────────────────────────
        raw   = 0.40 * momentum + 0.30 * vol_signal + 0.30 * trend
        nudge = raw * 0.06

        # ── Update with mean reversion + noise ────────────────
        new_val  = seq[i - 1] + nudge
        new_val += mean_reversion * (0.5 - new_val)
        new_val += float(rng.normal(0.0, noise_std))

        seq[i] = float(np.clip(new_val, 0.0, 1.0))

    return seq.tolist()


# ─────────────────────────────────────────────────────────────
# Data loader
# ─────────────────────────────────────────────────────────────

def load_token_data(token: str, data_dir: str = "data") -> dict:
    """Load a fetched token JSON file.

    Args:
        token:    One of 'celo', 'matic', 'algo', 'btc'.
        data_dir: Directory where fetch_market_data.py saved files.

    Returns:
        Dict with keys: token, dates, close_prices, volumes, n_days, ...
    """
    path = Path(data_dir) / f"{token}_daily.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Data file not found: {path}\n"
            f"Run: python scripts/fetch_market_data.py"
        )
    with open(path) as f:
        return json.load(f)


def build_sentiment_sequence(
    token: str,
    data_dir: str = "data",
    episode_days: int = 1825,
    rng_seed: int = 42,
) -> tuple[list[float], dict]:
    """Load token data and build a sentiment sequence for one episode.

    Returns:
        (sentiment_sequence, token_metadata)
        sentiment_sequence: list of `episode_days` floats in [0, 1]
        token_metadata:     dict with dates, price stats, etc.
    """
    data   = load_token_data(token, data_dir)
    prices = data["close_prices"]

    # Trim / pad to episode_days
    if len(prices) >= episode_days:
        prices = prices[-episode_days:]          # most recent N days
    else:
        # Pad with last known price if data is shorter
        prices = prices + [prices[-1]] * (episode_days - len(prices))

    sentiment = prices_to_sentiment(prices, rng_seed=rng_seed)

    meta = {
        "token":      data["token"],
        "label":      data.get("label", token.upper()),
        "start_date": data["dates"][-episode_days] if len(data["dates"]) >= episode_days
                      else data["dates"][0],
        "end_date":   data["dates"][-1],
        "n_days":     episode_days,
        "prices":     prices,
        "dates":      (data["dates"][-episode_days:] if len(data["dates"]) >= episode_days
                       else data["dates"]),
        "price_start": prices[0],
        "price_end":   prices[-1],
        "price_min":   float(min(prices)),
        "price_max":   float(max(prices)),
        "return_pct":  (prices[-1] / prices[0] - 1) * 100,
        "sentiment_avg":  float(np.mean(sentiment)),
        "sentiment_min":  float(np.min(sentiment)),
        "sentiment_max":  float(np.max(sentiment)),
        "bear_days":   int(sum(1 for s in sentiment if s < 0.35)),
        "bull_days":   int(sum(1 for s in sentiment if s > 0.65)),
        "neutral_days":int(sum(1 for s in sentiment if 0.35 <= s <= 0.65)),
    }

    return sentiment, meta


# ─────────────────────────────────────────────────────────────
# Composite (all 4 tokens averaged)
# ─────────────────────────────────────────────────────────────

TOKENS = ["celo", "matic", "algo", "btc"]


def build_composite_sentiment(
    tokens: list[str] | None = None,
    weights: list[float] | None = None,
    data_dir: str = "data",
    episode_days: int = 1825,
    rng_seed: int = 42,
) -> tuple[list[float], dict]:
    """Weighted average sentiment across multiple tokens.

    Default weights: CELO 35%, MATIC 25%, ALGO 20%, BTC 20%
    (CELO weighted highest — closest to PAYTKN's use case)

    Returns:
        (composite_sentiment, metadata_dict_per_token)
    """
    tokens  = tokens  or TOKENS
    weights = weights or [0.35, 0.25, 0.20, 0.20]

    if len(tokens) != len(weights):
        raise ValueError("tokens and weights must have same length")

    total_w = sum(weights)
    weights = [w / total_w for w in weights]   # normalise

    sequences = []
    metas     = {}

    for tok, w in zip(tokens, weights):
        seq, meta = build_sentiment_sequence(
            tok, data_dir=data_dir,
            episode_days=episode_days,
            rng_seed=rng_seed,
        )
        sequences.append((np.array(seq) * w))
        metas[tok] = meta

    composite = np.sum(sequences, axis=0)
    composite = np.clip(composite, 0.0, 1.0)

    composite_meta = {
        "type":    "composite",
        "tokens":  tokens,
        "weights": weights,
        "tokens_meta": metas,
        "sentiment_avg":   float(np.mean(composite)),
        "sentiment_min":   float(np.min(composite)),
        "sentiment_max":   float(np.max(composite)),
        "bear_days":   int(sum(1 for s in composite if s < 0.35)),
        "bull_days":   int(sum(1 for s in composite if s > 0.65)),
        "neutral_days":int(sum(1 for s in composite if 0.35 <= s <= 0.65)),
    }

    return composite.tolist(), composite_meta


# ─────────────────────────────────────────────────────────────
# Quick diagnostics
# ─────────────────────────────────────────────────────────────

def print_sentiment_summary(meta: dict) -> None:
    if meta.get("type") == "composite":
        print(f"  Composite sentiment ({', '.join(meta['tokens'])})")
        for tok, tm in meta["tokens_meta"].items():
            print(f"    {tok.upper():6s}  {tm['start_date']} → {tm['end_date']}  "
                  f"return={tm['return_pct']:+.1f}%  "
                  f"bear={tm['bear_days']}d  bull={tm['bull_days']}d")
    else:
        print(f"  {meta['label']}")
        print(f"  Period:  {meta['start_date']} → {meta['end_date']}")
        print(f"  Return:  {meta['return_pct']:+.1f}%")
        print(f"  Price:   ${meta['price_start']:.4f} → ${meta['price_end']:.4f}")
    print(f"  Sentiment: avg={meta['sentiment_avg']:.3f}  "
          f"bear={meta['bear_days']}d  "
          f"neutral={meta['neutral_days']}d  "
          f"bull={meta['bull_days']}d")
