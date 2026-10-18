@echo off
setlocal
REM Back up the active MySQL examination database to a timestamped JSON file.

cd /d "%~dp0.."
call "venv\Scripts\activate.bat"

if not exist "deployment\mysql.local.bat" (
  echo ERROR: deployment\mysql.local.bat was not found.
  exit /b 1
)
call "deployment\mysql.local.bat"

python manage.py backup_data
if errorlevel 1 exit /b 1

echo.
echo Backup complete. Copy the new file in backups\ to another device.
