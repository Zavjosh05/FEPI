# Sistema de programas de PROBOSQUE
# Etapas: base (bibliotecas del sistema y de Python) -> produccion (Gunicorn) y pruebas (pytest + Chromium).
# La imagen de producción no lleva Chromium ni las herramientas de prueba.

FROM python:3.12-slim-trixie AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GDAL_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/libgdal.so.36 \
    GEOS_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/libgeos_c.so.1

# GDAL/GEOS/PROJ para GeoDjango; Pango y HarfBuzz para WeasyPrint; fuentes para los acuses.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgdal36 libgeos-c1t64 libproj25 \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---------------------------------------------------------------- producción
FROM base AS produccion
RUN useradd --create-home --uid 1000 probosque \
    && mkdir -p /srv/estaticos /srv/archivos \
    && chown -R probosque /srv
COPY --chown=probosque . /app
USER probosque
EXPOSE 8000
ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]
CMD ["gunicorn", "probosque.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-"]

# ---------------------------------------------------------------- pruebas
FROM base AS pruebas
COPY requirements-pruebas.txt .
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 \
    && pip install -r requirements-pruebas.txt \
    && playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/* /root/.cache/pip
ENV DJANGO_ALLOW_ASYNC_UNSAFE=true
# El código se monta como volumen en docker-compose (sistema/ -> /app).
CMD ["pytest"]
