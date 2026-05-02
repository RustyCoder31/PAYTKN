"""
PAYTKN RL Model Inference Server — Port 8001
Loads the trained PPO model and runs inference against live chain state.
Falls back to a rule-based heuristic policy if no model file is found.
"""
import time
import threading
import hashlib
import numpy as np
import requests
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────────────────────
BACKEND_URL  = "http://localhost:8000"
MODEL_PATHS  = [
    Path(__file__).parent.parent / "models_v4"  / "models" / "best_model.zip",
    Path(__file__).parent.parent / "chainenv"   / "models" / "best_model.zip",
    Path(__file__).parent.parent / "models_v4"  / "models" / "paytkn_v4_5yr_final.zip",
    Path(__file__).parent.parent / "chainenv"   / "models" / "paytkn_v33_final.zip",
    Path(__file__).parent / "best_model.zip",
]
STEP_INTERVAL = 30        # seconds between RL steps — updated via /speed endpoint
_step_interval: float = STEP_INTERVAL
OBS_DIM       = 10

# ── Parameter bounds (must match contract) ───────────────────────────────────
PARAM_BOUNDS = {
    "mint_factor":        (1,    200),
    "burn_rate_bps":      (0,    5),
    "reward_alloc_bps":   (1000, 6000),
    "cashback_base_bps":  (10,   100),
    "merchant_alloc_bps": (100,  2500),
    "treasury_ratio_bps": (1000, 9000),
}
PARAM_KEYS = list(PARAM_BOUNDS.keys())

app = FastAPI(title="PAYTKN RL Model Server", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── State ─────────────────────────────────────────────────────────────────────
_model        = None
_model_path   = None
_step_count   = 0
_last_obs     = None
_last_action  = None
_last_reward  = None
_loop_running = False
_loop_thread  = None


# ── Model loading ─────────────────────────────────────────────────────────────
def try_load_model():
    global _model, _model_path
    for path in MODEL_PATHS:
        if path.exists():
            try:
                from stable_baselines3 import PPO
                _model = PPO.load(str(path))
                _model_path = str(path)
                print(f"[MODEL] Loaded PPO from {path}")
                return True
            except Exception as e:
                print(f"[MODEL] Failed to load {path}: {e}")
    print("[MODEL] No model file found — using rule-based fallback policy")
    return False


def rule_based_policy(obs: dict) -> dict:
    """
    Heuristic policy used when no trained model is available.
    Implements basic stability rules:
      - If price < 0.98: reduce burn, increase mint, boost cashback
      - If price > 1.02: increase burn, reduce mint
      - If staking ratio < 0.05: boost reward allocation
      - If treasury < 0.3 ETH: increase treasury ratio
    """
    price         = obs.get("token_price",       1.0)
    stake_ratio   = obs.get("staking_ratio",     0.08)
    treasury      = obs.get("treasury_stable_ratio", 0.5)
    current       = obs.get("current_params", {})

    mf  = current.get("mint_factor",        100)
    br  = current.get("burn_rate_bps",      2)
    ra  = current.get("reward_alloc_bps",   3000)
    cb  = current.get("cashback_base_bps",  50)
    ma  = current.get("merchant_alloc_bps", 1000)
    tr  = current.get("treasury_ratio_bps", 6000)

    # Price stability
    if price < 0.95:
        mf = min(200, mf + 10);  br = max(0, br - 1);  cb = min(100, cb + 5)
    elif price < 0.98:
        mf = min(200, mf + 5);   br = max(0, br - 1)
    elif price > 1.05:
        mf = max(1, mf - 10);    br = min(5, br + 1)
    elif price > 1.02:
        mf = max(1, mf - 5);     br = min(5, br + 1)

    # Staking incentive
    if stake_ratio < 0.05:
        ra = min(6000, ra + 200); cb = min(100, cb + 3)
    elif stake_ratio > 0.25:
        ra = max(1000, ra - 100)

    # Treasury health
    if treasury < 0.3:
        tr = min(9000, tr + 300)
    elif treasury > 0.7:
        tr = max(1000, tr - 200); ma = min(2500, ma + 100)

    return {
        "mint_factor":        int(np.clip(mf,  *PARAM_BOUNDS["mint_factor"])),
        "burn_rate_bps":      int(np.clip(br,  *PARAM_BOUNDS["burn_rate_bps"])),
        "reward_alloc_bps":   int(np.clip(ra,  *PARAM_BOUNDS["reward_alloc_bps"])),
        "cashback_base_bps":  int(np.clip(cb,  *PARAM_BOUNDS["cashback_base_bps"])),
        "merchant_alloc_bps": int(np.clip(ma,  *PARAM_BOUNDS["merchant_alloc_bps"])),
        "treasury_ratio_bps": int(np.clip(tr,  *PARAM_BOUNDS["treasury_ratio_bps"])),
    }


def obs_to_array(obs: dict) -> np.ndarray:
    """Convert observation dict to numpy array for model inference."""
    current = obs.get("current_params", {})
    arr = np.array([
        float(obs.get("token_price",           1.0)),
        float(obs.get("treasury_stable_ratio", 0.5)),
        float(obs.get("staking_ratio",         0.08)),
        float(obs.get("reward_pool",           0)) / 1e6,
        float(obs.get("current_apy_bps",       800)) / 10000,
        float(obs.get("total_supply",          12e6)) / 1e8,
        float(obs.get("total_payments",        0)) / 1000,
        float(obs.get("payment_volume_usd",    0)) / 1e6,
        float(current.get("burn_rate_bps",     2)) / 5,
        float(current.get("reward_alloc_bps",  3000)) / 6000,
    ], dtype=np.float32)
    return arr


def action_to_params(raw_action: np.ndarray) -> dict:
    """Map PPO action (normalized) to parameter dict."""
    keys  = PARAM_KEYS
    bounds = [PARAM_BOUNDS[k] for k in keys]
    # PPO action is in [-1, 1]; map to [lo, hi]
    params = {}
    for i, (key, (lo, hi)) in enumerate(zip(keys, bounds)):
        a = float(raw_action[i]) if i < len(raw_action) else 0.0
        val = lo + (a + 1) / 2 * (hi - lo)
        params[key] = int(np.clip(round(val), lo, hi))
    return params


def run_inference_step() -> dict:
    """Fetch observation, run model/policy, return proposed params."""
    global _last_obs, _last_action, _step_count

    # Fetch observation from backend
    try:
        r = requests.get(f"{BACKEND_URL}/agent/observe", timeout=10)
        obs = r.json()
    except Exception as e:
        print(f"[STEP] Failed to fetch observation: {e}")
        obs = {"token_price": 1.0, "current_params": {}}

    _last_obs = obs

    # Run inference
    if _model is not None:
        try:
            obs_arr   = obs_to_array(obs)
            action, _ = _model.predict(obs_arr, deterministic=True)
            params    = action_to_params(action)
            source    = "ppo_model"
        except Exception as e:
            print(f"[STEP] Model inference failed: {e}")
            params = rule_based_policy(obs)
            source = "fallback"
    else:
        params = rule_based_policy(obs)
        source = "rule_based"

    _last_action = params
    _step_count += 1

    # Push to backend
    try:
        r = requests.post(f"{BACKEND_URL}/agent/update-params", json=params, timeout=15)
        push_result = r.json()
    except Exception as e:
        push_result = {"error": str(e)}

    print(f"[STEP {_step_count}] source={source} params={params} push={push_result.get('status','?')}")
    return {"step": _step_count, "source": source, "params": params, "push": push_result}


def inference_loop():
    global _loop_running
    print(f"[LOOP] Starting inference loop every {_step_interval:.1f}s")
    while _loop_running:
        try:
            run_inference_step()
        except Exception as e:
            print(f"[LOOP] Error: {e}")
        elapsed = 0.0
        while _loop_running and elapsed < _step_interval:
            time.sleep(0.05)
            elapsed += 0.05
    print("[LOOP] Stopped")


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    try_load_model()
    report_status()


def report_status():
    try:
        requests.post(f"{BACKEND_URL}/agent/model-status", json={
            "connected":  True,
            "model_path": _model_path,
            "step_count": _step_count,
            "last_action": _last_action,
            "running":    _loop_running,
        }, timeout=5)
    except Exception:
        pass


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "service":    "PAYTKN RL Model Server",
        "model":      _model_path or "rule_based_fallback",
        "steps_run":  _step_count,
        "loop":       _loop_running,
    }


@app.get("/status")
def status():
    return {
        "model_loaded": _model is not None,
        "model_path":   _model_path,
        "step_count":   _step_count,
        "loop_running": _loop_running,
        "last_obs":     _last_obs,
        "last_action":  _last_action,
        "last_reward":  _last_reward,
        "policy":       "ppo" if _model else "rule_based",
    }


@app.post("/step")
def manual_step():
    """Run one inference step immediately."""
    result = run_inference_step()
    report_status()
    return result


@app.post("/start")
def start_loop():
    global _loop_running, _loop_thread
    if _loop_running:
        return {"status": "already_running", "step_count": _step_count}
    _loop_running = True
    _loop_thread  = threading.Thread(target=inference_loop, daemon=True)
    _loop_thread.start()
    report_status()
    return {"status": "started", "interval_seconds": STEP_INTERVAL}


@app.post("/stop")
def stop_loop():
    global _loop_running
    _loop_running = False
    report_status()
    return {"status": "stopping"}


@app.post("/speed")
def set_speed(seconds_per_step: float = 30.0):
    """Set the RL inference interval. Min 0.3s, max 60s."""
    global _step_interval
    _step_interval = max(0.3, min(60.0, seconds_per_step))
    print(f"[LOOP] Speed set to {_step_interval:.2f}s per step")
    return {"status": "ok", "seconds_per_step": _step_interval}


@app.get("/predict")
def predict_only():
    """Run inference without pushing to backend — for frontend display."""
    try:
        r   = requests.get(f"{BACKEND_URL}/agent/observe", timeout=10)
        obs = r.json()
    except Exception:
        obs = {}
    if _model:
        try:
            arr, _ = _model.predict(obs_to_array(obs), deterministic=True)
            params = action_to_params(arr)
        except Exception:
            params = rule_based_policy(obs)
    else:
        params = rule_based_policy(obs)
    return {"params": params, "policy": "ppo" if _model else "rule_based"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("model_server:app", host="0.0.0.0", port=8001, reload=False)
