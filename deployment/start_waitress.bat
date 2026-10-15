@echo off
REM ============================================================
REM Starts the LAN Examination System for real examination use,
REM served by Waitress (not the Django development server).
REM
REM BEFORE FIRST USE: edit the values below (marked EDIT ME) to
REM match your server. See deployment\README_DEPLOYMENT.md for
REM the full explanation of each setting.
REM
REM Run this from the project root (the folder containing
REM manage.py), with the virtual environment already created
REM (see README_DEPLOYMENT.md Section 3).
REM ============================================================

call venv\Scripts\activate.bat

REM ---- Core settings (EDIT ME) --------------------------------
set DJANGO_DEBUG=False
set DJANGO_SECRET_KEY=CHANGE-THIS-TO-A-LONG-RANDOM-STRING-BEFORE-EXAM-DAY
set DJANGO_ALLOWED_HOSTS=192.168.0.200,localhost,127.0.0.1
set DJANGO_CSRF_TRUSTED_ORIGINS=http://192.168.0.200:8000

REM ---- Database (EDIT ME) -------------------------------------
REM Leave DB_ENGINE unset (or "sqlite") to keep using SQLite.
REM Uncomment the block below to use MySQL/MariaDB instead
REM (recommended for ~160 concurrent students - see README_DEPLOYMENT.md
REM Section 5).
REM
set DB_ENGINE=mysql
set DB_NAME=examsystem
set DB_USER=admin_user
set DB_PASSWORD=Fcu3spp4t2b8
set DB_HOST=127.0.0.1
set DB_PORT=3306

echo.
echo Applying database migrations...
python manage.py migrate

echo.
echo Collecting static files...
python manage.py collectstatic --noinput

echo.
echo Starting Waitress on 0.0.0.0:8000 ...
echo Students should browse to: http://YOUR-SERVER-LAN-IP:8000/
echo (the same IP you set in DJANGO_ALLOWED_HOSTS above)
echo (Press CTRL+C to stop the server once the exam period is over.)
echo.
waitress-serve --listen=0.0.0.0:8000 --threads=8 examsystem.wsgi:application

pause
