"""
These settings are here to use during tests, because django requires them.

In a real-world use case, apps in this project are installed into other
Django applications, so these settings will not be used.
"""

from __future__ import absolute_import, unicode_literals

from os.path import abspath, dirname, join


def root(*args):
    """
    Get the absolute path of the given path relative to the project root.
    """
    return join(abspath(dirname(__file__)), *args)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "default.db",
        "USER": "",
        "PASSWORD": "",
        "HOST": "",
        "PORT": "",
    }
}

INSTALLED_APPS = (
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sites",
    "django.contrib.sessions",
    "django.contrib.admin",  # only used in DEBUG mode
    "django.contrib.messages",
    "waffle",

    "enterprise",
    "consent",
    "integrated_channels.integrated_channel",
    "integrated_channels.sap_success_factors",
)

MIDDLEWARE_CLASSES = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

MIDDLEWARE = MIDDLEWARE_CLASSES  # Django 1.10 compatibility - the setting was renamed

AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

SESSION_ENGINE = "django.contrib.sessions.backends.file"

LOCALE_PATHS = [
    root("enterprise", "conf", "locale"),
]

MAKO_TEMPLATES = {
    "main": []
}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": {
                "django.contrib.auth.context_processors.auth",  # this is required for admin
                "django.contrib.messages.context_processors.messages",
            }
        }
    },
]

PLATFORM_NAME = "Test platform"
PLATFORM_DESCRIPTION = "Test description"

ROOT_URLCONF = "enterprise.urls"

SECRET_KEY = "insecure-secret-key"

# Default Site id
SITE_ID = 1

EDX_API_KEY = "PUT_YOUR_API_KEY_HERE"

COURSE_CATALOG_API_URL = "http://localhost:18381/api/v1/"

LMS_ROOT_URL = "http://localhost:8000"
ECOMMERCE_PUBLIC_URL_ROOT = "http://localhost:18130"

ENTERPRISE_ENROLLMENT_API_URL = LMS_ROOT_URL + "/api/enrollment/v1/"

ENTERPRISE_PUBLIC_ENROLLMENT_API_URL = ENTERPRISE_ENROLLMENT_API_URL

ENTERPRISE_API_CACHE_TIMEOUT = 60

ENTERPRISE_SUPPORT_URL = "http://foo"

ENTERPRISE_TAGLINE = "High-quality online learning opportunities from the world's best universities"

OAUTH_ID_TOKEN_EXPIRATION = 60*60  # in seconds

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

DEFAULT_FROM_EMAIL = 'course_staff@example.com'

USER_THROTTLE_RATE = '80/minute'
SERVICE_USER_THROTTLE_RATE = '90/minute'
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'URL_FORMAT_OVERRIDE': None,
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'user': USER_THROTTLE_RATE,
        'service_user': SERVICE_USER_THROTTLE_RATE,
    },
    'DATETIME_FORMAT': '%Y-%m-%dT%H:%M:%SZ',
}

# URL for the server that django client listens to by default.
TEST_SERVER = "http://testserver"
ALLOWED_HOSTS = ["testserver.enterprise"]
MEDIA_URL = "/"

ECOMMERCE_SERVICE_WORKER_USERNAME = 'ecommerce_worker'
ENTERPRISE_SERVICE_WORKER_USERNAME = 'enterprise_worker'

ENTERPRISE_CUSTOMER_LOGO_IMAGE_SIZE = 512   # Enterprise logo image size limit in KB's

ENTERPRISE_COURSE_ENROLLMENT_AUDIT_MODES = ['audit', 'honor']

# These are standard regexes for pulling out info like course_ids, usage_ids, etc.
COURSE_KEY_PATTERN = r'(?P<course_key_string>[^/+]+(/|\+)[^/+]+(/|\+)[^/?]+)'
COURSE_ID_PATTERN = COURSE_KEY_PATTERN.replace('course_key_string', 'course_id')

USE_TZ = True

LMS_SEGMENT_KEY = 'SOME_KEY'
