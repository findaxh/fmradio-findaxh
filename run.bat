@echo off
cd /d %~dp0

set PORT=8000
set PYTHON=C:\Users\finda\miniconda3\envs\pythonBase\python.exe

rem Force direct connection: never use system/env proxy (Clash Verge, etc.)
set RB_PROXY_MODE=direct
set HTTP_PROXY=
set HTTPS_PROXY=
set ALL_PROXY=
set http_proxy=
set https_proxy=
set all_proxy=

echo [1/2] Installing dependencies (first run needs internet)...
"%PYTHON%" -m pip install -r requirements.txt -q
if errorlevel 1 (
  echo Dependency install failed. Run manually: %PYTHON% -m pip install -r requirements.txt
  pause
  exit /b 1
)

echo [2/2] Starting FM radio server on port %PORT% ...
echo Browser:  http://localhost:%PORT%/
echo Public:   your-public-IP : frp-mapped-port  (optional, via frp)
echo Press Ctrl+C to stop.
"%PYTHON%" app.py
pause
