@echo off
title PAYTKN — Launch All Services
color 0A
echo.
echo  ██████╗  █████╗ ██╗   ██╗████████╗██╗  ██╗███╗   ██╗
echo  ██╔══██╗██╔══██╗╚██╗ ██╔╝╚══██╔══╝██║ ██╔╝████╗  ██║
echo  ██████╔╝███████║ ╚████╔╝    ██║   █████╔╝ ██╔██╗ ██║
echo  ██╔═══╝ ██╔══██║  ╚██╔╝     ██║   ██╔═██╗ ██║╚██╗██║
echo  ██║     ██║  ██║   ██║      ██║   ██║  ██╗██║ ╚████║
echo  ╚═╝     ╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═══╝
echo.
echo  Starting all PAYTKN services...
echo  ════════════════════════════════════════════════════════
echo.

:: ── 1. Backend API (Port 8000) ────────────────────────────────────────────────
echo  [1/4] Starting Backend API on port 8000...
start "PAYTKN Backend (8000)" cmd /k "cd /d %~dp0paytkn-backend && echo [BACKEND] Starting... && uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

:: Wait for backend to start
timeout /t 4 /nobreak > nul

:: ── 2. RL Model Server (Port 8001) ───────────────────────────────────────────
echo  [2/4] Starting RL Model Server on port 8001...
start "PAYTKN RL Model (8001)" cmd /k "cd /d %~dp0paytkn-model && echo [MODEL] Starting... && python model_server.py"

:: ── 3. Merchant Store (Port 3001) ────────────────────────────────────────────
echo  [3/4] Starting TechMart Store on port 3001...
start "TechMart Store (3001)" cmd /k "cd /d %~dp0paytkn-store && echo [STORE] Starting... && python serve.py"

:: Wait a moment
timeout /t 2 /nobreak > nul

:: ── 4. Frontend App (Port 3000) ──────────────────────────────────────────────
echo  [4/4] Starting PAYTKN Frontend on port 3000...
start "PAYTKN Frontend (3000)" cmd /k "cd /d %~dp0paytkn-frontend && echo [FRONTEND] Starting... && npm run dev"

:: Wait for everything to boot
timeout /t 8 /nobreak > nul

echo.
echo  ════════════════════════════════════════════════════════
echo   All services running:
echo.
echo   Port 3000  PAYTKN App        http://localhost:3000
echo              └─ Protocol Dashboard   /
echo              └─ User Dashboard       /dashboard
echo              └─ Merchant Dashboard   /merchant
echo              └─ RL Agent Panel       /agent
echo              └─ Checkout             /checkout
echo.
echo   Port 3001  TechMart Store    http://localhost:3001
echo              └─ External merchant demo website
echo.
echo   Port 8000  Backend API       http://localhost:8000
echo              └─ Swagger UI           /docs
echo.
echo   Port 8001  RL Model Server   http://localhost:8001
echo              └─ Status               /status
echo              └─ Start Loop           POST /start
echo.
echo  ════════════════════════════════════════════════════════
echo.

:: Open browsers
start "" "http://localhost:3001"
timeout /t 2 /nobreak > nul
start "" "http://localhost:3000"

echo  Press any key to close this launcher (services keep running)
pause > nul
