# ════════════════════════════════════════════════════════════════
#  PAYTKN FYP — Full Demo Startup Script
#  Starts all 4 services in separate windows then seeds demo data
#
#  Usage: Right-click → Run with PowerShell  (or: .\START_DEMO.ps1)
# ════════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "  ██████╗  █████╗ ██╗   ██╗████████╗██╗  ██╗███╗   ██╗" -ForegroundColor Cyan
Write-Host "  ██╔══██╗██╔══██╗╚██╗ ██╔╝╚══██╔══╝██║ ██╔╝████╗  ██║" -ForegroundColor Cyan
Write-Host "  ██████╔╝███████║ ╚████╔╝    ██║   █████╔╝ ██╔██╗ ██║" -ForegroundColor Cyan
Write-Host "  ██╔═══╝ ██╔══██║  ╚██╔╝     ██║   ██╔═██╗ ██║╚██╗██║" -ForegroundColor Cyan
Write-Host "  ██║     ██║  ██║   ██║      ██║   ██║  ██╗██║ ╚████║" -ForegroundColor Cyan
Write-Host "  ╚═╝     ╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═══╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  FYP Demo — RL-Controlled Crypto Payment Protocol" -ForegroundColor White
Write-Host "  NUST NSTP Incubation | Base Sepolia Testnet" -ForegroundColor Gray
Write-Host ""

$FYP = "C:\Users\Muhammad Essa\Desktop\FYP"

# ── 1. Backend (FastAPI — port 8000) ─────────────────────────────────────────
Write-Host "[1/4] Starting Backend API (port 8000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$FYP\paytkn-backend'; Write-Host '  PAYTKN Backend — port 8000' -ForegroundColor Cyan; python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
) -WindowStyle Normal

Start-Sleep -Seconds 3

# ── 2. RL Model Server (FastAPI — port 8001) ─────────────────────────────────
Write-Host "[2/4] Starting RL Model Server (port 8001)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$FYP\paytkn-model'; Write-Host '  PAYTKN RL Model Server — port 8001' -ForegroundColor Magenta; python -m uvicorn model_server:app --host 0.0.0.0 --port 8001 --reload"
) -WindowStyle Normal

Start-Sleep -Seconds 3

# ── 3. Frontend (Next.js — port 3000) ────────────────────────────────────────
Write-Host "[3/4] Starting Frontend (port 3000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$FYP\paytkn-frontend'; Write-Host '  PAYTKN Frontend — port 3000' -ForegroundColor Green; npm run dev"
) -WindowStyle Normal

Start-Sleep -Seconds 2

# ── 4. TechMart Store (Python — port 3001) ──────────────────────────────────
Write-Host "[4/4] Starting TechMart Store (port 3001)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$FYP\paytkn-store'; Write-Host '  TechMart Store — port 3001' -ForegroundColor Blue; python serve.py"
) -WindowStyle Normal

# ── Wait for backend to be ready ─────────────────────────────────────────────
Write-Host ""
Write-Host "  Waiting for services to start..." -ForegroundColor Gray
Start-Sleep -Seconds 8

# ── Seed demo data automatically ─────────────────────────────────────────────
Write-Host "  Seeding demo economy data..." -ForegroundColor Yellow
try {
    $seed = Invoke-RestMethod -Uri "http://localhost:8000/demo/seed" -Method POST -ContentType "application/json" -Body "{}" -TimeoutSec 10
    Write-Host "  Demo data seeded: $($seed.transactions) transactions, $($seed.staking_positions) staking positions" -ForegroundColor Green
} catch {
    Write-Host "  Backend not ready yet — seed manually via dashboard 'Load Demo Data' button" -ForegroundColor Red
}

# ── Start RL loop ─────────────────────────────────────────────────────────────
Write-Host "  Starting RL inference loop..." -ForegroundColor Yellow
try {
    $loop = Invoke-RestMethod -Uri "http://localhost:8001/start" -Method POST -ContentType "application/json" -Body "{}" -TimeoutSec 10
    Write-Host "  RL loop started: $($loop.status)" -ForegroundColor Green
} catch {
    Write-Host "  Model server not ready yet — start loop manually via Agent page" -ForegroundColor Red
}

# ── Open browser tabs ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Opening browser tabs..." -ForegroundColor Gray
Start-Sleep -Seconds 3

Start-Process "http://localhost:3000/agent"
Start-Sleep -Milliseconds 500
Start-Process "http://localhost:3001"
Start-Sleep -Milliseconds 500
Start-Process "http://localhost:3000/merchant"
Start-Sleep -Milliseconds 500
Start-Process "http://localhost:3000/dashboard"

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "   ALL SERVICES STARTED" -ForegroundColor White
Write-Host "  ═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Port 3000  → Next.js Frontend (main app)" -ForegroundColor Green
Write-Host "               /           Protocol dashboard"
Write-Host "               /agent      RL Agent control panel"
Write-Host "               /store      Product catalogue (also at 3001)"
Write-Host "               /checkout   Payment flow"
Write-Host "               /merchant   Merchant dashboard"
Write-Host "               /dashboard  User dashboard"
Write-Host ""
Write-Host "   Port 3001  → TechMart Store (standalone HTML)" -ForegroundColor Blue
Write-Host "   Port 8000  → FastAPI Backend (REST API)" -ForegroundColor Yellow
Write-Host "   Port 8001  → RL Model Server (PPO inference)" -ForegroundColor Magenta
Write-Host ""
Write-Host "  ═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "   DEMO FLOW:" -ForegroundColor White
Write-Host "   1. /agent  — Show PPO model running, parameters live"
Write-Host "   2. /store  — Browse TechMart products"
Write-Host "   3. Checkout— Pay with ETH → Jumper/LIFI → RL cashback"
Write-Host "   4. /dashboard — Connect wallet → 'Load Demo Data'"
Write-Host "              — See transaction, staking, referrals"
Write-Host "   5. /merchant — See payment received, webhook, tier"
Write-Host "   6. /agent  — Show RL step ran, cashback_bps updated"
Write-Host ""
Write-Host "   Docs: http://localhost:8000/docs" -ForegroundColor Gray
Write-Host ""

Read-Host "  Press ENTER to exit this launcher"
