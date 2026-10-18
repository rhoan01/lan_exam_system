@echo off
REM Compatibility launcher. The maintained deployment script lives in
REM deployment\start_waitress.bat and uses the correct DB_* variables.
cd /d "%~dp0.."
call "deployment\start_waitress.bat"
