"""
PAYTKN RL Model Server
======================
Loads the trained PPO policy and serves RL actions over HTTP.
The backend agent router polls /action every day tick.

Usage:
    python scripts/model_server.py \
        --model ../models_v4/models/paytkn_v4_5yr_final.zip \
        --port 8001

Endpoints:
    GET  /status   — model info + step count
    POST /action   — receive observation dict, return action dict
    POST /shutdown — graceful stop
"""
from __future__ import annotations

import argparse
import json
import threading
import time
import os
import sys
from typing import Any

import numpy as np
import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ─── Try to import SB3 ────────────────────────────────────────────────────────
try:
    from stable_baselines3 import PPO
    SB3_AVAILABLE = True
except ImportError:
    SB3_AVAILABLE = False
    print("[model_server] stable-baselines3 not installed — running in mock mode")

# ─── Argument parsing ─────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="PAYTKN RL model server")
parser.add_argument("--model",  default="../models_v4/models/paytkn_v4_5yr_final.zip",
                    help="Path to trained SB3 PPO model (.zip)")
parser.add_argument("--port",   type=int, default=8001)
parser.add_argument("--backend",default="http://localhost:8000",
                    help="Backend base URL for status registration")
args, _ = parser.parse_known_args()

# ─── Model loading ────────────────────────────────────────────────────────────
_model = None
_step_count: int = 0
_last_action: dict | None = None
_last_reward: float | None = None
_lock = threading.Lock()

# ActionBounds (must match chainenv/config.py ActionBounds)
ACTION_BOUNDS = {
    "mint_factor":        (0.0,   2.0),
    "burn_rate":          (0.0,   0.0005),
    "reward_alloc":       (0.20,  0.60),
    "cashback_base_rate": (0.001, 0.010),
    "merchant_pool_alloc":(0.05,  0.25),
    "treasury_ratio":     (0.50,  0.90),
}

# Map continuous action [0-1] → bps integer for the backend API
def _action_to_bps(name: str, value: float) -> int:
    lo, hi = ACTION_BOUNDS[name]
    clipped = float(np.clip(value, lo, hi))
    if name == "mint_factor":
        return int(clipped * 100)            # 0–200
    elif name == "burn_rate":
        return int(clipped * 10_000)         # 0–5 bps
    elif name == "reward_alloc":
        return int(clipped * 10_000)         # 2000–6000 bps
    elif name == "cashback_base_rate":
        return int(clipped * 10_000)         # 10–100 bps
    elif name == "merchant_pool_alloc":
        return int(clipped * 10_000)         # 500–2500 bps
    elif name == "treasury_ratio":
        return int(clipped * 10_000)         # 5000–9000 bps
    return int(clipped * 10_000)

def _load_model(path: str) -> bool:
    global _model
    if not SB3_AVAILABLE:
        return False
    if not os.path.exists(path):
        print(f"[model_server] Model not found: {path}")
        return False
    try:
        _model = PPO.load(path)
        print(f"[model_server] Loaded model from {path}")
        return True
    except Exception as e:
        print(f"[model_server] Failed to load model: {e}")
        return False

def _obs_dict_to_array(obs: dict) -> np.ndarray:
    """Convert observation dict from /agent/observe to a 24-dim numpy array.

    Observation order must match PaytknEnv._build_obs() in env.py.
    """
    def g(key: str, default: float = 0.0) -> float:
        return float(obs.get(key, default))

    p = obs.get("current_params", {})

    vec = np.array([
        # Economy state (10)
        g("token_price"),
        g("treasury_stable_ratio"),
        g("treasury_paytkn") / 2_000_000.0,
        g("staking_ratio"),
        g("reward_pool") / 100_000.0,
        g("current_apy_bps") / 10_000.0,
        g("total_supply") / 12_000_000.0,
        g("total_payments") / 1000.0,
        g("total_fees_eth"),
        g("merchant_pool") / 100_000.0,
        # Current RL params (6)
        float(p.get("mint_factor", 100)) / 200.0,
        float(p.get("burn_rate_bps", 2)) / 5.0,
        float(p.get("reward_alloc_bps", 3000)) / 10_000.0,
        float(p.get("cashback_base_bps", 50)) / 100.0,
        float(p.get("merchant_alloc_bps", 1000)) / 2500.0,
        float(p.get("treasury_ratio_bps", 6000)) / 10_000.0,
        # Placeholders for remaining dims (8)
        g("payment_volume_usd") / 10_000.0,
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    ], dtype=np.float32)
    return np.clip(vec, -1.0, 1.0)

def _mock_action() -> dict:
    """Return plausible default parameters when model is not loaded."""
    return {
        "mint_factor":        100,
        "burn_rate_bps":      2,
        "reward_alloc_bps":   3000,
        "cashback_base_bps":  50,
        "merchant_alloc_bps": 1000,
        "treasury_ratio_bps": 6000,
    }

# ─── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="PAYTKN RL Model Server", version="1.0.0")

class ObsRequest(BaseModel):
    observation: dict[str, Any] = {}
    reward: float | None = None

class ActionResponse(BaseModel):
    mint_factor:        int
    burn_rate_bps:      int
    reward_alloc_bps:   int
    cashback_base_bps:  int
    merchant_alloc_bps: int
    treasury_ratio_bps: int
    step: int
    source: str  # "model" | "mock"

@app.get("/status")
def status():
    global _model, _step_count, _last_action, _last_reward
    return {
        "connected":   _model is not None or not SB3_AVAILABLE,
        "model_path":  args.model,
        "model_loaded":_model is not None,
        "sb3_available": SB3_AVAILABLE,
        "step_count":  _step_count,
        "last_action": _last_action,
        "last_reward": _last_reward,
        "running":     True,
    }

@app.post("/action", response_model=ActionResponse)
def get_action(req: ObsRequest):
    global _step_count, _last_action, _last_reward
    with _lock:
        _last_reward = req.reward
        _step_count += 1

        if _model is not None:
            try:
                obs_arr = _obs_dict_to_array(req.observation)
                raw_action, _ = _model.predict(obs_arr, deterministic=True)
                action_keys = list(ACTION_BOUNDS.keys())
                params = {
                    "mint_factor":        _action_to_bps("mint_factor",        float(raw_action[0])),
                    "burn_rate_bps":      _action_to_bps("burn_rate",          float(raw_action[1])),
                    "reward_alloc_bps":   _action_to_bps("reward_alloc",       float(raw_action[2])),
                    "cashback_base_bps":  _action_to_bps("cashback_base_rate", float(raw_action[3])),
                    "merchant_alloc_bps": _action_to_bps("merchant_pool_alloc",float(raw_action[4])),
                    "treasury_ratio_bps": _action_to_bps("treasury_ratio",     float(raw_action[5])),
                }
                _last_action = params
                return ActionResponse(**params, step=_step_count, source="model")
            except Exception as e:
                print(f"[model_server] predict error: {e}")

        # Fallback: mock action
        params = _mock_action()
        _last_action = params
        return ActionResponse(**params, step=_step_count, source="mock")

@app.post("/shutdown")
def shutdown():
    threading.Thread(target=lambda: (time.sleep(0.5), os._exit(0))).start()
    return {"status": "shutting_down"}

# ─── Backend registration ─────────────────────────────────────────────────────
def _register_with_backend():
    """Tell the backend agent router we're up, so the Agent page shows connected."""
    time.sleep(2)  # wait for uvicorn to start
    try:
        requests.post(f"{args.backend}/agent/model-status", json={
            "connected":  True,
            "model_path": args.model,
            "step_count": 0,
            "running":    True,
        }, timeout=3)
        print(f"[model_server] Registered with backend at {args.backend}")
    except Exception as e:
        print(f"[model_server] Could not register with backend: {e} (backend may not be running)")

# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    model_loaded = _load_model(args.model)
    if not model_loaded:
        print("[model_server] Running in mock mode — /action will return default params")

    threading.Thread(target=_register_with_backend, daemon=True).start()

    print(f"[model_server] Serving on http://localhost:{args.port}")
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
