@echo off
REM ============================================================
REM Backs up all examination data (accounts, subjects, exams,
REM questions, attempts, and scores) to a timestamped JSON file
REM in the "backups" folder.
REM
REM Safe to run at any time, including while an exam is in
REM progress - it only reads data, it never deletes or changes
REM anything.
REM
REM Run this from the project root, with the same environment
REM variables set as when the server is running (so it connects
REM to the same database - MySQL settings if you're using MySQL).
REM ============================================================

call venv\Scripts\activate.bat

python manage.py backup_data

pause
