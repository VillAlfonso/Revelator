@echo off
REM ============================================================
REM  Runs Revelator locally and exposes it through Cloudflare.
REM  Uses the named "revelator" tunnel when configured; otherwise
REM  starts a temporary trycloudflare.com tunnel.
REM  Close both windows to stop hosting.
REM ============================================================

setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

if not exist "%ROOT%tools\cloudflared.exe" (
  echo ERROR: Cloudflare Tunnel binary not found:
  echo   %ROOT%tools\cloudflared.exe
  pause
  exit /b 1
)

where npm >nul 2>&1
if not errorlevel 1 goto npm_ready

for /d %%P in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_*") do (
  for /d %%N in ("%%~fP\node-v*-win-x64") do (
    if exist "%%~fN\npm.cmd" set "PATH=%%~fN;%PATH%"
  )
)

where npm >nul 2>&1
if errorlevel 1 (
  echo ERROR: Node.js and npm are required to build the latest frontend.
  echo Install Node.js, then run this file again.
  pause
  exit /b 1
)

:npm_ready
echo Building the latest Revelator frontend...
pushd "%ROOT%frontend"
call npm run build
if errorlevel 1 (
  popd
  echo.
  echo ERROR: Frontend build failed; Revelator was not started.
  pause
  exit /b 1
)
popd

"%PY%" -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python could not start or the environment lacks FastAPI and Uvicorn.
  echo Restore the project venv and backend requirements before hosting.
  pause
  exit /b 1
)

set "TUNNEL_CREDENTIALS=%USERPROFILE%\.cloudflared\ac5f952f-02ad-457d-8d2d-64cafbc359ec.json"
if exist "%TUNNEL_CREDENTIALS%" if exist "%ROOT%tools\cloudflared-config.yml" set "NAMED_TUNNEL=1"

echo [1/2] Starting Revelator server on http://localhost:8010 ...
start "Revelator Server" /min cmd /k "cd /d "%ROOT%backend" && set PORT=8010&& set RELOAD=0&& "%PY%" run.py"

if not defined NAMED_TUNNEL goto quick_tunnel
echo [2/2] Starting named Cloudflare tunnel "revelator"...
start "Revelator Cloudflare Tunnel" cmd /k ""%ROOT%tools\cloudflared.exe" tunnel --config "%ROOT%tools\cloudflared-config.yml" --credentials-file "%TUNNEL_CREDENTIALS%" --logfile "%ROOT%tools\cloudflared.log" --loglevel info run revelator"
goto started

:quick_tunnel
echo [2/2] No named tunnel config found. Starting a temporary Cloudflare URL...
echo The trycloudflare.com URL will appear in the tunnel window.
start "Revelator Cloudflare Tunnel" cmd /k ""%ROOT%tools\cloudflared.exe" tunnel --url http://localhost:8010 --logfile "%ROOT%tools\cloudflared.log" --loglevel info"

:started
echo.
echo Revelator server and Cloudflare Tunnel are launching.
echo Cloudflare warning/error log: %ROOT%tools\cloudflared.log
echo Close both windows to stop hosting.
endlocal
