@echo off
setlocal
REM One-time LAN firewall setup. This file requests Administrator access,
REM marks the adapter that owns LAN_SERVER_IP as Private when needed, and
REM allows only local-subnet clients to reach Waitress on standard HTTP port 80.

cd /d "%~dp0.."

if not exist "deployment\mysql.local.bat" (
  echo ERROR: deployment\mysql.local.bat was not found.
  pause
  exit /b 1
)
call "deployment\mysql.local.bat"

fltmc.exe >nul 2>&1
if errorlevel 1 (
  echo Requesting Administrator access for the one-time firewall setup...
  powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; $ip = $env:LAN_SERVER_IP; $adapter = Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -eq $ip | Select-Object -First 1; if (-not $adapter) { throw ('No network adapter owns LAN_SERVER_IP ' + $ip) }; $profile = Get-NetConnectionProfile -InterfaceIndex $adapter.InterfaceIndex; if ($profile.NetworkCategory -eq 'Public') { Set-NetConnectionProfile -InterfaceIndex $adapter.InterfaceIndex -NetworkCategory Private }; @('LAN Exam System (TCP 8000)','LAN Exam System (TCP 80)') | ForEach-Object { Get-NetFirewallRule -DisplayName $_ -ErrorAction SilentlyContinue | Remove-NetFirewallRule }; $name = 'LAN Exam System (TCP 80)'; New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Allow -Protocol TCP -LocalPort 80 -RemoteAddress LocalSubnet -Profile Private,Domain | Out-Null; Write-Host ('LAN access enabled for http://exam.ite/ on ' + $ip + ' from the local subnet only.') -ForegroundColor Green"
if errorlevel 1 (
  echo.
  echo Firewall setup failed. Review the error above.
  pause
  exit /b 1
)

echo.
echo Firewall setup complete. You may close this window.
pause
