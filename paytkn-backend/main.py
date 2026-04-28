"""PAYTKN Backend API — FastAPI + Web3.py on Base Sepolia."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import protocol, agent, payments, staking, users, demo, simulation

app = FastAPI(
    title="PAYTKN API",
    description="Backend for PAYTKN — RL-controlled crypto payment token",
    version="1.0.0",
    docs_url="/docs",
)

# Allow frontend (Next.js on port 3000) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(protocol.router)
app.include_router(agent.router)
app.include_router(payments.router)
app.include_router(staking.router)
app.include_router(users.router)
app.include_router(demo.router)
app.include_router(simulation.router)


@app.get("/")
def root():
    return {
        "project": "PAYTKN",
        "version": "1.0.0",
        "network": "Base Sepolia",
        "docs":    "/docs",
        "endpoints": [
            "GET  /protocol/state    — full protocol snapshot",
            "GET  /protocol/price    — PAYTKN price",
            "GET  /agent/observe     — RL agent observation",
            "POST /agent/update-params — push new RL parameters",
            "POST /agent/burn        — trigger daily burn",
            "POST /agent/mint        — trigger adaptive mint",
            "POST /payments/process  — simulate payment",
            "GET  /staking/stats     — user staking pool",
            "GET  /staking/merchant/stats — merchant pool",
            "POST /users/register    — register new user",
            "GET  /users/{address}/profile — user profile",
        ]
    }


@app.get("/health")
def health():
    from contracts import w3
    return {
        "status":       "ok",
        "connected":    w3.is_connected(),
        "block_number": w3.eth.block_number,
    }
