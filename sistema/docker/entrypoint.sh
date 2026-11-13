#!/bin/sh
# Arranque del contenedor web: si PREPARAR_SITIO=1 aplica migraciones, recolecta estáticos,
# carga catálogos y reglas y (si CARGAR_DEMO=1) los datos de demostración. Todo es idempotente.
set -e

if [ "${PREPARAR_SITIO:-0}" = "1" ]; then
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput --verbosity 0
    python manage.py cargar_catalogos
    python manage.py cargar_reglas
    if [ "${CARGAR_DEMO:-0}" = "1" ]; then
        python manage.py cargar_demo
    fi
fi

exec "$@"
