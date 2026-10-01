"""Settings for the fuel route assessment API."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "development-only-change-before-deployment")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
ROOT_URLCONF = "fuelroute.urls"
INSTALLED_APPS = ["django.contrib.staticfiles", "routes"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware"]
TEMPLATES = []
WSGI_APPLICATION = "fuelroute.wsgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cache repeated route requests without another call to the free routing service.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
