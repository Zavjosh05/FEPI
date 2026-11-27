"""Extrae el diseño de la capa de persistencia a partir de los modelos de Django del Sistema de programas.

Escribe `entregas/diseno/persistencia_datos.json`: cada tabla propia con su app, su docstring, sus columnas (tipo en
PostgreSQL/PostGIS, nulo, llaves, referencias, valor por omisión, opciones y descripción), sus restricciones e índices
y si guarda historial (django-simple-history). No toca la base de datos: solo lee los modelos.

Se corre con la imagen de pruebas, desde `sistema/` (el servicio monta `../entregas` en `/entregas`):

    docker compose --profile pruebas run --rm --no-deps --entrypoint python pruebas /entregas/diseno/extraer_persistencia.py

Con `--nombres` solo imprime `app.Modelo` de cada tabla (sirve para saber qué tablas existen en la rama de cada sprint).
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "probosque.settings")

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402
from django.db import connection, models  # noqa: E402

APPS = ["nucleo", "recepcion", "dictamen", "contrato", "pagos", "portal", "ejecucion", "seguimiento"]
SALIDA = Path(__file__).resolve().parent / "persistencia_datos.json"


def propios():
    return [m for m in apps.get_models()
            if m._meta.app_label in APPS and not m.__name__.startswith("Historical") and not m._meta.proxy]


def por_omision(f):
    if f.default is models.NOT_PROVIDED:
        return None
    if callable(f.default):
        return getattr(f.default, "__name__", "función") + "()"
    valor = f.default
    return valor if isinstance(valor, (int, float, bool, str)) or valor is None else str(valor)


def tipo_bd(f):
    try:
        return f.db_type(connection) or ""
    except Exception:   # noqa: BLE001
        return ""


def columna(m, f):
    dato = {"nombre": f.name, "columna": f.column, "tipo_django": type(f).__name__, "tipo_bd": tipo_bd(f),
            "nulo": f.null, "pk": f.primary_key, "unico": bool(getattr(f, "unique", False)) and not f.primary_key,
            "descripcion": str(f.help_text or ""), "verbose": str(f.verbose_name or "")}
    if isinstance(f, (models.ForeignKey, models.OneToOneField)):
        dato["fk"] = {"tabla": f.related_model._meta.db_table, "modelo": f.related_model.__name__,
                      "al_borrar": f.remote_field.on_delete.__name__, "uno_a_uno": isinstance(f, models.OneToOneField)}
        dato["tipo_bd"] = tipo_bd(f.target_field) or "integer"
    if getattr(f, "max_length", None) and not isinstance(f, (models.ForeignKey, models.OneToOneField)):
        dato["max"] = f.max_length
    d = por_omision(f)
    if d is not None:
        dato["omision"] = d
    if f.choices:
        dato["opciones"] = [str(v) for v, _ in f.flatchoices]
    if getattr(f, "srid", None):
        dato["srid"] = f.srid
    if getattr(f, "db_index", False) and not f.primary_key and not dato["unico"]:
        dato["indice"] = True
    return dato


def tabla(m):
    meta = m._meta
    columnas, muchos = [], []
    for f in meta.get_fields():
        if f.auto_created and not f.concrete:
            continue
        if isinstance(f, models.ManyToManyField):
            muchos.append({"nombre": f.name, "modelo": f.related_model.__name__, "tabla": f.related_model._meta.db_table,
                           "tabla_intermedia": f.remote_field.through._meta.db_table})
            continue
        if f.concrete:
            columnas.append(columna(m, f))
    restricciones = [{"tipo": "único", "campos": list(u)} for u in meta.unique_together]
    for c in meta.constraints:
        r = {"tipo": type(c).__name__.replace("Constraint", "").lower() or "restricción", "nombre": c.name}
        if getattr(c, "fields", None):
            r["campos"] = list(c.fields)
        if getattr(c, "condition", None) is not None:
            r["condicion"] = str(c.condition)
        if getattr(c, "check", None) is not None:
            r["condicion"] = str(c.check)
        restricciones.append(r)
    doc = (m.__doc__ or "").strip()
    if doc.startswith(m.__name__ + "("):      # docstring automático de Django
        doc = ""
    return {"app": meta.app_label, "modelo": m.__name__, "tabla": meta.db_table, "verbose": str(meta.verbose_name),
            "verbose_plural": str(meta.verbose_name_plural), "doc": " ".join(doc.split()),
            "orden": [str(o) for o in (meta.ordering or [])], "columnas": columnas, "muchos_a_muchos": muchos,
            "restricciones": restricciones, "indices": [list(i.fields) for i in meta.indexes],
            "historial": hasattr(m, "history"),
            "tabla_historial": f"{meta.app_label}_historical{m.__name__.lower()}" if hasattr(m, "history") else None}


def main():
    modelos = sorted(propios(), key=lambda m: (APPS.index(m._meta.app_label), m.__name__))
    if "--nombres" in sys.argv:
        print("\n".join(f"{m._meta.app_label}.{m.__name__}" for m in modelos))
        return
    datos = {"motor": connection.vendor, "tablas": [tabla(m) for m in modelos]}
    SALIDA.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{SALIDA}: {len(datos['tablas'])} tablas")


if __name__ == "__main__":
    main()
