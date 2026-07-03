import os
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

SECRET_KEY = 'django-insecure-anonymizer-demo'

DEBUG = True

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'anonymizer_app',
    'close_side',
    'open_side',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'anonymizer_app.network_policy.NetworkSegmentPolicyMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

NETWORK_POLICY_ENFORCED = True
NETWORK_POLICY_ALLOW_LOOPBACK = DEBUG
NETWORK_POLICY_TRUST_X_FORWARDED_FOR = True
NETWORK_POLICY = {
    'close_side': {
        'label': 'CloseSide',
        'paths': ['/close/'],
        'cidrs': ['192.168.50.0/24'],
    },
    'open_side': {
        'label': 'OpenSide',
        'paths': ['/open/'],
        'cidrs': ['192.168.110.0/24'],
    },
    'dmz': {
        'label': 'DMZ',
        'paths': [],
        'cidrs': ['192.168.150.0/24'],
    },
}

ROOT_URLCONF = 'anonflow.urls'

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

WSGI_APPLICATION = 'anonflow.wsgi.application'


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _sqlite_database_config() -> dict[str, object]:
    return {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }


def _postgres_database_config(*, parsed=None) -> dict[str, object]:
    parsed_name = unquote(parsed.path.lstrip('/')) if parsed and parsed.path else ''
    parsed_user = unquote(parsed.username or '') if parsed else ''
    parsed_password = unquote(parsed.password or '') if parsed else ''
    parsed_host = parsed.hostname if parsed else None
    parsed_port = parsed.port if parsed else None
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': parsed_name or os.environ.get('POSTGRES_DB', 'anonflow'),
        'USER': parsed_user or os.environ.get('POSTGRES_USER', 'anonflow'),
        'PASSWORD': parsed_password or os.environ.get('POSTGRES_PASSWORD', ''),
        'HOST': parsed_host or os.environ.get('POSTGRES_HOST', '127.0.0.1'),
        'PORT': str(parsed_port or os.environ.get('POSTGRES_PORT', '5432')),
        'CONN_MAX_AGE': int(os.environ.get('POSTGRES_CONN_MAX_AGE', '60') or 60),
    }


def _build_database_config() -> dict[str, dict[str, object]]:
    database_url = os.environ.get('DATABASE_URL', '').strip()
    if database_url:
        parsed = urlparse(database_url)
        scheme = (parsed.scheme or '').split('+', 1)[0].lower()
        if scheme in {'postgres', 'postgresql'}:
            return {'default': _postgres_database_config(parsed=parsed)}
        if scheme == 'sqlite':
            return {'default': _sqlite_database_config()}
    if _env_bool('USE_POSTGRESQL') or any(
        os.environ.get(name)
        for name in ('POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_HOST', 'POSTGRES_PORT')
    ):
        return {'default': _postgres_database_config()}
    return {'default': _sqlite_database_config()}


DATABASES = _build_database_config()

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'ja'

TIME_ZONE = 'Asia/Tokyo'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
