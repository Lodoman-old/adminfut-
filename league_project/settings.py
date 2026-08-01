import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY') or os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-fallback-dev-only')

DEBUG = (os.environ.get('DEBUG', 'False') == 'True') or (os.environ.get('DJANGO_DEBUG', 'False') == 'True')

ALLOWED_HOSTS = (os.environ.get('ALLOWED_HOSTS', '') or os.environ.get('DJANGO_ALLOWED_HOSTS', '*')).split(',')

CSRF_TRUSTED_ORIGINS = (os.environ.get('CSRF_TRUSTED_ORIGINS', '') or os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '')).split(',') if (os.environ.get('CSRF_TRUSTED_ORIGINS') or os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS')) else []

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'cloudinary_storage',
    'cloudinary',
    'rest_framework',
    'accounts',
    'league',
    'finance',
    'reports',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'league_project.middleware.LoginPermisoMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

if DEBUG:
    MIDDLEWARE.insert(0, 'league_project.middleware.AutoNgrokCSRFMiddleware')

ROOT_URLCONF = 'league_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.media',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'league.context_processors.configuracion_global',
            ],
        },
    },
]

WSGI_APPLICATION = 'league_project.wsgi.application'

import dj_database_url
DATABASES = {
    'default': dj_database_url.config(
        default='sqlite:///db.sqlite3',
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-mx'
TIME_ZONE = 'America/Mexico_City'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

CLOUDINARY_URL = os.environ.get('CLOUDINARY_URL')
CLOUDINARY_STORAGE = {
    'PREFIX': '',
}

MEDIA_URL = 'https://res.cloudinary.com/donvyblde/image/upload/'
MEDIA_ROOT = BASE_DIR / 'media'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

AUTH_USER_MODEL = 'accounts.Usuario'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

SESSION_EXPIRE_AT_BROWSER_CLOSE = True

try:
    from local_settings import *
except ImportError:
    pass

def _apply_infra_config():
    try:
        from league.models import ConfiguracionLiga
        config = ConfiguracionLiga.objects.get(pk=1)
        if config.database_url:
            import dj_database_url
            DATABASES['default'] = dj_database_url.parse(
                config.database_url,
                conn_max_age=600,
                conn_health_checks=True,
            )
    except Exception:
        pass

_apply_infra_config()
