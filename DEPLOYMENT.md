# LAN Deployment Guide — Examination Day

This guide explains how to run the **LAN Examination System** (Django project
`examsystem`) on a school computer laboratory network for an actual
examination with ~160 simultaneous students.

**No Docker, Kubernetes, or cloud hosting is used or required.** The target
environment is plain Windows Server 2019 + Python + MySQL/MariaDB + Waitress.

---

## 1. Development vs. Examination Deployment

| | Development / testing | Examination day |
|---|---|---|
| Command | `python manage.py runserver` | `waitress-serve --listen=0.0.0.0:8000 examsystem.wsgi:application` |
| Database | SQLite (`db.sqlite3`) | MySQL / MariaDB |
| `DJANGO_DEBUG` | not set (defaults to `True`) | `False` |
| Who can connect | just your own PC | every PC on the school LAN |

The codebase is identical for both — switching between them is just a matter
of which environment variables are set before starting the server. Nothing
about the existing UI or functionality changes.

---

## 2. Required Software (install once, ahead of exam day)

1. **Windows Server 2019**
2. **Python 3.10+** (from python.org) — during install, check "Add python.exe
   to PATH".
3. **MySQL 8.0.11+** or **MariaDB 10.5+**. Older bundled database servers
   (including XAMPP MariaDB 10.4) are not supported by Django 5.2.
4. A **Gigabit LAN switch** connecting the server and student PCs.

---

## 3. Python Environment Setup

Open **Command Prompt** in the project folder (the one containing
`manage.py`) and run:

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

This installs Django, **Waitress** (production WSGI server), **PyMySQL**
(pure-Python MySQL/MariaDB driver — no C compiler needed on Windows), and
**whitenoise** (serves CSS/JS/images without needing IIS).

Run `venv\Scripts\activate` again every time you open a new Command Prompt
to work on the project.

---

## 4. Database Setup — SQLite vs. MySQL/MariaDB

### Why not keep SQLite for the actual exam?

SQLite allows only **one writer at a time**. During an exam, ~160 students
may submit answers within the same few minutes — each submission is a
database write. Under SQLite, these writes queue up one-by-one and can
time out ("database is locked") under real concurrent load. SQLite remains
perfectly fine for development and small-scale testing, which is why it's
still the default when no environment variables are set.

**Recommendation: use MySQL or MariaDB for the actual ~160-user
examination.** It handles many simultaneous connections and concurrent
writes properly, which is exactly the examination workload described above.

### Creating the MySQL/MariaDB database

In the MySQL/MariaDB command-line client (or a GUI tool like phpMyAdmin/
HeidiSQL), run:

```sql
CREATE DATABASE examsystem CHARACTER SET utf8mb4;
CREATE USER 'examsystem_user'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
GRANT ALL PRIVILEGES ON examsystem.* TO 'examsystem_user'@'localhost';
FLUSH PRIVILEGES;
```

### Pointing Django at it

Copy `deployment\.env.example` to the ignored
`deployment\mysql.local.bat` file and set these values. Both maintained
launchers load that private file automatically:

```bat
set DB_ENGINE=mysql
set DB_NAME=examsystem
set DB_USER=examsystem_user
set DB_PASSWORD=choose-a-strong-password
set DB_HOST=127.0.0.1
set DB_PORT=3306
```

If these variables are **not** set, the app automatically falls back to
SQLite — nothing breaks for local development.

### Migrating

The project already includes its migration history. On first-time setup run:

```bat
python manage.py migrate
python manage.py create_instructor <username> <password>
```

If you were previously testing with SQLite and already have real data in
`db.sqlite3` that you want to carry over into MySQL, back it up first (see
Section 8), point the environment variables at MySQL, run `migrate` to
create empty tables, then restore the backup with:

```bat
python manage.py loaddata backups\your_backup_file.json
```

---

## 5. Django Settings for LAN Deployment

`examsystem/settings.py` reads the following environment variables (all
optional — sensible development defaults are used if unset):

| Variable | Purpose | Example |
|---|---|---|
| `DJANGO_DEBUG` | `False` on exam day | `False` |
| `DJANGO_SECRET_KEY` | Random secret, keep private | (long random string) |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts allowed to connect | `192.168.1.10,localhost,127.0.0.1` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Only needed if using HTTPS or a hostname | `http://examserver:8000` |
| `DB_ENGINE` | `mysql` or leave unset for SQLite | `mysql` |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | MySQL/MariaDB connection | see above |

**`ALLOWED_HOSTS`** must include the server's LAN IP address (or `*` during
testing) or Django will reject requests from student PCs with a
"Bad Request (400)" error.

---

## 6. Static Files

Static files (CSS/JS/images) are unchanged from the existing project —
`STATIC_ROOT` and `STATICFILES_DIRS` were already configured correctly.
Before exam day, run:

```bat
python manage.py collectstatic --noinput
```

With `whitenoise` installed (already in `requirements.txt`), Waitress will
correctly serve these files even with `DJANGO_DEBUG=False` — no separate
web server (IIS/nginx) is required.

---

## 7. LAN Network Access

### Give the server a static LAN IP

On the Windows Server: **Control Panel → Network and Sharing Center →
Change adapter settings → (your NIC) → Properties → Internet Protocol
Version 4 → Properties** → set a static IP, e.g. `192.168.1.10`, matching
your school's LAN addressing.

### Windows Firewall

Allow inbound TCP port 8000:

```bat
netsh advfirewall firewall add rule name="Exam System" dir=in action=allow protocol=TCP localport=8000
```

(Or via GUI: **Windows Defender Firewall with Advanced Security → Inbound
Rules → New Rule → Port → TCP 8000 → Allow the connection**.)

### Starting the server

```bat
waitress-serve --listen=0.0.0.0:8000 examsystem.wsgi:application
```

Listening on `0.0.0.0` (not `127.0.0.1`) is what makes the server reachable
from other PCs on the LAN, not just the server itself.

### How students connect

On each student PC, open a browser and go to:

```
http://192.168.1.10:8000
```

(replace with your server's actual static IP). Consider writing this URL on
the whiteboard, or setting it as the student PCs' browser homepage before
the exam.

This system stays on the internal school LAN only — it is **not** exposed
to the public Internet.

---

## 8. Database Backup

Before every examination, take a backup:

```bat
python manage.py backup_data
```

This uses Django's own data export (works identically for SQLite and
MySQL/MariaDB) and writes a timestamped `.json` file into the `backups\`
folder, containing all accounts, subjects, exams, questions, answer keys,
attempts, answers, and results. Copy that file to a USB drive or another
computer afterward.

To restore a backup:

```bat
python manage.py loaddata backups\exam_backup_20260101_080000.json
```

`deploy\backup_before_exam.bat` runs this for you with one double-click and
loads the same ignored `deployment\mysql.local.bat` configuration.

The backup command never deletes existing data — it only reads and exports.
Avoid restoring a backup, running `migrate`, or making other destructive
database changes while an examination is actively in progress.

---

## 9. Starting and Stopping the System

**One-time network setup:** double-click
`deployment\configure_firewall_admin.bat` and accept the Administrator
prompt. It limits TCP 8000 access to the local subnet.

**Before the exam:** double-click `deploy\start_exam_server.bat`. Leave the
Command Prompt window open — closing it stops the web server.

**After the exam:** press `Ctrl+C` in that Command Prompt window, or simply
close the window.

### Keeping the server up for the whole exam period

- Disable Windows Server sleep/hibernation: **Control Panel → Power
  Options → Choose when to turn off the display → set "Put the computer to
  sleep" to Never.**
- Use a wired Ethernet connection to the server, not Wi-Fi.
- Use a UPS if available, in case of a brief power interruption.
- Don't install Windows Updates or reboot the server during an active exam
  window.
- Keep the Command Prompt window with `waitress-serve` running open and
  visible for the whole exam.

---

## 10. Pre-Examination Load Testing

Before trusting this system with a real exam, test it with a load close to
160 concurrent users. Options, from simplest to most thorough:

1. **Manual LAN test:** have as many staff/student volunteers as you can
   gather log in and take a short practice exam simultaneously from
   different computers, while you watch for slow pages or errors.
2. **Scripted load test (recommended if feasible):** use a tool such as
   [Locust](https://locust.io/) or [k6](https://k6.io/) from a separate
   machine on the LAN to simulate ~160 virtual students logging in, opening
   an exam, and submitting answers, pointed at
   `http://<server-ip>:8000`.
3. At minimum, test: simultaneous logins, simultaneous exam loading,
   simultaneous answer submission, an instructor viewing results while
   students are still testing, and toggling an exam's publish/lock status
   while students are logged in.

**Do not assume the system can handle 160 concurrent users without testing
it at that scale first** — the code changes in this deployment (MySQL,
query optimizations) are designed to support that load, but only an actual
test on your specific hardware and network confirms it.

If a full scripted load test isn't possible in your environment, the
manual LAN test above, run a few days before the real exam, is the
practical minimum.

---

## 11. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Student PC gets "This site can't be reached" | Server not started, wrong IP, or firewall blocking port 8000. Confirm `ipconfig` on the server for the correct IP, confirm the firewall rule from Section 7. |
| Django shows "Bad Request (400)" | The URL/IP a student used isn't in `DJANGO_ALLOWED_HOSTS`. Add it and restart the server. |
| "database is locked" errors during the exam | Still running on SQLite under real concurrent load. Switch to MySQL/MariaDB per Section 4. |
| CSS/styling missing after `DJANGO_DEBUG=False` | Run `python manage.py collectstatic --noinput` before starting the server. |
| CSRF / "Forbidden" errors on submit | If accessing via a hostname instead of a raw IP, add it to `DJANGO_CSRF_TRUSTED_ORIGINS`. |
| Server IP changed since last exam | Re-run the firewall rule if needed, update `DJANGO_ALLOWED_HOSTS` and the URL you give students. Consider setting a DHCP reservation or static IP so this doesn't happen again. |

---

## 12. Final Architecture

```
                    SCHOOL LAN
                        |
                 Gigabit Network
                        |
              +---------+---------+
              |                   |
       Windows Server 2019    Student PCs (~160)
              |
           Waitress
              |
            Django (examsystem)
              |
         MySQL / MariaDB
```

No Docker, Kubernetes, or public Internet exposure at any point in this
architecture.
