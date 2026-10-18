@echo off
setlocal
REM ============================================================
REM Starts the LAN Examination System with MySQL and Waitress.
REM Secrets and machine-specific values live in mysql.local.bat, which
REM is ignored by Git. Run this file from anywhere or double-click it.
REM ============================================================

cd /d "%~dp0.."

if not exist "venv\Scripts\activate.bat" (
  echo ERROR: venv\Scripts\activate.bat was not found.
  echo Create the virtual environment and install requirements first.
  goto :error
)
call "venv\Scripts\activate.bat"

if not exist "deployment\mysql.local.bat" (
  echo ERROR: deployment\mysql.local.bat was not found.
  echo Copy deployment\.env.example to deployment\mysql.local.bat,
  echo then replace every placeholder with this server's values.
  goto :error
)
call "deployment\mysql.local.bat"

if /I not "%DB_ENGINE%"=="mysql" (
  echo ERROR: DB_ENGINE must be mysql in deployment\mysql.local.bat.
  goto :error
)

REM Start the dedicated MySQL 8.4 instance quietly when it is not already
REM listening. The database binds only to 127.0.0.1; students never connect
REM to it directly.
if not defined MYSQLD_EXE (
  echo ERROR: MYSQLD_EXE is missing from deployment\mysql.local.bat.
  goto :error
)
if not defined MYSQLD_CONFIG (
  echo ERROR: MYSQLD_CONFIG is missing from deployment\mysql.local.bat.
  goto :error
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$port = [int]$env:DB_PORT; $ready = Test-NetConnection -ComputerName $env:DB_HOST -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue; if (-not $ready) { if (-not (Test-Path -LiteralPath $env:MYSQLD_EXE)) { Write-Error ('MySQL executable not found: ' + $env:MYSQLD_EXE); exit 1 }; if (-not (Test-Path -LiteralPath $env:MYSQLD_CONFIG)) { Write-Error ('MySQL configuration not found: ' + $env:MYSQLD_CONFIG); exit 1 }; Start-Process -FilePath $env:MYSQLD_EXE -ArgumentList ('--defaults-file=' + $env:MYSQLD_CONFIG),'--standalone' -WorkingDirectory (Split-Path -Parent $env:MYSQLD_EXE) -WindowStyle Hidden; for ($i=0; $i -lt 40; $i++) { Start-Sleep -Milliseconds 500; if (Test-NetConnection -ComputerName $env:DB_HOST -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue) { exit 0 } }; Write-Error ('MySQL did not become ready on port ' + $port + '.'); exit 1 }"
if errorlevel 1 goto :error

echo.
echo Checking application configuration...
python manage.py check --deploy
if errorlevel 1 goto :error

echo.
echo Applying MySQL database migrations...
python manage.py migrate --noinput
if errorlevel 1 goto :error

echo.
echo Collecting static files...
python manage.py collectstatic --noinput
if errorlevel 1 goto :error

echo.
echo ============================================================
echo  LAN Examination System is starting on MySQL.
echo  Local: http://127.0.0.1:8000/
echo  LAN:   http://%LAN_SERVER_IP%:8000/
echo  Press CTRL+C to stop the web server.
echo ============================================================
echo.
waitress-serve --listen=0.0.0.0:8000 --threads=8 examsystem.wsgi:application
goto :eof

:error
echo.
echo The server was NOT started. Review the error above.
exit /b 1
