"""Django settings for fridge manager."""

from pathlib import Path
import os

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-fridge-manager-secret-key")
DEBUG = os.getenv("DJANGO_DEBUG", "true").strip().lower() in ("1", "true", "yes", "on")
ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",") if host.strip()] or ["*"]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "django_api",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "fridge_service.urls"
WSGI_APPLICATION = "fridge_service.wsgi.application"
ASGI_APPLICATION = "fridge_service.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv("SQLITE_PATH", str(BASE_DIR / "fridge.db")),
    }
}

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = False

STATIC_URL = "/static/"
MEDIA_URL = os.getenv("MEDIA_URL", "/uploads/")
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", str(BASE_DIR / "uploads")))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
}

CORS_ALLOWED_ORIGINS = [
    "https://servicewechat.com",
    "http://localhost:3000",
    "http://localhost:5173",
]
CORS_ALLOW_CREDENTIALS = True