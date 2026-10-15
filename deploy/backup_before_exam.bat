@echo off
REM ============================================================
REM  LAN Examination System - BEFORE-EXAM backup script
REM  Run this before every examination session.
REM  Works for both SQLite (dev) and MySQL/MariaDB (production) -
REM  it uses Django's own dumpdata command, so it doesn't matter
REM  which database engine is active.
REM ============================================================

REM Must match the same environment variables used in
REM start_exam_server.bat so it backs up the right database.
set DJANGO_DEBUG=False
set DJANGO_DB_ENGINE=mysql
set DJANGO_DB_NAME=examsystem
set DJANGO_DB_USER=examsystem_user
set DJANGO_DB_PASSWORD=CHANGE-THIS-PASSWORD
set DJANGO_DB_HOST=127.0.0.1
set DJANGO_DB_PORT=3306

python manage.py backup_exam_data

echo.
echo Backup complete. The .json file is inside the "backups" folder.
echo Copy it to a USB drive or another computer for safekeeping.
pause
