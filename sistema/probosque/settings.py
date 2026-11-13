"""Configuración del Sistema de programas de PROBOSQUE.

Todo lo que cambia entre equipos se lee de variables de entorno (ver .env.ejemplo).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(nombre, defecto=""):
    return os.environ.get(nombre, defecto)


def _lista(nombre, defecto=""):
    return [v.strip() for v in _env(nombre, defecto).split(",") if v.strip()]


SECRET_KEY = _env("DJANGO_SECRET_KEY", "desarrollo-no-usar-en-produccion")
DEBUG = _env("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = _lista("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = _lista("DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:8080")

if _env("GDAL_LIBRARY_PATH"):
    GDAL_LIBRARY_PATH = _env("GDAL_LIBRARY_PATH")
if _env("GEOS_LIBRARY_PATH"):
    GEOS_LIBRARY_PATH = _env("GEOS_LIBRARY_PATH")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "simple_history",
    "nucleo",
    "recepcion",
    "dictamen",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "probosque.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "plantillas"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "nucleo.contexto.sistema",
            ],
        },
    },
]

WSGI_APPLICATION = "probosque.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": _env("BD_NOMBRE", "probosque"),
        "USER": _env("BD_USUARIO", "probosque"),
        "PASSWORD": _env("BD_CONTRASENA", "probosque-desarrollo"),
        "HOST": _env("BD_SERVIDOR", "localhost"),
        "PORT": _env("BD_PUERTO", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

AUTH_USER_MODEL = "nucleo.Usuario"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
]
LOGIN_URL = "nucleo:entrar"
LOGIN_REDIRECT_URL = "nucleo:bandeja"
LOGOUT_REDIRECT_URL = "nucleo:entrar"

LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "estaticos"]
STATIC_ROOT = _env("ESTATICOS_RAIZ", str(BASE_DIR / "estaticos_recolectados"))

# Archivos del expediente en disco (FileSystemStorage, volumen de Docker). No hay MEDIA_URL
# pública: se descargan por la vista nucleo:archivo, que revisa el permiso.
MEDIA_ROOT = _env("ARCHIVOS_RAIZ", str(BASE_DIR / "archivos_locales"))
MEDIA_URL = "/archivos/"
USAR_X_ACCEL = _env("USAR_X_ACCEL", "0") == "1"
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Carpetas de datos del sistema
REGLAS_DIR = BASE_DIR / "reglas"
DATOS_DIR = BASE_DIR / "datos"

MAPA_TESELAS_URL = _env("MAPA_TESELAS_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")

SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"consola": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["consola"], "level": "INFO"},
    "loggers": {"weasyprint": {"level": "ERROR"}, "fontTools": {"level": "ERROR"}},
}
