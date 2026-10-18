@echo off
REM Compatibility launcher for the maintained MySQL backup script.
cd /d "%~dp0.."
call "deployment\backup.bat"
