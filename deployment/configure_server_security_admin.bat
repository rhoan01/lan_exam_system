@echo off
setlocal
REM One-time administrator setup for the LAN exam server:
REM - binds MySQL to localhost only
REM - removes inbound MySQL firewall rules
REM - allows local-subnet access to Django/Waitress on standard HTTP port 80

cd /d "%~dp0.."

fltmc.exe >nul 2>&1
if errorlevel 1 (
  echo Requesting Administrator access for the one-time server security setup...
  powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "deployment\configure_mysql_localhost_admin.ps1"
if errorlevel 1 (
  echo.
  echo Server security setup failed. Review deployment\runtime\mysql-localhost-result.txt.
  pause
  exit /b 1
)

echo.
echo MySQL is restricted to localhost and LAN web access is enabled on TCP 80.
pause
