#!/usr/bin/env python3
"""
Compara dos carpetas de resultados de `correr`: balance, incendios y ráster de cambio.

Uso (desde la raíz del repositorio):
    python src/comparar_resultados.py resultados/piloto_2023_2024 C:/temp/piloto_bloques

Compara valor por valor, no los archivos byte a byte: las filas del balance por unidad y las de
incendios por clave (columna `incendio` o, en el piloto, `CLAVEINC`), en las columnas que
tengan las dos. Sale con código 0 si todo coincide y 1 si hay diferencias, que muestra.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

COLUMNAS_INCENDIO = ["fecha_inicio", "poligono_ha", "quemado_dnbr_ha", "quemado_en_bosque_ha",
                     "perdido_al_cierre_ha", "dnbr_mediana"]


def _tablas(ruta_a, ruta_b, clave):
    ta, tb = pd.read_csv(ruta_a), pd.read_csv(ruta_b)
    ka = clave if clave in ta.columns else "CLAVEINC"
    kb = clave if clave in tb.columns else "CLAVEINC"
    ta, tb = ta.set_index(ta[ka].astype(str)), tb.set_index(tb[kb].astype(str))
    return ta, tb


def comparar_tabla(ruta_a, ruta_b, clave, columnas=None) -> list[str]:
    ta, tb = _tablas(ruta_a, ruta_b, clave)
    problemas = []
    solo_a, solo_b = sorted(set(ta.index) - set(tb.index)), sorted(set(tb.index) - set(ta.index))
    if solo_a or solo_b:
        problemas.append(f"filas solo en A: {solo_a}; solo en B: {solo_b}")
    if ta.index.duplicated().any() or tb.index.duplicated().any():
        problemas.append("hay claves repetidas")
        return problemas
    comunes = sorted(set(ta.index) & set(tb.index))
    cols = [c for c in (columnas or ta.columns) if c in ta.columns and c in tb.columns and c != clave]
    a, b = ta.loc[comunes, cols], tb.loc[comunes, cols]
    distinto = (a != b) & ~(a.isna() & b.isna())
    for fila, col in zip(*np.nonzero(distinto.to_numpy())):
        problemas.append(f"{comunes[fila]} / {cols[col]}: {a.iat[fila, col]} contra {b.iat[fila, col]}")
    return problemas


def comparar_raster(ruta_a, ruta_b) -> list[str]:
    import rasterio
    with rasterio.open(ruta_a) as sa, rasterio.open(ruta_b) as sb:
        if (sa.shape, sa.transform, sa.crs) != (sb.shape, sb.transform, sb.crs):
            return [f"malla distinta: {sa.shape} {sa.transform} contra {sb.shape} {sb.transform}"]
        a, b = sa.read(1), sb.read(1)
    distinto = a != b
    if not distinto.any():
        return []
    pares = pd.Series(list(zip(a[distinto].tolist(), b[distinto].tolist()))).value_counts().head(10)
    return [f"{int(distinto.sum()):,} píxeles distintos; (A, B) más comunes: "
            + ", ".join(f"{k}: {v:,}" for k, v in pares.items())]


def main():
    p = argparse.ArgumentParser(description="Compara dos carpetas de resultados de correr")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--periodo", default="2023_2024", help="sufijo de los archivos, p. ej. 2023_2024")
    args = p.parse_args()
    a, b = Path(args.a), Path(args.b)

    revisiones = [
        (f"balance_{args.periodo}.csv", lambda x, y: comparar_tabla(x, y, "unidad")),
        ("incendios_dnbr.csv", lambda x, y: comparar_tabla(x, y, "incendio", COLUMNAS_INCENDIO)),
        (f"cambio_{args.periodo}.tif", comparar_raster),
    ]
    todo_igual = True
    for nombre, funcion in revisiones:
        if not (a / nombre).exists() or not (b / nombre).exists():
            print(f"{nombre}: falta en {'A' if not (a / nombre).exists() else 'B'}")
            todo_igual = False
            continue
        problemas = funcion(a / nombre, b / nombre)
        todo_igual &= not problemas
        print(f"{nombre}: {'IDÉNTICO' if not problemas else 'DIFERENTE'}")
        for linea in problemas[:20]:
            print(f"  {linea}")
        if len(problemas) > 20:
            print(f"  ... y {len(problemas) - 20} diferencias más")
    sys.exit(0 if todo_igual else 1)


if __name__ == "__main__":
    main()
