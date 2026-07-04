@echo off
REM ============================================================
REM  Revelator HOST launcher (completely free)
REM  Runs the whole app on THIS laptop and exposes it to the
REM  internet with a free Cloudflare quick tunnel.
REM
REM  Prereqs (one-time, see HOSTING.md):
REM    1) cloudflared installed  (winget install Cloudflare.cloudflared)
REM    2) frontend built         (cd frontend && npm run build)
REM    3) backend deps installed (pip install -r backend/requirements.txt)
REM
REM  The public https URL is printed in the "Cloudflare Tunnel" window.
REM  Close both windows to stop hosting.
REM ============================================================

setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

if not exist "%ROOT%frontend\dist\index.html" (
  echo [!] frontend\dist not found. Build it first:  cd frontend ^&^& npm run build
  echo     Continuing anyway - the API will run, but no web UI will be served.
)

echo [1/2] Starting Revelator server (backend + built frontend) on http://localhost:8000 ...
start "Revelator Server" cmd /k "cd /d "%ROOT%backend" && "%PY%" run.py"

echo [2/2] Starting Cloudflare quick tunnel (free public URL) ...
echo     ^>^>^> Your public https URL appears in the "Cloudflare Tunnel" window. Share it. ^<^<^<
start "Cloudflare Tunnel" cmd /k "cloudflared tunnel --url http://localhost:8000"

echo.
echo Revelator is launching in two windows. Close them to stop hosting.
endlocal
