@echo off
title AudioTrimmer Web
cd /d "%~dp0"

echo [~] Stopping old server (if running)...
:: Kill the process holding the port (and all its children)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8001 " ^| findstr "LISTENING"') do (
    taskkill /F /T /PID %%a >nul 2>&1
)

timeout /t 2 /nobreak >nul

echo [*] Starting server at http://localhost:8001
poetry run python web/server.py > server.log 2>&1