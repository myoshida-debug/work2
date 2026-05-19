from pathlib import Path
import sys

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

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'ja'

TIME_ZONE = 'Asia/Tokyo'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
