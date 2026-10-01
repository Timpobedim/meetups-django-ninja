"""Настройки MeetupBoard. Всё, что зависит от окружения, читается из переменных окружения."""

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, *, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-dev-only-change-me")
DEBUG = env_bool("DEBUG")
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "jwt_ninja",
    "apps.accounts",
    "apps.events",
    "apps.comments",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# DATABASE_URL: postgres://… в Docker/CI; sqlite:///… или in-memory для быстрых тестов и Hurl.
DATABASES = {
    "default": dj_database_url.config(default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}

AUTH_USER_MODEL = "accounts.User"

# Как в референсе: быстрый хешер только для тестов (USE_FAST_HASHER=True).
if env_bool("USE_FAST_HASHER"):
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")

# jwtninja 2.x: отдельный ключ подписи (для HS256 — не короче 32 байт), явные издатель и аудитория.
# Референс писался под jwtninja 1.x (словарь JWT_NINJA), в 2.x эти параметры обязательны.
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-only-jwt-signing-key-change-me-0123456789")
JWT_ISSUER = "meetupboard"
JWT_AUDIENCE = "meetupboard-api"
JWT_ACCESS_TOKEN_EXPIRE_SECONDS = 24 * 60 * 60
# IP-адреса в сессиях не храним: для афиши они не нужны, а это персональные данные.
JWT_PERSIST_CLIENT_IP = False
