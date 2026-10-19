"""
Django settings for the LAN-Based Examination System.

This project is designed to run on a local area network (LAN) without
requiring internet access, Docker, or any container platform.

Two deployment modes are supported, controlled entirely by environment
variables (nothing below needs to be hand-edited for a normal deployment):

  DEVELOPMENT (default, if no environment variables are set):
    - SQLite database (db.sqlite3)
    - DEBUG = True
    - `python manage.py runserver`

  PRODUCTION / EXAMINATION DAY (set environment variables, see
  deployment/README_DEPLOYMENT.md for the full walkthrough):
    - MySQL / MariaDB database
    - DEBUG = False
    - Served through Waitress: `waitress-serve --listen=0.0.0.0:8000 examsystem.wsgi:application`

Environment variables recognized (all optional; sensible dev defaults if unset):
    DJANGO_SECRET_KEY        - secret key (set a real one in production)
    DJANGO_DEBUG             - "True" / "False" (default: True)
    DJANGO_ALLOWED_HOSTS     - comma-separated hosts/IPs, e.g. "192.168.1.10,examserver"
    DJANGO_CSRF_TRUSTED_ORIGINS - comma-separated origins, e.g. "http://192.168.1.10:8000"
    DB_ENGINE                - "sqlite" (default) or "mysql"
    DB_NAME                  - database name (mysql only; default "examsystem")
    DB_USER                  - database user (mysql only)
    DB_PASSWORD              - database password (mysql only)
    DB_HOST                  - database host (mysql only; default "127.0.0.1")
    DB_PORT                  - database port (mysql only; default "3306")
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def _env_list(name, default=None):
    value = os.environ.get(name)
    if not value:
        return default or []
    return [item.strip() for item in value.split(',') if item.strip()]


# SECURITY WARNING: keep the default only for local development. Set
# DJANGO_SECRET_KEY to a long random value before deploying for real use.
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-CHANGE-THIS-SECRET-KEY-BEFORE-DEPLOYING'
)

DEBUG = _env_bool('DJANGO_DEBUG', True)

# '*' is convenient for local development but should NOT be used for the
# actual examination deployment. Set DJANGO_ALLOWED_HOSTS to the server's
# LAN IP / hostname instead, e.g. "192.168.1.10,examserver".
ALLOWED_HOSTS = _env_list('DJANGO_ALLOWED_HOSTS', ['*'] if DEBUG else [])
LAN_HOSTNAME = os.environ.get('LAN_HOSTNAME', 'exam.ite').strip().lower()
if LAN_HOSTNAME and LAN_HOSTNAME not in ALLOWED_HOSTS and '*' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(LAN_HOSTNAME)

# Needed when serving over plain http:// from a LAN IP so Django accepts
# POST requests (form submissions) with a valid CSRF token. Set this to
# match how students actually reach the server, e.g.:
# DJANGO_CSRF_TRUSTED_ORIGINS=http://192.168.1.10:8000
CSRF_TRUSTED_ORIGINS = _env_list('DJANGO_CSRF_TRUSTED_ORIGINS', [])
if LAN_HOSTNAME:
    lan_origin = f'http://{LAN_HOSTNAME}'
    if lan_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(lan_origin)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Local apps
    'accounts',
    'exams',
    'results',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise serves static files directly from the WSGI app (Waitress),
    # so no separate web server (nginx/IIS) is required for CSS/JS/images.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'examsystem.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'examsystem.wsgi.application'

# ----------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------
# DB_ENGINE=sqlite (default) -> single-file SQLite database, fine for
#     development, testing, and small trial runs.
# DB_ENGINE=mysql -> MySQL / MariaDB, recommended for the actual
#     examination day with hundreds of concurrent students (see
#     deployment/README_DEPLOYMENT.md for why, and for setup steps).
DB_ENGINE = os.environ.get('DB_ENGINE', 'sqlite').strip().lower()

if DB_ENGINE not in {'sqlite', 'mysql'}:
    raise ImproperlyConfigured(
        'DB_ENGINE must be either "sqlite" or "mysql"; '
        f'received {DB_ENGINE!r}.'
    )

if DB_ENGINE == 'mysql':
    # PyMySQL is a pure-Python MySQL driver: no C build tools needed on
    # Windows Server, unlike mysqlclient. It's registered here to act as
    # a drop-in replacement for MySQLdb, which Django's mysql backend expects.
    import pymysql
    pymysql.install_as_MySQLdb()

    db_password = os.environ.get('DB_PASSWORD', '')
    if not db_password:
        raise ImproperlyConfigured(
            'DB_PASSWORD must be set when DB_ENGINE=mysql.'
        )

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ.get('DB_NAME', 'examsystem'),
            'USER': os.environ.get('DB_USER', 'examsystem_user'),
            'PASSWORD': db_password,
            'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
            'PORT': os.environ.get('DB_PORT', '3306'),
            'OPTIONS': {
                'charset': 'utf8mb4',
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
            # Waitress owns a bounded thread pool, so at most one persistent
            # database connection per active worker thread is needed. Reusing
            # these connections avoids setup overhead during autosave bursts.
            'CONN_MAX_AGE': 60,
            'CONN_HEALTH_CHECKS': True,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 6}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
# Django 5.1 removed the legacy STATICFILES_STORAGE setting. Configure both
# default and static-file backends through STORAGES instead. WhiteNoise's
# non-manifest backend keeps local development usable before collectstatic.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'accounts:redirect_after_login'
LOGOUT_REDIRECT_URL = 'accounts:login'

# ----------------------------------------------------------------------
# Sessions / performance under concurrent LAN load
# ----------------------------------------------------------------------
# Cached-DB sessions avoid a database round trip on every single request
# just to validate the session, while still persisting sessions if the
# process restarts. Requires a CACHES entry; LocMemCache is fine for a
# single-process Waitress deployment (see deployment docs for the
# recommended --threads setting).
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
