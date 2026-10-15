# LAN Deployment Guide — Windows Server + MySQL/MariaDB + Waitress

This document covers deploying the **LAN Examination System**
(Django project `examsystem`, apps `accounts`, `exams`, `results`) on a
school computer laboratory network for actual examination use with
approximately **160 simultaneous student computers**.

**No Docker, Kubernetes, or any container platform is used or required.**
Everything here runs directly on Windows Server with Python.

---

## Contents

1. [Required software](#1-required-software)
2. [Python environment setup](#2-python-environment-setup)
3. [Virtual environment setup](#3-virtual-environment-setup)
4. [Required Python packages](#4-required-python-packages)
5. [Database setup](#5-database-setup)
6. [Django settings for LAN deployment](#6-django-settings-for-lan-deployment)
7. [ALLOWED_HOSTS configuration](#7-allowed_hosts-configuration)
8. [Static file configuration](#8-static-file-configuration)
9. [Database migration commands](#9-database-migration-commands)
10. [Waitress installation](#10-waitress-installation)
11. [Waitress startup command](#11-waitress-startup-command)
12. [Windows Firewall configuration](#12-windows-firewall-configuration)
13. [Server LAN IP configuration](#13-server-lan-ip-configuration)
14. [How student computers access the system](#14-how-student-computers-access-the-system)
15. [How to start the system before an examination](#15-how-to-start-the-system-before-an-examination)
16. [How to stop the system after an examination](#16-how-to-stop-the-system-after-an-examination)
17. [Database backup procedure](#17-database-backup-procedure)
18. [Recommended pre-examination testing](#18-recommended-pre-examination-testing)
19. [Troubleshooting common LAN connection problems](#19-troubleshooting-common-lan-connection-problems)
20. [What was changed in the code, and why](#20-what-was-changed-in-the-code-and-why)
21. [Honest limitations / what has NOT been tested](#21-honest-limitations--what-has-not-been-tested)

---

## 1. Required software

Install these on the Windows Server 2019 machine that will host the exam:

- **Python 3.10 or newer** (64-bit) — [python.org/downloads](https://www.python.org/downloads/windows/)
  During install, check **"Add python.exe to PATH"**.
- **MySQL Server** or **MariaDB Server** (only if you choose the MySQL
  route for exam day — see [Section 5](#5-database-setup) for when this
  matters vs. when SQLite is fine).
  - MySQL Community Server: https://dev.mysql.com/downloads/mysql/
  - or MariaDB: https://mariadb.org/download/
- A **MySQL client GUI** is optional but convenient: MySQL Workbench or
  HeidiSQL, for creating the database/user and inspecting data if needed.
- No web server (IIS/nginx/Apache) is required — Waitress serves
  everything directly, including static files (via WhiteNoise).
- No Docker, Kubernetes, or container runtime is required or used
  anywhere in this deployment.

## 2. Python environment setup

Confirm Python installed correctly:

```cmd
python --version
```

Should print `Python 3.10.x` or newer.

## 3. Virtual environment setup

From the **project root** (the folder that directly contains
`manage.py` — confirm with `dir` before proceeding):

```cmd
cd C:\path\to\lan_exam_system
python -m venv venv
venv\Scripts\activate
```

Your prompt should now start with `(venv)`. Create the venv **inside**
the project folder (not one level above it) to avoid path confusion.

## 4. Required Python packages

With the venv activated:

```cmd
pip install -r requirements.txt
```

This installs:
- `Django` — the framework
- `waitress` — production WSGI server (replaces `runserver` for exam day)
- `whitenoise` — serves CSS/JS/images directly through Waitress
- `PyMySQL` — pure-Python MySQL/MariaDB driver (no C compiler needed on
  Windows Server; only used if you switch to MySQL)

## 5. Database setup

### Should you use SQLite or MySQL/MariaDB for ~160 concurrent users?

**SQLite's limitation:** SQLite allows many simultaneous *readers*, but
only **one writer at a time** for the whole database file. During an
exam, every answer submission is a write. With ~160 students
potentially submitting within the same few minutes (e.g. everyone
finishing near the time limit), SQLite writes serialize one after
another. Django/SQLite will retry briefly on a locked database, but
under sustained concurrent writes this shows up as slow submissions or
occasional "database is locked" errors.

**Recommendation:** for the actual exam day with ~160 concurrent
students, **use MySQL or MariaDB**. It supports many concurrent writers
without this bottleneck. For development, testing, or a much smaller
class size, SQLite (the default) is fine and requires no extra setup.

This project does **not** hard-code either choice — it switches based
on the `DB_ENGINE` environment variable, so you can develop on SQLite
and only switch to MySQL for exam day itself, without touching code.

### Setting up MySQL/MariaDB

1. Install MySQL Server or MariaDB Server (Section 1) and make sure the
   Windows service is running (`services.msc` → look for "MySQL" —
   should say "Running").
2. Open a MySQL client (command line `mysql -u root -p`, or a GUI) and
   run:

   ```sql
   CREATE DATABASE examsystem CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'examsystem_user'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
   GRANT ALL PRIVILEGES ON examsystem.* TO 'examsystem_user'@'localhost';
   FLUSH PRIVILEGES;
   ```

   (If Django and MySQL run on the *same* server, `'localhost'` is
   correct. If MySQL is on a different machine, use `'%'` or the
   application server's IP instead, and set `DB_HOST` accordingly.)

3. Tell Django to use it by setting environment variables before
   starting the server (see `deployment/start_waitress.bat`, which has
   these ready to fill in):

   ```
   DB_ENGINE=mysql
   DB_NAME=examsystem
   DB_USER=examsystem_user
   DB_PASSWORD=choose-a-strong-password
   DB_HOST=127.0.0.1
   DB_PORT=3306
   ```

### If you already have existing data in SQLite and want to move to MySQL

Your existing student accounts, subjects, exams, questions, and results
in `db.sqlite3` are **not lost** by switching `DB_ENGINE` — they simply
won't appear in the new MySQL database until migrated across. To
migrate the data itself (not just the schema):

```cmd
REM 1. While still pointed at SQLite (DB_ENGINE unset/sqlite), back up your data:
python manage.py backup_data

REM 2. Switch environment variables to MySQL (see above), then create the schema:
python manage.py migrate

REM 3. Load your previously backed-up data into the new MySQL database:
python manage.py loaddata backups\exam_backup_<timestamp>.json
```

This preserves all existing student accounts, instructor accounts,
subjects, exams, questions, attempts, and results — nothing is deleted
or overwritten automatically.

## 6. Django settings for LAN deployment

All production settings are controlled through **environment
variables**, not by editing `examsystem/settings.py` directly. This
keeps the same codebase working for both development and exam day. See
`deployment/.env.example` for the full list, and
`deployment/start_waitress.bat` for a ready-to-edit startup script that
sets them.

Key ones for exam day:
```
DJANGO_SECRET_KEY=<a long random string — do not reuse the example one>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=<server LAN IP>,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://<server LAN IP>:8000
```

`DJANGO_DEBUG=False` is important for a real exam: with `DEBUG=True`,
Django shows full error tracebacks (including internal code and
settings) to anyone who triggers an error — not appropriate once real
students are using the system.

## 7. ALLOWED_HOSTS configuration

Django rejects requests whose `Host` header isn't in `ALLOWED_HOSTS` —
this stops a category of attacks and is required once `DEBUG=False`.
Set it to the server's actual LAN IP (and `localhost`/`127.0.0.1` for
convenience when testing on the server itself):

```
set DJANGO_ALLOWED_HOSTS=192.168.1.10,localhost,127.0.0.1
```

Replace `192.168.1.10` with your real server IP (see [Section 13](#13-server-lan-ip-configuration)).

## 8. Static file configuration

CSS/JS files are served by **WhiteNoise**, bundled directly into the
Waitress-served application — no separate static file server is
needed. Before starting the server for real use, run:

```cmd
python manage.py collectstatic --noinput
```

This copies all static files into the `staticfiles/` folder, where
WhiteNoise serves them from. `deployment/start_waitress.bat` already
runs this automatically each time it starts the server, so you
normally don't need to run it by hand — but re-run it manually if you
edit any CSS/JS and don't see the change reflected.

## 9. Database migration commands

Whenever models change (already done for you in this project) or
you're setting up a fresh database:

```cmd
python manage.py makemigrations
python manage.py migrate
```

Run this once per environment (SQLite for dev, and again after
switching to MySQL for the first time — see Section 5).

## 10. Waitress installation

Already included in `requirements.txt` (Section 4) — `pip install -r
requirements.txt` installs it. Verify with:

```cmd
waitress-serve --help
```

## 11. Waitress startup command

```cmd
waitress-serve --listen=0.0.0.0:8000 --threads=8 examsystem.wsgi:application
```

- `examsystem.wsgi:application` is this project's actual WSGI module —
  confirmed from `examsystem/wsgi.py`.
- `--listen=0.0.0.0:8000` makes it listen on **all** network interfaces
  on port 8000, so it's reachable from other computers on the LAN (not
  just the server itself).
- `--threads=8` lets Waitress handle multiple requests concurrently
  within one process, which is what actually lets 160 students be
  served at once (a single-threaded server would process one request
  at a time). 8 is a reasonable starting point for this workload — you
  can raise it (e.g. `--threads=16`) if load testing (Section 18) shows
  requests queuing up.

`deployment/start_waitress.bat` wraps all of this into one double-clickable script.

## 12. Windows Firewall configuration

By default, Windows Firewall blocks unsolicited inbound connections on
port 8000. To allow student computers to reach the server:

1. Open **Windows Defender Firewall with Advanced Security**
   (search for it in the Start menu).
2. Click **Inbound Rules** → **New Rule...**
3. Rule type: **Port**
4. Protocol: **TCP**, Specific local port: **8000**
5. Action: **Allow the connection**
6. Profile: check **Domain** and **Private** (uncheck **Public** unless
   this server is genuinely on a public network, which it shouldn't be)
7. Name it something like "LAN Exam System (port 8000)"

If Windows prompts to allow `python.exe` or `waitress-serve` through
the firewall the first time you run the server, you can also just
click **Allow** at that prompt instead of creating the rule manually.

## 13. Server LAN IP configuration

Find the server's current LAN IP:

```cmd
ipconfig
```

Look for **IPv4 Address** under the active adapter (Ethernet is
recommended over Wi-Fi for server stability).

**Use a static IP** so it doesn't change between exam sessions (a
DHCP-assigned IP can change after a reboot, which would break student
access and require reconfiguring `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`
each time). To set a static IP on Windows Server:

1. **Control Panel** → **Network and Sharing Center** → **Change
   adapter settings**
2. Right-click the active network adapter → **Properties**
3. Select **Internet Protocol Version 4 (TCP/IPv4)** → **Properties**
4. Choose **Use the following IP address** and enter an IP in your
   school LAN's range (ask whoever manages the network switch/router
   for an address outside the DHCP pool to avoid conflicts), the
   subnet mask, and gateway.

Once set, use that fixed IP consistently in `DJANGO_ALLOWED_HOSTS`,
`DJANGO_CSRF_TRUSTED_ORIGINS`, and when telling students the address.

## 14. How student computers access the system

Once the server is running and reachable, students open a web browser
on their lab computer and go to:

```
http://<server-LAN-IP>:8000/
```

For example, if the server's static IP is `192.168.1.10`:

```
http://192.168.1.10:8000/
```

All computers must be on the **same LAN** (connected to the same
network switch, or the same Wi-Fi network if applicable). The system
is not exposed to the public internet — only devices on the local
network can reach it, which is intentional. Students do not need
internet access at all, and the system is not meant to be
internet-facing.

## 15. How to start the system before an examination

1. Log into the server.
2. Open Command Prompt.
3. `cd` into the project folder.
4. Run:
   ```cmd
   venv\Scripts\activate
   deployment\start_waitress.bat
   ```
   (or just double-click `start_waitress.bat` in File Explorer, after
   editing it once with your real IP/credentials — see the file's
   comments).
5. Confirm you see `Serving on http://0.0.0.0:8000` in the console
   with no errors.
6. From another computer on the LAN, browse to
   `http://<server-IP>:8000/` to confirm it loads before students
   arrive.

Leave that Command Prompt window open and running for the entire
duration of the exam — closing it stops the server.

## 16. How to stop the system after an examination

In the Command Prompt window running Waitress, press:

```
CTRL + C
```

This gracefully stops accepting new connections. Confirm the console
returns to a normal prompt. It's safe to close the window after that.

**Do not** stop the server while students are actively in the middle of
an exam — always inform students of the exam's cutoff time and only
stop the server afterward, since additional submissions can't be
recorded once the server is down. If a student's browser still shows
the exam page while the server is stopped, their timer will keep
running visually in JavaScript, but their submission attempt will fail
until the server is back up.

Also worth noting for overall stability during the exam period:
- Disable sleep/hibernation on the server (**Control Panel → Power
  Options → Choose when to turn off the display/put the computer to
  sleep** → set both to **Never** while an exam is in progress).
- Use a wired Ethernet connection for the server rather than Wi-Fi.
- Use a UPS if one is available, to protect against power interruptions.
- Avoid Windows Update reboots and other software installs during the
  exam window.

## 17. Database backup procedure

Use the built-in `backup_data` management command, which exports all
student accounts, instructor accounts, subjects, exams, questions,
answer keys, attempts, and answers to a single timestamped JSON file:

```cmd
python manage.py backup_data
```

By default this saves into a `backups\` folder inside the project
(created automatically). To specify a different location, e.g. an
external drive:

```cmd
python manage.py backup_data --output-dir=D:\ExamBackups
```

**Recommended timing:**
- Run it **before** the exam period starts (captures the "clean"
  state — registered students, exams, questions).
- Run it again **immediately after** the exam period ends (captures
  final scores/results).

To restore a backup (e.g. onto a freshly migrated database):

```cmd
python manage.py loaddata "backups\exam_backup_20260101_090000.json"
```

`deployment\backup.bat` wraps the backup command for convenience.

**If using MySQL**, you can additionally take a full raw database dump
as a second safety net (this captures everything at the database level,
independent of Django):

```cmd
mysqldump -u examsystem_user -p examsystem > examsystem_backup.sql
```

This command never deletes existing data — running it repeatedly just
produces additional backup files (or, for `loaddata`, adds/updates
records; it does not wipe the database first).

## 18. Recommended pre-examination testing

**Important — please read Section 21 first.** This project was built
in a sandbox with no internet access and no Django installation, so an
actual 160-concurrent-user load test could not be run there. The
system has **not** been empirically verified to handle 160 simultaneous
users — the changes made (Section 20) are targeted at removing the
most obvious bottlenecks, but "the obvious bottlenecks were fixed" is a
narrower claim than "confirmed to handle 160 users," and you should
treat it that way until you've run a rehearsal test on your actual
hardware.

### A practical LAN test you can run yourself, without extra tools

1. **Small-scale first:** have 5-10 people (staff or students) log in
   and take a short test exam simultaneously from different lab
   computers. Confirm timers, submissions, and scores all work
   correctly.
2. **Scale up:** if possible, schedule a rehearsal with a full room (or
   as many computers as you can gather) taking a real practice exam at
   the same time, ideally the number closest to your actual 160.
3. **Watch the server console** during the test for any error
   tracebacks.
4. **Watch response times** — if pages start taking several seconds to
   load as more students join, that's a sign to increase `--threads`
   in the Waitress command (Section 11), or confirms you should be on
   MySQL rather than SQLite (Section 5).

### A scripted concurrency test (optional, for the technically inclined)

If you have Python and want a rough automated load test, the
[`locust`](https://locust.io/) tool (a separate pip package, not
included here since it's a testing tool rather than part of the exam
system itself) lets you simulate many simultaneous virtual users
hitting the login and exam pages. This is optional — the manual
rehearsal above is the more realistic test for this specific use case.

### Things specifically worth testing before relying on this for a real exam

- 160 (or as many as available) simultaneous logins
- Multiple students opening the same exam at once
- Multiple students submitting within the same minute (worst case:
  everyone submits right as the timer hits zero)
- An instructor viewing results while students are still testing
- Attempting to access another student's or another exam's URL
  directly (e.g. by editing the number in
  `/student/attempts/5/result/` in the address bar) while logged in as
  a different student — should be blocked (this is already enforced in
  the code; see Section 20)
- Publishing/unpublishing an exam while students are logged in

## 19. Troubleshooting common LAN connection problems

**"This site can't be reached" from a student computer**
- Confirm the student's computer is on the same LAN/switch as the server.
- Confirm you used the server's actual LAN IP, not `127.0.0.1` or
  `0.0.0.0` (those only work *on* the server itself).
- Confirm Waitress is actually running (check the server's console
  window).
- Confirm the Windows Firewall rule from Section 12 is in place.

**`DisallowedHost` error / "Invalid HTTP_HOST header"**
- The IP/hostname students are using isn't in `DJANGO_ALLOWED_HOSTS`.
  Add it (Section 7) and restart the server.

**"CSRF verification failed" when submitting a form**
- Add the exact address students use (including `http://` and the
  port) to `DJANGO_CSRF_TRUSTED_ORIGINS` (Section 6) and restart.

**Server was reachable before but not after a reboot**
- The server's IP likely changed (if it wasn't set to static — see
  Section 13). Reconfigure to a static IP to prevent this.

**Static files (CSS) not loading — page looks unstyled**
- Run `python manage.py collectstatic --noinput` again (Section 8) and
  restart Waitress.

**"database is locked" errors during the exam**
- You're likely still on SQLite under real concurrent load. Switch to
  MySQL/MariaDB (Section 5).

**Students report their timer hit zero but nothing happened / an error appeared**
- Confirm the server is still running and reachable from their
  machine (see the first troubleshooting item). The timer runs in the
  student's browser; the actual grading happens when their browser
  successfully reaches the server to submit.

---

## 20. What was changed in the code, and why

These changes were made to the existing project to support the ~160
concurrent LAN examination use case. **Nothing about the existing
features, UI, or working functionality was removed or rebuilt** — this
was additive/configuration work plus targeted performance fixes.

- **`examsystem/settings.py`** — rewritten to read `SECRET_KEY`,
  `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and database
  settings from environment variables, defaulting to the same SQLite +
  DEBUG=True development behavior as before if no environment
  variables are set. Added MySQL support (via PyMySQL) behind
  `DB_ENGINE=mysql`, WhiteNoise for static files, and cached-DB
  sessions (fewer database hits per request under concurrent load).
- **`exams/models.py`** — added a database index on `Exam.is_published`,
  since every student's dashboard load and exam-access check filters on
  this field.
- **`results/views.py`** (the exam submission/grading path — the
  highest-traffic part of the system during an exam) —
  - `_auto_grade_and_submit` previously ran one database query *per
    question* to fetch that question's answer, plus one more query per
    question to save its grade — up to ~200 queries for a 100-item exam,
    multiplied by however many students submit around the same time.
    It now fetches all answers in a single query and saves all grades
    in a single `bulk_update`, regardless of item count.
  - `submit_exam` previously queried the database once per multiple-choice
    question just to validate the selected choice, and wrote each
    answer with a separate `update_or_create`. It now prefetches all
    questions and choices once, matches the submitted choice in memory,
    and writes all new/changed answers with a single `bulk_create`
    and/or `bulk_update`.
  - `submit_exam` now wraps the whole submission in
    `transaction.atomic()` with `select_for_update()` on the student's
    attempt row, so a duplicate or near-simultaneous submit (e.g. the
    JavaScript timer firing at the same moment as a manual click)
    cannot double-grade or corrupt the same attempt.
  - `take_exam`'s attempt creation now tolerates a rare race condition
    (two near-simultaneous requests for the same student+exam) instead
    of raising an error, falling back to fetching the row that "won."
- **`accounts/management/commands/backup_data.py`** — new command
  producing a timestamped JSON backup of all examination data,
  independent of whether you're on SQLite or MySQL.
- **`requirements.txt`** — added `waitress`, `whitenoise`, and
  `PyMySQL`.
- **New `deployment/` folder** — this guide, plus
  `start_waitress.bat`, `backup.bat`, and `.env.example` to make the
  above configuration concrete and copy-pasteable.

**Access control was already in place** in the existing code before
these changes (every instructor view filters by
`subject__instructor=request.user`; every student exam/result view
filters by `student=request.user`; unpublished exams are excluded from
student-facing queries) — this was verified by re-reading the relevant
views, not re-implemented, since it was already correct.

## 21. Honest limitations / what has NOT been tested

To be direct about the boundaries of what's been verified:

- **No live load test was performed.** The environment this project
  was built in has no internet access and no Django installation, so
  it was not possible to actually spin up the server and simulate 160
  concurrent users. The performance changes in Section 20 target
  specific, identifiable bottlenecks (N+1 queries during grading,
  SQLite's single-writer limitation, unindexed lookups) — but that is
  a narrower claim than "confirmed to handle 160 users," and you
  should treat it that way until you've run the rehearsal test in
  Section 18 on your actual hardware.
- **Waitress's `--threads` value (8) is a reasonable starting point,
  not a benchmarked number** for your specific server's CPU/RAM. Adjust
  based on what your own rehearsal test shows.
- **MySQL vs. MariaDB:** both are supported identically through the
  same `DB_ENGINE=mysql` setting (MariaDB is wire-compatible with
  MySQL's protocol), but only the general approach was verified by
  reasoning through Django's MySQL backend requirements — an actual
  MySQL/MariaDB server was not available to connect to and test
  against in this environment.
