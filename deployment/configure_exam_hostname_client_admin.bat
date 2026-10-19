@echo off
setlocal
REM Run this once on every Windows student computer, or deploy it through
REM Group Policy. It maps exam.ite to the examination server's static IP.

set "SERVER_IP=%~1"
if not defined SERVER_IP set "SERVER_IP=192.168.0.244"

fltmc.exe >nul 2>&1
if errorlevel 1 (
  echo Requesting Administrator access to configure exam.ite...
  powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%SERVER_IP%' -Verb RunAs"
  exit /b
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure_exam_hostname_client.ps1" -ServerIp "%SERVER_IP%"
if errorlevel 1 (
  echo.
  echo Could not configure exam.ite. Review the error above.
  pause
  exit /b 1
)

echo.
echo Open http://exam.ite/ in the browser.
pause
