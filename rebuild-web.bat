@echo off
REM Rebuilds the web bundle that revelator.site actually serves.
REM The backend serves frontend\dist (see backend\app\main.py _DIST), so any
REM change to frontend\src is invisible on the live site until this runs.
REM Uses .env.production.local (VITE_API_URL blank -> relative /api, same-origin).
REM No backend restart needed: dist is read from disk per request.

cd /d "%~dp0frontend"
echo Building web bundle...
call npm run build
if errorlevel 1 (
  echo.
  echo BUILD FAILED - see the errors above.
  pause
  exit /b 1
)
echo.
echo Done. Hard-refresh the site with Ctrl+Shift+R.
pause
