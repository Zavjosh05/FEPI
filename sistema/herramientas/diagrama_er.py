"""Genera el diagrama entidad-relación del sistema a partir de los modelos de Django.

Escribe Mermaid (erDiagram) en la salida estándar. No toca la base de datos: solo lee los modelos.

    docker compose --profile pruebas run --rm --no-deps --entrypoint python pruebas \
        herramientas/diagrama_er.py > docs/modelo_datos.mmd

Opciones: --resumen (llaves y campos principales), --max-campos N, --entidades A B C (un diagrama
por área) y --apps nucleo recepcion dictamen.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "probosque.settings")

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402
from django.db import models  # noqa: E402

TIPOS = {
    "AutoField": "int", "BigAutoField": "int", "CharField": "texto", "TextField": "texto", "SlugField": "texto",
    "EmailField": "texto", "BooleanField": "bool", "DateField": "fecha", "DateTimeField": "fecha_hora",
    "DecimalField": "decimal", "IntegerField": "int", "PositiveIntegerField": "int",
    "PositiveSmallIntegerField": "int", "SmallIntegerField": "int", "FloatField": "decimal",
    "JSONField": "json", "FileField": "archivo", "ImageField": "archivo",
    "MultiPolygonField": "geom_multipoligono", "PolygonField": "geom_poligono", "GeometryField": "geom",
    "PointField": "geom_punto",
}
# Campos de auditoría que se repiten en casi todos los modelos: se omiten en el resumen.
SECUNDARIOS = {"password", "last_login", "is_superuser", "is_staff", "is_active", "date_joined", "first_name",
               "last_name", "email"}


def es_propio(modelo, etiquetas):
    return modelo._meta.app_label in etiquetas and not modelo.__name__.startswith("Historical")


def nombre(modelo):
    return modelo.__name__


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apps", nargs="+", default=["nucleo", "recepcion", "dictamen"])
    p.add_argument("--resumen", action="store_true", help="Solo la llave, las llaves foráneas y hasta 6 campos más.")
    p.add_argument("--entidades", nargs="+", help="Dibuja solo estas entidades (para un diagrama por área).")
    p.add_argument("--max-campos", type=int, default=6, help="Campos que no son llave en el resumen.")
    p.add_argument("--con-usuario", action="store_true",
                   help="Dibuja también las relaciones hacia Usuario (quién registró cada cosa).")
    a = p.parse_args()

    propios = [m for m in apps.get_models() if es_propio(m, a.apps)]
    if a.entidades:
        propios = [m for m in propios if nombre(m) in a.entidades]
    nombres = {nombre(m) for m in propios}
    entidades, relaciones = [], []
    for m in propios:
        filas = []
        otros = 0
        for f in m._meta.get_fields():
            if f.auto_created and not f.concrete:
                continue                                # relaciones inversas
            if isinstance(f, models.ManyToManyField):
                destino = nombre(f.related_model)
                if destino in nombres:
                    relaciones.append(f"  {nombre(m)} }}o--o{{ {destino} : {f.name}")
                continue
            if isinstance(f, (models.ForeignKey, models.OneToOneField)):
                destino = nombre(f.related_model)
                if not a.resumen or destino in nombres:
                    filas.append(f"    int {f.name}_id FK")
                if destino not in nombres or (destino == "Usuario" and nombre(m) != "Usuario" and not a.con_usuario):
                    continue
                if isinstance(f, models.OneToOneField):
                    card = "||--o|"
                else:
                    card = "|o--o{" if f.null else "||--o{"
                relaciones.append(f"  {destino} {card} {nombre(m)} : {f.name}")
                continue
            if f.name in SECUNDARIOS:
                continue
            tipo = TIPOS.get(type(f).__name__, type(f).__name__.replace("Field", "").lower())
            marca = " PK" if f.primary_key else (" UK" if getattr(f, "unique", False) else "")
            if a.resumen and not marca:
                otros += 1
                if otros > a.max_campos:
                    continue
            filas.append(f"    {tipo} {f.name}{marca}")
        entidades.append((m._meta.app_label, nombre(m), filas))

    print("erDiagram")
    for linea in sorted(set(relaciones)):
        print(linea)
    for _, ent, filas in sorted(entidades):
        print(f"  {ent} {{")
        print("\n".join(filas))
        print("  }")


if __name__ == "__main__":
    main()
