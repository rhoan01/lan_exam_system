@echo off
setlocal EnableExtensions
REM ============================================================
REM One-click production launcher for the LAN Examination System.
REM Starts MySQL, forces MySQL-only operation, applies migrations,
REM validates deployment capacity, and starts Waitress.
REM ============================================================

cd /d "%~dp0.."
title LAN Examination System

if not exist "venv\Scripts\activate.bat" (
  echo ERROR: venv\Scripts\activate.bat was not found.
  echo Run: python -m venv venv
  echo Then: venv\Scripts\pip install -r requirements.txt
  goto :error
)
call "venv\Scripts\activate.bat"

if not exist "deployment\mysql.local.bat" (
  echo ERROR: deployment\mysql.local.bat was not found.
  echo Copy deployment\.env.example to deployment\mysql.local.bat and fill it in.
  goto :error
)
call "deployment\mysql.local.bat"

if /I not "%DB_ENGINE%"=="mysql" (
  echo ERROR: DB_ENGINE must be mysql. The server will not fall back to SQLite.
  goto :error
)
if not defined DB_PASSWORD (
  echo ERROR: DB_PASSWORD is missing from deployment\mysql.local.bat.
  goto :error
)

if not defined WAITRESS_PORT set "WAITRESS_PORT=80"
if not defined LAN_HOSTNAME set "LAN_HOSTNAME=exam.ite"
if not defined WAITRESS_THREADS set "WAITRESS_THREADS=32"
REM Waitress uses select() on Windows, whose descriptor set is limited. Keep
REM live channels below that ceiling; the larger OS backlog queues the rest.
if not defined WAITRESS_CONNECTION_LIMIT set "WAITRESS_CONNECTION_LIMIT=400"
if not defined WAITRESS_BACKLOG set "WAITRESS_BACKLOG=2048"
if not defined WAITRESS_CHANNEL_TIMEOUT set "WAITRESS_CHANNEL_TIMEOUT=20"

echo.
echo [1/6] Starting MySQL...
if defined MYSQL_SERVICE_NAME (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$service = Get-Service -Name $env:MYSQL_SERVICE_NAME -ErrorAction Stop; if ($service.Status -ne 'Running') { try { Start-Service -Name $env:MYSQL_SERVICE_NAME -ErrorAction Stop } catch { $command = 'Start-Service -Name ' + [char]39 + $env:MYSQL_SERVICE_NAME + [char]39; $process = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList '-NoProfile','-Command',$command; if ($process.ExitCode -ne 0) { exit $process.ExitCode } } }; $service = Get-Service -Name $env:MYSQL_SERVICE_NAME; if ($service.Status -ne 'Running') { Write-Error 'MySQL service did not start.'; exit 1 }"
  if errorlevel 1 goto :error
) else (
  if not defined MYSQLD_EXE goto :missing_mysql_start
  if not defined MYSQLD_CONFIG goto :missing_mysql_start
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ready = Test-NetConnection -ComputerName $env:DB_HOST -Port ([int]$env:DB_PORT) -InformationLevel Quiet -WarningAction SilentlyContinue; if (-not $ready) { Start-Process -FilePath $env:MYSQLD_EXE -ArgumentList ('--defaults-file=' + $env:MYSQLD_CONFIG),'--standalone' -WorkingDirectory (Split-Path -Parent $env:MYSQLD_EXE) -WindowStyle Hidden }"
  if errorlevel 1 goto :error
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ready = $false; for ($i = 0; $i -lt 60; $i++) { if (Test-NetConnection -ComputerName $env:DB_HOST -Port ([int]$env:DB_PORT) -InformationLevel Quiet -WarningAction SilentlyContinue) { $ready = $true; break }; Start-Sleep -Milliseconds 500 }; if (-not $ready) { Write-Error 'MySQL did not become ready.'; exit 1 }"
if errorlevel 1 goto :error

echo [2/6] Checking Django configuration...
python manage.py check
if errorlevel 1 goto :error

echo [3/6] Applying migrations to MySQL...
python manage.py migrate --noinput
if errorlevel 1 goto :error

echo [4/6] Verifying MySQL deployment readiness...
python manage.py check_exam_readiness
if errorlevel 1 goto :error

echo [5/6] Collecting static files...
python manage.py collectstatic --noinput
if errorlevel 1 goto :error

echo [6/6] Checking web port %WAITRESS_PORT%...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$listener = Get-NetTCPConnection -State Listen -LocalPort ([int]$env:WAITRESS_PORT) -ErrorAction SilentlyContinue; if ($listener) { Write-Error ('Port ' + $env:WAITRESS_PORT + ' is already in use by process ' + $listener[0].OwningProcess + '. Stop the existing server first.'); exit 1 }; exit 0"
if errorlevel 1 goto :error

echo.
echo ============================================================
echo  LAN Examination System - PRODUCTION / MYSQL
echo  Local: http://127.0.0.1:%WAITRESS_PORT%/
echo  LAN:   http://%LAN_SERVER_IP%:%WAITRESS_PORT%/
echo  Name:  http://%LAN_HOSTNAME%/
echo  Threads: %WAITRESS_THREADS%   Connection limit: %WAITRESS_CONNECTION_LIMIT%
echo  Press CTRL+C to stop the web server.
echo ============================================================
echo.

waitress-serve --listen=0.0.0.0:%WAITRESS_PORT% --threads=%WAITRESS_THREADS% --connection-limit=%WAITRESS_CONNECTION_LIMIT% --backlog=%WAITRESS_BACKLOG% --channel-timeout=%WAITRESS_CHANNEL_TIMEOUT% --cleanup-interval=10 --max-request-body-size=16777216 examsystem.wsgi:application
goto :eof

:missing_mysql_start
echo ERROR: Set MYSQL_SERVICE_NAME, or set both MYSQLD_EXE and MYSQLD_CONFIG.
goto :error

:error
echo.
echo The examination server was NOT started. Review the error above.
pause
exit /b 1
