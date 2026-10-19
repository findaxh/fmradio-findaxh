@echo off
cd /d %~dp0

set PORT=6123
set PYTHON=C:\Users\finda\miniconda3\envs\pythonBase\python.exe
set PIDFILE=.fmradio.pid
set LOGFILE=fmradio.log
set ERRLOG=fmradio.err.log

rem Force direct connection: never use system/env proxy (Clash Verge, etc.)
set RB_PROXY_MODE=direct
set HTTP_PROXY=
set HTTPS_PROXY=
set ALL_PROXY=
set http_proxy=
set https_proxy=
set all_proxy=

if /I "%1"=="stop"    goto STOP
if /I "%1"=="restart" goto RESTART
if /I "%1"=="status"  goto STATUS
if /I "%1"=="logs"    goto LOGS
if /I "%1"=="run"     goto RUN
if /I "%1"=="help"    goto HELP
if    "%1"==""        goto START
if /I "%1"=="start"   goto START
echo Unknown command: %1
goto HELP

:START
echo [1/2] Checking dependencies...
"%PYTHON%" -m pip install -r requirements.txt -q
if errorlevel 1 (
  echo Dependency install failed. Run manually:
  echo   "%PYTHON%" -m pip install -r requirements.txt
  pause
  exit /b 1
)
echo [2/2] Starting in background on port %PORT% ...
powershell -NoProfile -Command "$p = Start-Process -FilePath '%PYTHON%' -ArgumentList 'app.py' -WorkingDirectory '%CD%' -WindowStyle Hidden -PassThru -RedirectStandardOutput '%LOGFILE%' -RedirectStandardError '%ERRLOG%'; Set-Content -Path '%PIDFILE%' -Value $p.Id -Encoding ASCII"
if errorlevel 1 (
  echo Failed to start.
  pause
  exit /b 1
)
echo.
echo Started. Port %PORT%
echo Browser:  http://localhost:%PORT%/
echo Public:   your-public-IP : frp-mapped-port  (optional, via frp)
echo Log:      %CD%\%LOGFILE%
echo You can close this window; the service keeps running.
goto END

:STOP
if not exist "%PIDFILE%" (
  echo Not running.
  exit /b 0
)
set /p FM_PID=<"%PIDFILE%"
taskkill /PID %FM_PID% /T /F >nul 2>&1
del "%PIDFILE%" >nul 2>&1
echo Stopped. PID was %FM_PID%.
exit /b 0

:RESTART
call :STOP
goto START

:STATUS
if not exist "%PIDFILE%" (
  echo Not running.
  goto END
)
set /p FM_PID=<"%PIDFILE%"
tasklist /FI "PID eq %FM_PID%" /NH | findstr /I "%FM_PID%" >nul
if errorlevel 1 (
  echo Not running. Stale pid file: %PIDFILE%
  goto END
)
echo Running. PID %FM_PID%  http://localhost:%PORT%/
goto END

:LOGS
echo Live log: %CD%\%LOGFILE%  (Ctrl+C to quit, service keeps running)
powershell -NoProfile -Command "Get-Content '%LOGFILE%' -Wait -Tail 50"
goto END

:RUN
echo Foreground mode (debug). Press Ctrl+C to stop.
echo Browser:  http://localhost:%PORT%/
"%PYTHON%" app.py
pause
goto END

:HELP
echo Usage: run.bat [command]
echo.
echo   (none)     Start in background (default, window can be closed)
echo   start      Start in background
echo   stop       Stop the service
echo   restart    Restart
echo   status     Show running status
echo   logs       Tail the log file (Ctrl+C only quits the view)
echo   run        Run in foreground (debug)
echo   help       Show this help
echo.
echo Port:     %PORT%   (edit PORT in run.bat to change)
echo Python:   %PYTHON%
goto END

:END
exit /b 0
