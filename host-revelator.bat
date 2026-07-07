@echo off
REM ============================================================
REM  Revelator LIVE launcher -> https://revelator.site
REM  Runs the app on THIS laptop and exposes it through the
REM  named Cloudflare tunnel "revelator" (stable domain, real
REM  cert, no "Dangerous" warning).
REM
REM  Prereqs (already done once): cloudflared login, tunnel
REM  "revelator" created, DNS routed, config.yml in
REM  %USERPROFILE%\.cloudflared\.
REM  Close both windows to stop hosting.
REM ============================================================

setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo [1/2] Starting Revelator server on http://localhost:8010 ...
start "Revelator Server" /min cmd /k "cd /d "%ROOT%backend" && set PORT=8010&& set RELOAD=0&& "%PY%" run.py"

echo [2/2] Starting named Cloudflare tunnel -> https://revelator.site ...
start "Revelator Tunnel" /min cmd /k ""%ROOT%tools\cloudflared.exe" tunnel run revelator"

echo.
echo Revelator is going live at https://revelator.site
echo Close both windows to stop hosting.
endlocal
