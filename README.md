# LAN-Based Examination System (Django)

A self-contained exam system designed to run on a local network (no internet
required) — students register and take timed exams; instructors act as
admins who create subjects, exams, and upload answer keys, with automatic
scoring.

## Features

- **Student registration/login** with ID Number, Name, Year, Section, Course
  (ID Number doubles as the login username).
- **Instructor accounts** created by the system administrator (via
  `createsuperuser` or the `create_instructor` command below) — instructors
  manage everything through the app, and also get full Django admin access.
- **Subjects → Exams → Questions** hierarchy. Each exam:
  - Has an **adjustable countdown timer** (set in minutes per exam).
  - Supports up to **100 items** total.
  - Supports 4 question types: **Multiple Choice, Enumeration,
    Identification, and Case Analysis** (free-typed answer).
- **Answer key upload** for Enumeration / Identification / Case Analysis
  questions (instructor types the accepted answers/keywords).
- **Automatic grading** the moment a student submits:
  - Multiple Choice — exact match.
  - Identification — matches any accepted answer (case-insensitive).
  - Enumeration — partial credit based on how many expected items were
    correctly supplied.
  - Case Analysis — keyword-matching auto score (flagged for optional
    instructor review, since it's free-typed text).
- **Question navigator**: a numbered grid the student can hover over
  (tooltip shows answered/unanswered) and click to jump to — freely skip
  ahead and return to any item before submitting.
- **Timer auto-submits** the exam when time runs out (also re-checked
  server-side, so the client clock can't be tampered with).
- Scores, subject, and student are all stored in the database and viewable
  by the instructor per exam (`/instructor/exams/<id>/results/`) and by the
  student on their own dashboard.

## Deploying for a real examination (Windows Server + MySQL + Waitress)

The steps below (SQLite + `runserver`) are for development and small
tryouts. For an actual exam with a full computer lab (~100+ students
submitting at once), see **[`deployment/README_DEPLOYMENT.md`](deployment/README_DEPLOYMENT.md)**,
which covers: switching to MySQL/MariaDB, running behind Waitress
instead of the development server, Windows Firewall/LAN configuration,
starting/stopping the system on exam day, backing up exam data, and
pre-exam testing recommendations. No Docker or container platform is
used anywhere in this project.

## Requirements

- Python 3.10+
- Django 4.2 (see `requirements.txt`)

This sandbox had no internet access, so the project could not be pip-installed
or run here — please run the steps below on your own machine.

## Setup

```bash
# 1. (Recommended) create a virtual environment
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 2. Install Django
pip install -r requirements.txt

# 3. Create the database tables
python manage.py makemigrations
python manage.py migrate

# 4. Create your first instructor/admin account
python manage.py create_instructor jdelacruz your-password --first_name Juan --last_name "Dela Cruz"
# (or: python manage.py createsuperuser — superusers are auto-flagged as instructors)

# 5. Run the server so it's reachable on your LAN
python manage.py runserver 0.0.0.0:8000
```

Then, from any device on the same LAN, browse to:
`http://<server-ip-address>:8000/`

- Students go to **Register** to create their own account.
- Instructors log in with the account created in step 4, and land on the
  **Instructor Dashboard**.
- The Django admin site is also available at `/admin/` for the instructor
  if they want direct database-level management.

## Typical instructor workflow

1. Log in → **+ New Subject** (code + name).
2. Inside the subject → **+ New Exam** (title, instructions, adjustable
   timer in minutes).
3. Inside the exam → **+ Add Question** repeatedly (up to 100 items),
   choosing a type each time:
   - *Multiple Choice*: type the question, add choices, tick the correct one.
   - *Enumeration*: type the question, set how many answers are expected,
     then list the accepted answers (answer key), one per line.
   - *Identification*: list accepted answer(s), one per line.
   - *Case Analysis*: list key concepts/keywords the answer should contain
     — this is what auto-grades the typed response.
4. Click **Publish** once ready — only published exams appear to students.
5. After students take it, click **View Results** to see each student's
   name, ID number, course/year/section, and score.

## Typical student workflow

1. **Register** with ID Number, Name, Year, Section, Course.
2. Log in → see **Available Exams** on the dashboard → **Start Exam**.
3. Answer items in any order using the **question navigator** grid on the
   right (hover to preview, click to jump — skip and come back freely).
4. Watch the countdown timer; it auto-submits when time is up.
5. Click **Submit Exam** any time to finish early — the score is shown
   immediately afterward, along with a per-item point breakdown.

## Notes on this codebase

- All styling/JS is self-hosted (no external CDNs), so it works fully
  offline on a LAN.
- SQLite is used by default (`db.sqlite3`) — a single file, no separate
  database server needed. For a busier deployment you can switch
  `DATABASES` in `examsystem/settings.py` to Postgres/MySQL.
- Before real deployment: change `SECRET_KEY` in `settings.py`, set
  `DEBUG = False`, and set `ALLOWED_HOSTS` to your server's LAN IP.
- Case Analysis grading is keyword-based (a practical approach for
  auto-scoring free text); instructors can still review those specific
  answers via the Django admin (`ExamAttempt` → inline student answers)
  since they're flagged "for review."
