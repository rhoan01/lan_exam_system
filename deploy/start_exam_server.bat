@echo off
REM ============================================================
REM  LAN Examination System - EXAMINATION DAY startup script
REM ============================================================
REM  Edit the values below ONCE (server IP, DB password, secret
REM  key), then just double-click this file on exam day to start
REM  the server. See DEPLOYMENT.md for full instructions.
REM ============================================================

REM --- Django core settings ---
set DJANGO_DEBUG=False
set DJANGO_SECRET_KEY=CHANGE-THIS-TO-A-LONG-RANDOM-VALUE

REM --- Replace with this server's actual static LAN IP address ---
set DJANGO_ALLOWED_HOSTS=192.168.1.10,localhost,127.0.0.1

REM --- Database: set to "mysql" to use MySQL/MariaDB instead of SQLite ---
set DJANGO_DB_ENGINE=mysql
set DJANGO_DB_NAME=examsystem
set DJANGO_DB_USER=examsystem_user
set DJANGO_DB_PASSWORD=CHANGE-THIS-PASSWORD
set DJANGO_DB_HOST=127.0.0.1
set DJANGO_DB_PORT=3306

echo.
echo Applying database migrations...
python manage.py migrate
if errorlevel 1 goto :error

echo.
echo Collecting static files...
python manage.py collectstatic --noinput
if errorlevel 1 goto :error

echo.
echo ============================================================
echo  Starting exam server.
echo  Students should browse to: http://THIS-SERVER-LAN-IP:8000
echo  (run "ipconfig" in another window if you need to check the IP)
echo  Press CTRL+C to stop the server after the exam.
echo ============================================================
echo.
waitress-serve --listen=0.0.0.0:8000 examsystem.wsgi:application
goto :eof

:error
echo.
echo Something went wrong above - the server was NOT started.
echo Fix the error and run this script again.
pause
