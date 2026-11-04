#!/usr/bin/env python3
"""
Prototipo de la Calculadora de masa forestal - PROBOSQUE
=========================================================

Masa forestal = superficie con cobertura arbórea (hectáreas).

Balance por unidad (predio, municipio o Delegación):

    bosque_actual = bosque_base - perdida_por_incendio - otras_perdidas + ganancia

Todo se mide con Sentinel-2 L2A (10 m), que se lee sin cuenta ni costo desde el
catálogo Earth Search (AWS Open Data). Aparte se reporta la recuperación
ESPERADA según los polígonos de reforestación de los programas (superficie x
sobrevivencia), para compararla con la que el satélite OBSERVA.

Instalación (Python 3.10 o superior):
    pip install -r requirements.txt

Uso:
    # 1. Probar la lógica con datos inventados (no descarga nada)
    python prototipo_masa_forestal.py demo

    # 2. Calibrar el umbral de NDVI con puntos de campo o fotointerpretados
    python prototipo_masa_forestal.py calibrar --aoi zona_piloto.geojson \
        --anio 2023 --puntos puntos_validacion.csv

    # 3. Correr el cálculo
    python prototipo_masa_forestal.py correr --aoi zona_piloto.geojson \
        --anio-base 2023 --anio 2025 --umbral-ndvi 0.55 \
        --incendios incendios_conafor.shp --campo-fecha FECHAINIC \
        --reforestacion poligonos_programas.shp --campo-anio ANIO --campo-sobrev SOBREV \
        --unidades municipios.shp --campo-unidad NOMGEO \
        --salida resultados

    # 4. Zonas grandes (todo el estado): lo mismo con --bloques
    python prototipo_masa_forestal.py correr --aoi estado_mexico.gpkg ... --bloques \
        --salida resultados/edomex

Archivos de entrada:
    --aoi            Polígono de la zona piloto (GeoJSON, SHP o GPKG, cualquier CRS).
    --puntos         CSV con columnas lon, lat, clase (clase = 1 bosque, 0 no bosque).
    --incendios      Polígonos de incendio con su fecha de inicio (p. ej. el
                     Concentrado Nacional de Polígonos de Incendios de CONAFOR).
    --reforestacion  Polígonos de PS, RHF y CC con año de plantación y, si existe,
                     sobrevivencia verificada (fracción 0-1 o porcentaje 0-100).
    --unidades       Polígonos donde se resume el balance (predios, municipios...).

Convenciones:
    - La cobertura de un año se mide con el compuesto de noviembre-diciembre de
      ese año: ya pasaron las lluvias, hay pocas nubes, la parcela agrícola está
      seca (buen contraste con el bosque) y todavía no empieza la temporada de
      incendios.
    - Un píxel cuenta como quemado si su dNBR >= 0.27 (severidad moderada-baja o
      mayor según los rangos del USGS). Se puede cambiar con --umbral-dnbr.
    - Con --bloques la zona se divide en bloques de 20.48 km que se leen, calculan y
      liberan uno por uno. Cada bloque se alinea a la malla interna de los COG de su
      tesela Sentinel-2, para no leer dos veces los mismos datos. El resultado es
      idéntico al de procesar todo de una vez (el modo demo lo comprueba).
    - Con --zona-forestal, el balance se desglosa además por clave de la Serie VII
      (CF-DEV-03) y por tipo de bosque (CF-DEV-04), y cada píxel de "otra pérdida" se
      clasifica según el uso al que pasó: agrícola, pecuario, urbano u otro (CF-DEV-07,
      opción A: clasificador entrenado con el compuesto del año actual y las zonas no
      forestales de la Serie VII).
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import math
import os
import re
import shutil
import warnings
import sys
import time
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Parámetros generales
# --------------------------------------------------------------------------
STAC_URL = "https://earth-search.aws.element84.com/v1"
COLECCIONES = ["sentinel-2-c1-l2a", "sentinel-2-l2a"]  # se usa la primera que tenga datos
CRS = "EPSG:32614"           # UTM 14N, cubre todo el Estado de México
RES = 10                     # metros por píxel
HA_PIXEL = RES * RES / 10_000
SCL_VALIDOS = [4, 5, 6, 7, 11]  # vegetación, suelo, agua, sin clasificar, nieve
BANDAS = {"ndvi": ("nir", "red"), "nbr": ("nir08", "swir22")}  # B8/B4 y B8A/B12
UMBRAL_DNBR = 0.27
VENTANA_COBERTURA = ("11-01", "12-31")
NUBES_MAX = 60               # % máximo de nubes por escena (eo:cloud_cover); --nubes-max
BLOQUE_COG = 1024            # bloque interno de los COG: 1024 px de 10 m = 512 px de 20 m = 10.24 km
LADO_TESELA = 100_000        # las teselas Sentinel-2 (MGRS) arrancan cada 100 km
HILOS_INCENDIOS = 6          # incendios que se calculan a la vez (--hilos-incendios)
CACHE_RAM_MB = 512           # caché de GDAL en memoria para las lecturas de los COG

# Códigos del ráster de cambio
SIN_BOSQUE, ESTABLE, PERD_INCENDIO, PERD_OTRA, GANANCIA = 0, 1, 2, 3, 4

COLUMNAS_BALANCE = ["bosque_base_ha", "perdida_incendio_ha", "otras_perdidas_ha", "ganancia_ha",
                    "ganancia_en_reforestacion_ha", "bosque_afectado_por_fuego_ha", "bosque_actual_ha"]

# Zona forestal: claves de la Serie VII que cuentan (bosques, selva baja caducifolia, matorrales y
# vegetación secundaria arbórea). Antes del 3-nov-2026 era ^(B|VSA/).
CLASES_FORESTALES = r"^(B|S|M|VSA/)"
CAMPO_DESCRIPCION = "DESCRIPCIO"

# Desglose por clave de la Serie VII (CF-DEV-03) y por tipo de bosque (CF-DEV-04)
COLUMNAS_VEG = ["zona_forestal_ha", "bosque_base_ha", "perdida_incendio_ha", "otras_perdidas_ha",
                "ganancia_ha", "bosque_actual_ha"]
SIN_CLAVE = "(reforestación fuera de la zona forestal)"
TIPOS_BOSQUE = [  # (tipo, claves de la Serie VII); lo que no encaja va a "Otro" (p. ej. BC, bosque cultivado)
    ("Coníferas", r"^(VSA/)?(BA|BP|BPQ|BJ|BB|BG)$"),
    ("Encino", r"^(VSA/)?(BQ|BQP)$"),
    ("Mesófilo de montaña", r"^(VSA/)?BM$"),
    ("Selva baja caducifolia", r"^(VSA/)?SBC$"),
    ("Vegetación de zonas semiáridas", r"^(MC|MDR)$"),
]
TIPO_OTRO = "Otro"
TIPOS_ORDEN = [t for t, _ in TIPOS_BOSQUE] + [TIPO_OTRO]

# Uso al que pasó el terreno en las "otras pérdidas" (CF-DEV-07, opción A). Códigos del ráster
# destino: 0 no aplica, 1 agrícola, 2 pecuario, 3 urbano, 4 otro, 5 sin dato.
DESTINOS = ["agricola", "pecuario", "urbano", "otro", "sin_dato"]
SIN_DATO_DESTINO = 5
CLASES_AGRICOLA = r"^(T|R|HA$)"   # temporal (TA, TAP...), riego (RA, RAS...) y humedad (HA)
CLASES_PECUARIO = r"^(PI|PC)$"    # pastizal inducido y cultivado
CLASES_URBANO = r"^AH$"           # asentamientos humanos
# Lo demás fuera de la zona forestal entrena "otro": vegetación secundaria arbustiva y herbácea,
# pastizal halófilo, pradera de alta montaña, agua, sin vegetación, tular, etc.
BANDAS_RASGOS = ["green", "red", "nir", "nir08", "swir16", "swir22"]  # B03 B04 B08 B8A B11 B12
RASGOS = BANDAS_RASGOS + ["ndvi", "nbr", "ndbi", "mndwi"]
PASO_MUESTRA = 25            # una muestra de entrenamiento cada 25 px (250 m) de la malla total
MUESTRAS_MAX = 1500          # máximo por clase y región (entrenamiento + prueba)
REGION_M = 100_000           # regiones de 100 km (la malla de las teselas Sentinel-2)
CELDA_PRUEBA_M = 5_000       # las muestras de 1 de cada 5 celdas de 5 km se reservan para prueba


# ==========================================================================
# 1. Núcleo del cálculo (solo numpy; se prueba con el modo demo)
# ==========================================================================
def mascara_bosque(ndvi: np.ndarray, umbral: float) -> np.ndarray:
    """Bosque = NDVI >= umbral. Los píxeles sin dato (NaN) quedan como no bosque."""
    return np.nan_to_num(ndvi, nan=-1.0) >= umbral


def mascaras_con_margen(ndvi_base, ndvi_act, umbral, margen, zona):
    """Bosque base y actual exigiendo un cambio mínimo de NDVI.

    Un píxel solo pasa de bosque a no bosque (o al revés) si además de cruzar el
    umbral su NDVI cambió al menos `margen`. Así los píxeles que oscilan alrededor
    del umbral por diferencias de fecha o de fenología no se cuentan como cambio.
    `zona` limita el cálculo (área de interés x zona forestal de referencia).
    """
    base = mascara_bosque(ndvi_base, umbral) & zona
    candidato = mascara_bosque(ndvi_act, umbral) & zona
    with np.errstate(invalid="ignore"):
        delta = ndvi_act - ndvi_base
        perdida = base & ~candidato & (delta <= -margen)
        ganancia = ~base & candidato & (delta >= margen)
    actual = (base & ~perdida) | ganancia
    return base, actual


def mapa_cambio(base: np.ndarray, actual: np.ndarray, quemado: np.ndarray) -> np.ndarray:
    cambio = np.full(base.shape, SIN_BOSQUE, dtype=np.uint8)
    cambio[base & actual] = ESTABLE
    perdida = base & ~actual
    cambio[perdida & quemado] = PERD_INCENDIO
    cambio[perdida & ~quemado] = PERD_OTRA
    cambio[~base & actual] = GANANCIA
    return cambio


def balance(base, actual, quemado, en_reforestacion, unidades, nombres) -> pd.DataFrame:
    """Balance en hectáreas por unidad, sobre arreglos completos.

    unidades: ráster entero (0 = fuera de cualquier unidad, 1..n = índice en nombres).
    `correr` usa conteos_unidades + balance_de_conteos, que se pueden sumar por bloques;
    esta versión queda como referencia para comprobarlas en el modo demo.
    """
    cambio = mapa_cambio(base, actual, quemado)
    filas = []
    for i, nombre in enumerate(nombres, start=1):
        u = unidades == i
        if not u.any():
            continue

        def ha(m):
            return round(float((m & u).sum()) * HA_PIXEL, 2)

        fila = {
            "unidad": nombre,
            "bosque_base_ha": ha(base),
            "perdida_incendio_ha": ha(cambio == PERD_INCENDIO),
            "otras_perdidas_ha": ha(cambio == PERD_OTRA),
            "ganancia_ha": ha(cambio == GANANCIA),
            "ganancia_en_reforestacion_ha": ha((cambio == GANANCIA) & en_reforestacion),
            "bosque_afectado_por_fuego_ha": ha(base & quemado),
            "bosque_actual_ha": ha(actual),
        }
        fila["cambio_neto_ha"] = round(fila["bosque_actual_ha"] - fila["bosque_base_ha"], 2)
        filas.append(fila)
    return pd.DataFrame(filas)


def conteos_unidades(cambio, base, actual, quemado, en_reforestacion, unidades, n) -> np.ndarray:
    """Píxeles de cada término del balance por unidad, para sumarlos bloque por bloque.

    Fila i = unidad i (0 = fuera de toda unidad). Columna 0 = píxeles de la unidad; las
    demás siguen el orden de COLUMNAS_BALANCE.
    """
    u = unidades.ravel()

    def cuenta(m):
        return np.bincount(u[m.ravel()], minlength=n + 1)

    return np.stack([np.bincount(u, minlength=n + 1), cuenta(base), cuenta(cambio == PERD_INCENDIO),
                     cuenta(cambio == PERD_OTRA), cuenta(cambio == GANANCIA),
                     cuenta((cambio == GANANCIA) & en_reforestacion), cuenta(base & quemado),
                     cuenta(actual)], axis=1).astype(np.int64)


def balance_de_conteos(conteos: np.ndarray, nombres) -> pd.DataFrame:
    """Mismo resultado que balance(), a partir de los conteos sumados de todos los bloques."""
    filas = []
    for i, nombre in enumerate(nombres, start=1):
        if conteos[i, 0] == 0:
            continue
        fila = {"unidad": nombre}
        fila.update({col: round(float(px) * HA_PIXEL, 2) for col, px in zip(COLUMNAS_BALANCE, conteos[i, 1:])})
        fila["cambio_neto_ha"] = round(fila["bosque_actual_ha"] - fila["bosque_base_ha"], 2)
        filas.append(fila)
    return pd.DataFrame(filas)


# --- Desglose por clave de la Serie VII y por tipo de bosque (CF-DEV-03 y 04) ---------------
def tipo_bosque(clave) -> str:
    """Tipo de bosque de una clave de la Serie VII (ver TIPOS_BOSQUE); None o sin tipo = Otro."""
    for tipo, patron in TIPOS_BOSQUE:
        if clave and re.match(patron, clave):
            return tipo
    return TIPO_OTRO


def conteos_vegetacion(cambio, base, actual, zona, unidades, claves_r, n, k) -> np.ndarray:
    """Píxeles de la zona por unidad y clave, para sumarlos bloque por bloque.

    claves_r: ráster con el número de clave (1..k; 0 = reforestación fuera de la zona forestal).
    Fila u * (k + 1) + clave. Columnas: zona, base, pérdida por incendio, otra pérdida,
    ganancia, actual (el orden de COLUMNAS_VEG).
    """
    idx = (unidades.astype(np.int64) * (k + 1) + claves_r)[zona]
    cz = cambio[zona]
    m = (n + 1) * (k + 1)
    columnas = [np.ones(idx.size, bool), base[zona], cz == PERD_INCENDIO, cz == PERD_OTRA,
                cz == GANANCIA, actual[zona]]
    return np.stack([np.bincount(idx[c], minlength=m) for c in columnas], axis=1).astype(np.int64)


def _fila_ha(px, columnas):
    fila = {col: round(float(v) * HA_PIXEL, 2) for col, v in zip(columnas, px)}
    fila["cambio_neto_ha"] = round(fila["bosque_actual_ha"] - fila["bosque_base_ha"], 2)
    return fila


def tablas_vegetacion(conteos, nombres, claves, descripciones=None):
    """(por clave, por tipo de bosque) en hectáreas, a partir de los conteos sumados de todos los
    bloques. El tipo se suma en píxeles antes de pasar a hectáreas, así que cuadra con el balance."""
    k = len(claves)
    etiquetas = [None] + list(claves)
    descripciones = descripciones or {}
    filas, por_tipo = [], defaultdict(lambda: np.zeros(conteos.shape[1], dtype=np.int64))
    for idx in np.flatnonzero(conteos[:, 0]):
        u, kk = divmod(int(idx), k + 1)
        if u == 0:  # fuera de toda unidad
            continue
        clave = etiquetas[kk]
        tipo = tipo_bosque(clave)
        filas.append({"unidad": nombres[u - 1], "clave": clave or SIN_CLAVE,
                      "descripcion": descripciones.get(clave, ""), "tipo_bosque": tipo,
                      **_fila_ha(conteos[idx], COLUMNAS_VEG)})
        por_tipo[(u, TIPOS_ORDEN.index(tipo))] += conteos[idx]
    tipos = [{"unidad": nombres[u - 1], "tipo_bosque": TIPOS_ORDEN[t], **_fila_ha(px, COLUMNAS_VEG)}
             for (u, t), px in sorted(por_tipo.items())]
    cols_veg = ["unidad", "clave", "descripcion", "tipo_bosque", *COLUMNAS_VEG, "cambio_neto_ha"]
    cols_tipo = ["unidad", "tipo_bosque", *COLUMNAS_VEG, "cambio_neto_ha"]
    return pd.DataFrame(filas, columns=cols_veg), pd.DataFrame(tipos, columns=cols_tipo)


# --- Uso al que pasó el terreno en las otras pérdidas (CF-DEV-07, opción A) ------------------
def clase_destino(clave, agricola=CLASES_AGRICOLA, pecuario=CLASES_PECUARIO, urbano=CLASES_URBANO) -> int:
    """Etiqueta de entrenamiento de una clave no forestal de la Serie VII: 1 agrícola, 2 pecuario,
    3 urbano, 4 otro."""
    for codigo, patron in enumerate((agricola, pecuario, urbano), start=1):
        if re.search(patron, str(clave)):
            return codigo
    return 4


@dataclass(frozen=True)
class Muestreo:
    """Cómo se toman las muestras de entrenamiento del clasificador de destino."""
    paso: int = PASO_MUESTRA              # una muestra cada `paso` píxeles de la malla total
    max_por_grupo: int = MUESTRAS_MAX     # por clase y región
    region_m: float = REGION_M
    celda_prueba_m: float = CELDA_PRUEBA_M
    arboles: int = 200


def puntos_muestra(b, dentro, zona, etiquetas, paso):
    """Píxeles del bloque en la retícula de muestreo (filas y columnas de la malla total que caen
    en paso // 2 + k * paso), dentro de la zona de interés, fuera de la zona forestal y con
    etiqueta. Como la retícula es de la malla total, da los mismos puntos con o sin bloques.
    Regresa filas y columnas locales del bloque y la etiqueta."""
    off = paso // 2
    rr = np.arange(b.r0 + (off - b.r0) % paso, b.r1, paso) - b.r0
    cc = np.arange(b.c0 + (off - b.c0) % paso, b.c1, paso) - b.c0
    f, c = (x.ravel() for x in np.meshgrid(rr, cc, indexing="ij"))
    ok = dentro[f, c] & ~zona[f, c] & (etiquetas[f, c] > 0)
    return f[ok], c[ok], etiquetas[f, c][ok]


def entrenar_destino(filas, cols, clases, X, transform, muestreo=Muestreo()):
    """Bosque aleatorio que separa agrícola, pecuario, urbano y otro con los rasgos Sentinel-2.

    filas, cols: posición de cada muestra en la malla total; clases 1..4 (de la Serie VII).
    - Las muestras se ordenan por posición, así que da lo mismo de qué bloques vengan.
    - Se balancean: como máximo muestreo.max_por_grupo por clase y región de 100 km (elegidas al
      azar con semilla fija), para que ninguna clase ni región domine.
    - Las de 1 de cada 5 celdas de 5 km se reservan para medir la exactitud (prueba espacial: las
      muestras vecinas se parecen y medirían de más).
    Regresa (modelo o None si no hay al menos dos clases, tabla de exactitud, resumen).
    """
    from sklearn.ensemble import RandomForestClassifier

    orden = np.lexsort((cols, filas))
    filas, cols, clases, X = filas[orden], cols[orden], clases[orden].astype(np.int64), X[orden]
    ok = np.isfinite(X).all(axis=1)
    filas, cols, clases, X = filas[ok], cols[ok], clases[ok], X[ok]
    x = transform.c + (cols + 0.5) * transform.a
    y = transform.f + (filas + 0.5) * transform.e
    region = np.unique(np.stack([np.floor(x / muestreo.region_m), np.floor(y / muestreo.region_m)], 1),
                       axis=0, return_inverse=True)[1].ravel() if len(x) else np.zeros(0, int)
    grupo = region.astype(np.int64) * 8 + clases
    azar = np.random.default_rng(0).permutation(len(grupo))
    en_orden = np.argsort(grupo[azar], kind="stable")  # grupos juntos, en el orden al azar
    g = grupo[azar][en_orden]
    inicio = np.r_[0, np.flatnonzero(np.diff(g)) + 1] if len(g) else np.zeros(0, int)
    rango = np.arange(len(g)) - np.repeat(inicio, np.diff(np.r_[inicio, len(g)]))
    elegidos = np.sort(azar[en_orden[rango < muestreo.max_por_grupo]])
    clases, X, x, y = clases[elegidos], X[elegidos], x[elegidos], y[elegidos]
    cx = np.floor(x / muestreo.celda_prueba_m).astype(np.int64)
    cy = np.floor(y / muestreo.celda_prueba_m).astype(np.int64)
    prueba = ((cx * 73_856_093) ^ (cy * 19_349_663)) % 5 == 0

    resumen = {"muestras_disponibles": int(ok.sum()), "muestras_entrenamiento": int((~prueba).sum()),
               "muestras_prueba": int(prueba.sum()), "regiones": int(region.max() + 1) if len(region) else 0,
               "rasgos": RASGOS}
    nombres = DESTINOS[:4]
    filas_tabla = [{"clase": nombres[k - 1], "entrenamiento": int(((clases == k) & ~prueba).sum()),
                    "prueba": int(((clases == k) & prueba).sum())} for k in range(1, 5)]
    if len(np.unique(clases[~prueba])) < 2:
        return None, pd.DataFrame(filas_tabla), resumen
    modelo = RandomForestClassifier(n_estimators=muestreo.arboles, min_samples_leaf=2,
                                    class_weight="balanced", random_state=0, n_jobs=-1)
    modelo.fit(X[~prueba], clases[~prueba])
    modelo.n_jobs = 1  # al predecir, un hilo: la suma de los árboles va siempre en el mismo orden
    resumen["importancia_rasgos"] = {r: round(float(v), 3) for r, v in zip(RASGOS, modelo.feature_importances_)}
    if prueba.any():
        cm = np.zeros((4, 4), dtype=np.int64)
        np.add.at(cm, (clases[prueba] - 1, modelo.predict(X[prueba]).astype(int) - 1), 1)
        total, diag = cm.sum(), np.diag(cm)
        with np.errstate(divide="ignore", invalid="ignore"):
            productor, usuario = diag / cm.sum(1), diag / cm.sum(0)
        pe = (cm.sum(0) * cm.sum(1)).sum() / total**2
        resumen["exactitud_global"] = round(float(diag.sum() / total), 4)
        resumen["kappa"] = round(float((diag.sum() / total - pe) / (1 - pe)), 4) if pe < 1 else None
        for k, fila in enumerate(filas_tabla):
            fila["exactitud_productor"] = None if np.isnan(productor[k]) else round(float(productor[k]), 4)
            fila["exactitud_usuario"] = None if np.isnan(usuario[k]) else round(float(usuario[k]), 4)
            fila.update({f"pred_{nombres[j]}": int(cm[k, j]) for j in range(4)})
        filas_tabla.append({"clase": "global", "entrenamiento": resumen["muestras_entrenamiento"],
                            "prueba": resumen["muestras_prueba"],
                            "exactitud_global": resumen["exactitud_global"], "kappa": resumen["kappa"]})
    tabla = pd.DataFrame(filas_tabla)
    for col in tabla.columns:
        if col == "entrenamiento" or col == "prueba" or col.startswith("pred_"):
            tabla[col] = tabla[col].astype("Int64")  # enteros con huecos en la fila "global"
    return modelo, tabla, resumen


def predecir_destino(modelo, X) -> np.ndarray:
    """Clase de destino (1-4) de cada fila de rasgos; SIN_DATO_DESTINO si falta algún rasgo o no
    hay modelo."""
    out = np.full(len(X), SIN_DATO_DESTINO, dtype=np.uint8)
    ok = np.isfinite(X).all(axis=1) if len(X) else np.zeros(0, bool)
    if modelo is not None and ok.any():
        out[ok] = modelo.predict(X[ok]).astype(np.uint8)
    return out


def tabla_destino(conteos, nombres, presentes) -> pd.DataFrame:
    """Hectáreas de otras pérdidas por unidad y destino. conteos: (n + 1) x 6 píxeles por código
    0..5 del ráster destino; presentes: unidades que lleva el balance."""
    filas = []
    for i, nombre in enumerate(nombres, start=1):
        if not presentes[i]:
            continue
        fila = {"unidad": nombre, "otras_perdidas_ha": round(float(conteos[i, 1:].sum()) * HA_PIXEL, 2)}
        fila.update({f"{d}_ha": round(float(conteos[i, k]) * HA_PIXEL, 2) for k, d in enumerate(DESTINOS, 1)})
        filas.append(fila)
    return pd.DataFrame(filas, columns=["unidad", "otras_perdidas_ha", *[f"{d}_ha" for d in DESTINOS]])


def ganancia_por_programa(*_):
    """CF-DEV-05, pendiente: ganancia observada por programa (PS, RHF, CC).

    Punto de conexión. Faltan los polígonos de PROBOSQUE con su programa. Cuando lleguen: pasarlos
    con --reforestacion y un campo de programa, rasterizarlos por bloque con su número de programa
    (como CapasVector.unidades) y contar aquí cambio == GANANCIA por unidad y programa, igual que
    conteos_vegetacion, para sumarlo bloque por bloque. Hoy la ganancia dentro de los polígonos
    solo se cuenta en conjunto (ganancia_en_reforestacion_ha del balance).
    """
    raise NotImplementedError("CF-DEV-05: faltan los polígonos de reforestación de PROBOSQUE")


def histograma_ndvi(valores, bins: int = 200):
    """Histograma de NDVI para Otsu, de -0.2 a 1 (sin incluirlos).

    `valores` es un arreglo o una lista de pedazos (uno por bloque). Con pedazos, el
    histograma va del mínimo al máximo de todos y se suma pedazo por pedazo: queda
    idéntico al de juntar todos los valores, sin copiarlos (el modo demo lo comprueba).
    """
    if isinstance(valores, np.ndarray):
        v = valores[np.isfinite(valores)]
        v = v[(v > -0.2) & (v < 1)]
        return np.histogram(v, bins=bins)
    piezas = [v[np.isfinite(v)] for v in valores]
    piezas = [v[(v > -0.2) & (v < 1)] for v in piezas]
    piezas = [v for v in piezas if v.size]
    if not piezas:
        return histograma_ndvi(np.array([], dtype="float32"), bins)
    rango = (min(v.min() for v in piezas), max(v.max() for v in piezas))
    hist = 0
    for v in piezas:
        h, bordes = np.histogram(v, bins=bins, range=rango)
        hist = hist + h
    return hist, bordes


def umbral_otsu(valores, bins: int = 200) -> float:
    """Umbral de Otsu: separa los dos picos del histograma de NDVI (bosque / no bosque).
    Sirve como valor provisional mientras no haya puntos de referencia para calibrar.
    `valores`: arreglo o lista de pedazos, como en histograma_ndvi."""
    hist, bordes = histograma_ndvi(valores, bins)
    centros = (bordes[:-1] + bordes[1:]) / 2
    p = hist / hist.sum()
    w0 = np.cumsum(p)
    m0 = np.cumsum(p * centros)
    mt = m0[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        var_entre = (mt * w0 - m0) ** 2 / (w0 * (1 - w0))
    return float(np.round(centros[np.nanargmax(var_entre)], 2))


def leer_fechas(serie: pd.Series) -> pd.Series:
    """Acepta AAAA-MM-DD y, si no, DD/MM/AAAA."""
    f = pd.to_datetime(serie, errors="coerce", format="ISO8601")
    faltan = f.isna()
    if faltan.any():
        f[faltan] = pd.to_datetime(serie[faltan], errors="coerce", dayfirst=True)
    return f


def calibrar_umbral(valores: np.ndarray, clases: np.ndarray) -> tuple[float, pd.DataFrame]:
    """Busca el umbral de NDVI con mejor exactitud balanceada contra puntos de referencia."""
    ok = ~np.isnan(valores)
    v, c = valores[ok], clases[ok].astype(bool)
    if c.all() or (~c).all():
        raise ValueError("Se necesitan puntos de ambas clases (bosque y no bosque).")
    filas = []
    for u in np.round(np.arange(0.20, 0.91, 0.01), 2):
        pred = v >= u
        sens = (pred & c).sum() / c.sum()          # bosque bien detectado
        espec = (~pred & ~c).sum() / (~c).sum()    # no bosque bien detectado
        filas.append({"umbral": u, "exactitud_global": (pred == c).mean(),
                      "sensibilidad": sens, "especificidad": espec,
                      "exactitud_balanceada": (sens + espec) / 2})
    tabla = pd.DataFrame(filas)
    mejor = tabla.loc[tabla["exactitud_balanceada"].idxmax()]
    return float(mejor["umbral"]), tabla


def recuperacion_esperada(refo_gdf, unidades_gdf, campo_unidad, campo_anio, campo_sobrev,
                          anio_base, anio, sobrev_default) -> pd.DataFrame:
    """Superficie plantada x sobrevivencia, para plantaciones del periodo (anio_base, anio]."""
    import geopandas as gpd

    r = refo_gdf.to_crs(CRS).copy()
    anios = pd.to_numeric(r[campo_anio], errors="coerce")
    r = r[(anios > anio_base) & (anios <= anio)]
    if r.empty:
        return pd.DataFrame(columns=["unidad", "plantado_periodo_ha", "recuperacion_esperada_ha"])
    if campo_sobrev and campo_sobrev in r.columns:
        s = pd.to_numeric(r[campo_sobrev], errors="coerce")
        s = s.where(s <= 1, s / 100)  # admite porcentaje
        r["sobrev"] = s.fillna(sobrev_default)
    else:
        r["sobrev"] = sobrev_default
    u = unidades_gdf.to_crs(CRS)[[campo_unidad, "geometry"]]
    inter = gpd.overlay(r[["sobrev", "geometry"]], u, how="intersection")
    inter["plantado_periodo_ha"] = inter.geometry.area / 10_000
    inter["recuperacion_esperada_ha"] = inter["plantado_periodo_ha"] * inter["sobrev"]
    out = inter.groupby(campo_unidad)[["plantado_periodo_ha", "recuperacion_esperada_ha"]].sum()
    return out.round(2).reset_index().rename(columns={campo_unidad: "unidad"})


# ==========================================================================
# 2. Utilidades ráster / vector
# ==========================================================================
def rasterizar(geoms, valores, shape, transform, fill=0, dtype="int32"):
    from rasterio.features import rasterize
    pares = [(g, v) for g, v in zip(geoms, valores) if g is not None and not g.is_empty]
    if not pares:
        return np.full(shape, fill, dtype=dtype)
    return rasterize(pares, out_shape=shape, transform=transform, fill=fill, dtype=dtype)


def guardar_tif(ruta, arr, transform, crs=CRS, nodata=None):
    import rasterio
    perfil = dict(driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                  dtype=arr.dtype, crs=crs, transform=transform, compress="deflate")
    if nodata is not None:
        perfil["nodata"] = nodata
    with rasterio.open(ruta, "w", **perfil) as dst:
        dst.write(arr, 1)


def _perfil_tif(geobox, dtype, nodata=None):
    """GeoTIFF comprimido que se llena por ventanas. Las partes que nunca se escriben no
    ocupan disco (SPARSE_OK) y se leen como 0, o como nodata si lo tiene."""
    ny, nx = geobox.shape
    perfil = dict(driver="GTiff", height=ny, width=nx, count=1, dtype=dtype, crs=CRS,
                  transform=geobox.affine, compress="deflate", sparse_ok=True, bigtiff="IF_SAFER")
    if ny >= 512 and nx >= 512:
        perfil.update(tiled=True, blockxsize=512, blockysize=512)
    if nodata is not None:
        perfil["nodata"] = nodata
    return perfil


def ram_pico_mb() -> float | None:
    """RAM máxima que ha usado el proceso hasta ahora, en MB (None si no se puede medir)."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class Contadores(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

            k32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
            c = Contadores()
            c.cb = ctypes.sizeof(c)
            if psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
                return c.PeakWorkingSetSize / 2**20
            return None
        import resource
        pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return pico / 2**20 if sys.platform == "darwin" else pico / 1024
    except Exception:
        return None


class CapasVector:
    """Capas vectoriales de la corrida (ya en CRS), rasterizadas bloque por bloque.

    Rasterizar un bloque da los mismos píxeles que recortar el ráster completo: GDAL
    marca cada píxel según si su centro cae dentro del polígono.
    """

    def __init__(self, aoi, zona_forestal=None, reforestacion=None, unidades=None, etiquetas=None):
        """zona_forestal puede traer la columna "_clave" (número de clave de la Serie VII, 1..k) y
        etiquetas, la columna "_destino" (1..4): las zonas no forestales con que se entrena el
        clasificador de destino."""
        self.aoi, self.zf, self.refo, self.uni, self.etq = aoi, zona_forestal, reforestacion, unidades, etiquetas

    @staticmethod
    def _rasterizar(gdf, geobox, numerar=False, dtype="uint8", campo=None):
        """1 dentro de los polígonos, el valor de `campo` o, con numerar, el número de polígono (1..n).
        Los píxeles marcados son los mismos con cualquier valor (solo cambia qué se escribe)."""
        from shapely.geometry import box
        idx = np.sort(gdf.sindex.query(box(*geobox.boundingbox[:4])))  # solo los que tocan el bloque
        if numerar:
            vals = (idx + 1).tolist()
        elif campo is not None and campo in gdf.columns:
            vals = gdf[campo].iloc[idx].astype(int).tolist()
        else:
            vals = [1] * len(idx)
        return rasterizar(gdf.geometry.iloc[idx], vals, tuple(geobox.shape), geobox.affine, dtype=dtype)

    def dentro(self, geobox):
        return self._rasterizar(self.aoi, geobox).astype(bool)

    def unidades(self, geobox, dentro):
        """Ráster de unidades (1..n); sin --unidades, la zona entera es la unidad 1."""
        if self.uni is None:
            return dentro.astype("int32")
        return self._rasterizar(self.uni, geobox, numerar=True, dtype="int32")

    def etiquetas(self, geobox):
        """Etiqueta de destino (1..4) de las zonas no forestales; 0 donde no hay."""
        if self.etq is None:
            return np.zeros(tuple(geobox.shape), dtype=np.uint8)
        return self._rasterizar(self.etq, geobox, campo="_destino")

    def de_bloque(self, geobox):
        """dentro, zona, en_refo, unidades y claves (número de clave de la Serie VII en la zona;
        0 fuera de ella o en reforestación fuera de la zona forestal)."""
        dentro = self.dentro(geobox)
        en_refo = (np.zeros(tuple(geobox.shape), dtype=bool) if self.refo is None
                   else self._rasterizar(self.refo, geobox).astype(bool))
        zona = dentro.copy()
        claves = np.zeros(tuple(geobox.shape), dtype=np.int16)
        if self.zf is not None:  # lo reforestado fuera de la zona forestal también cuenta
            claves = self._rasterizar(self.zf, geobox, dtype="int16", campo="_clave")
            zona &= (claves > 0) | en_refo
            claves[~zona] = 0
        return dentro, zona, en_refo, self.unidades(geobox, dentro), claves


# ==========================================================================
# 3. Descarga y compuestos Sentinel-2 (Earth Search, sin cuenta)
# ==========================================================================
def _configurar_lectura():
    from odc.stac import configure_rio
    # Caché en RAM (no en disco) de los pedazos de COG ya bajados: los incendios cercanos y de
    # fechas parecidas leen los mismos bloques internos, y así no se bajan otra vez.
    # Límites de espera: sin ellos, una conexión colgada deja la corrida esperando para siempre.
    # Se corta si no conecta en 30 s o si deja de llegar información por 60 s (una descarga lenta
    # pero viva no se corta); GDAL reintenta y, si no se recupera, la corrida falla con error y se
    # puede reanudar con el mismo comando.
    configure_rio(cloud_defaults=True, aws={"aws_unsigned": True},
                  CPL_VSIL_CURL_CACHE_SIZE=str(CACHE_RAM_MB * 2**20),
                  GDAL_HTTP_CONNECTTIMEOUT="30", GDAL_HTTP_LOW_SPEED_TIME="60",
                  GDAL_HTTP_LOW_SPEED_LIMIT="1")


def geobox_de(gdf):
    """Malla de 10 m que cubre la zona. Los bordes de píxel caen en múltiplos de 10 m, igual
    que en las teselas Sentinel-2, así que los píxeles coinciden sin remuestrear."""
    from odc.geo.geobox import GeoBox
    minx, miny, maxx, maxy = gdf.to_crs(CRS).total_bounds
    return GeoBox.from_bbox((minx, miny, maxx, maxy), CRS, resolution=RES)


def buscar_items(geobox, inicio, fin, nubes_max=NUBES_MAX):
    from pystac_client import Client
    bbox = list(geobox.geographic_extent.boundingbox)
    cat = Client.open(STAC_URL, timeout=120)  # sin límite, una consulta colgada no termina nunca
    for col in COLECCIONES:
        items = list(cat.search(collections=[col], bbox=bbox, datetime=f"{inicio}/{fin}",
                                query={"eo:cloud_cover": {"lt": nubes_max}}).items())
        if items:
            return items
    return []


def _tesela(item) -> str:
    """Clave MGRS de la escena (p. ej. 14QNG)."""
    p = item.properties
    if p.get("grid:code"):
        return str(p["grid:code"]).replace("MGRS-", "")
    if p.get("s2:mgrs_tile"):
        return str(p["s2:mgrs_tile"])
    if p.get("mgrs:grid_square"):
        return f"{p.get('mgrs:utm_zone', '')}{p.get('mgrs:latitude_band', '')}{p['mgrs:grid_square']}"
    return item.id


def limitar_escenas(items, maximo):
    """Deja las `maximo` escenas menos nubladas de cada tesela (todas si maximo es None).
    Se aplica a la búsqueda de toda la zona, así cada bloque usa las mismas escenas."""
    if not maximo:
        return items
    por_tesela = defaultdict(list)
    for it in items:
        por_tesela[_tesela(it)].append(it)
    elegidas = set()
    for its in por_tesela.values():
        its.sort(key=lambda it: (it.properties.get("eo:cloud_cover", 100),
                                 str(it.properties.get("datetime")), it.id))
        elegidas.update(id(it) for it in its[:maximo])
    return [it for it in items if id(it) in elegidas]


def items_anuales(geobox, anio, nubes_max=NUBES_MAX, escenas_max=None, ventana=VENTANA_COBERTURA):
    """Escenas de la ventana del año (nov-dic por defecto) para toda la zona, en una sola búsqueda."""
    ini, fin = ventana
    items = buscar_items(geobox, f"{anio}-{ini}", f"{anio}-{fin}", nubes_max)
    if not items:
        sys.exit(f"No hay imágenes Sentinel-2 del {ini} al {fin} de {anio} en la zona.")
    elegidas = limitar_escenas(items, escenas_max)
    extra = f" (de {len(items)}; máximo {escenas_max} por tesela)" if len(elegidas) < len(items) else ""
    print(f"  {len(elegidas)} escenas para el compuesto de {anio}{extra}")
    return elegidas


class Escenas:
    """Escenas de un año con su huella: la imagen completa de la tesela, que es la que usa
    odc-stac para decidir qué escenas leer en cada parte de la malla."""

    def __init__(self, items, crs):
        from odc.stac import parse_items
        self.items = items
        self.huellas = [p.safe_geometry(crs) for p in parse_items(items)]

    def en(self, geobox):
        """Escenas que se traslapan con el bloque; las demás no le aportan ningún píxel. Tampoco
        las que solo tocan su borde (pasa en las costuras entre teselas): no tienen píxeles en
        el bloque y odc-stac las abriría de todos modos."""
        ext = geobox.extent.geom
        return [it for it, h in zip(self.items, self.huellas)
                if h is None or (h.geom.intersects(ext) and not h.geom.touches(ext))]


def _escala(item, banda):
    """Escala y offset de reflectancia (desde 2022 Sentinel-2 L2A trae offset -0.1)."""
    asset = item.assets.get(banda)
    rb = {}
    if asset is not None:
        rb = (asset.extra_fields.get("raster:bands") or [{}])[0]
    escala, offset = rb.get("scale"), rb.get("offset")
    if escala is None:
        escala = 1e-4
    if offset is None:
        try:
            offset = -0.1 if float(item.properties.get("s2:processing_baseline", 0)) >= 4.0 else 0.0
        except (TypeError, ValueError):
            offset = 0.0
    return float(escala), float(offset)


def compuesto_indice(items, indice, geobox) -> np.ndarray:
    """Mediana temporal del índice (ndvi o nbr) con nubes y sombras enmascaradas."""
    import xarray as xr
    from odc.stac import load

    b1, b2 = BANDAS[indice]
    grupos = defaultdict(list)
    for it in items:
        grupos[_escala(it, b1)].append(it)
    partes = []
    for (escala, offset), its in grupos.items():
        ds = load(its, bands=[b1, b2, "scl"], geobox=geobox, groupby="solar_day",
                  chunks={"x": 2048, "y": 2048}, resampling={"scl": "nearest", "*": "bilinear"})
        ok = ds["scl"].isin(SCL_VALIDOS) & (ds[b1] > 0) & (ds[b2] > 0)
        x1 = ds[b1].astype("float32") * escala + offset
        x2 = ds[b2].astype("float32") * escala + offset
        partes.append(((x1 - x2) / (x1 + x2)).where(ok))
    serie = xr.concat(partes, dim="time") if len(partes) > 1 else partes[0]
    return serie.chunk({"time": -1}).median("time", skipna=True).compute().values


def _dif_norm(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        return (a - b) / (a + b)


def rasgos_en_puntos(items, geobox, filas, cols) -> np.ndarray:
    """Rasgos del clasificador de destino (RASGOS) en los píxeles (filas, cols) del geobox.

    Para cada escena: reflectancia de B03, B04, B08, B8A, B11 y B12 (las de 20 m pasan a 10 m por
    vecino más cercano: así un píxel da lo mismo con cualquier ventana) y los índices NDVI (B08,
    B04), NBR (B8A, B12), NDBI (B11, B08) y MNDWI (B03, B11), con nubes y sombras enmascaradas
    con la SCL. Luego la mediana temporal de cada uno, igual que el compuesto de NDVI. Solo se
    guardan los puntos pedidos, no las imágenes completas: lee los bloques de COG como el
    compuesto, pero ocupa poca memoria. Regresa (puntos x len(RASGOS)) float32; NaN sin dato.
    """
    from odc.stac import load

    out = np.full((len(filas), len(RASGOS)), np.nan, dtype="float32")
    if not len(filas) or not items:
        return out
    import xarray as xr
    fy, fx = xr.DataArray(np.asarray(filas), dims="p"), xr.DataArray(np.asarray(cols), dims="p")
    grupos = defaultdict(list)
    for it in items:
        grupos[tuple(_escala(it, b) for b in BANDAS_RASGOS)].append(it)
    crudos = []
    for escalas, its in grupos.items():
        ds = load(its, bands=[*BANDAS_RASGOS, "scl"], geobox=geobox, groupby="solar_day",
                  chunks={"x": 2048, "y": 2048}, resampling="nearest")
        pts = ds.isel(y=fy, x=fx).compute()
        crudos.append((escalas, {b: pts[b].values for b in [*BANDAS_RASGOS, "scl"]}))
    # Por pedazos de puntos, para no tener en memoria todas las escenas en float32
    for i0 in range(0, len(filas), 50_000):
        sl = slice(i0, i0 + 50_000)
        series = []
        for escalas, v in crudos:
            ok = np.isin(v["scl"][:, sl], SCL_VALIDOS)
            refl = []
            for b, (esc, off) in zip(BANDAS_RASGOS, escalas):
                ok &= v[b][:, sl] > 0
                refl.append(v[b][:, sl].astype("float32") * esc + off)
            x = np.stack(refl, axis=-1)
            x[~ok] = np.nan
            series.append(x)
        x = np.concatenate(series)  # (escenas, puntos, bandas)
        g, r, nir, n8, s1, s2 = (x[..., j] for j in range(len(BANDAS_RASGOS)))
        todo = np.concatenate([x, np.stack([_dif_norm(nir, r), _dif_norm(n8, s2), _dif_norm(s1, nir),
                                            _dif_norm(g, s1)], axis=-1)], axis=-1)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # puntos sin ninguna escena válida
            out[sl] = np.nanmedian(todo, axis=0)
    return out


def ndvi_anual(geobox, anio, nubes_max=NUBES_MAX, escenas_max=None, ventana=VENTANA_COBERTURA) -> np.ndarray:
    return compuesto_indice(items_anuales(geobox, anio, nubes_max, escenas_max, ventana), "ndvi", geobox)


def ventana_incendio(geobox_total, geom):
    """Filas y columnas (r0, r1, c0, c1) del polígono + 200 m en la malla total, o None."""
    from rasterio.windows import from_bounds

    minx, miny, maxx, maxy = geom.buffer(200).bounds
    w = from_bounds(minx, miny, maxx, maxy, transform=geobox_total.affine)
    ny, nx = geobox_total.shape
    r0, c0 = max(int(np.floor(w.row_off)), 0), max(int(np.floor(w.col_off)), 0)
    r1 = min(int(np.ceil(w.row_off + w.height)), ny)
    c1 = min(int(np.ceil(w.col_off + w.width)), nx)
    if r1 <= r0 or c1 <= c0:
        return None
    return r0, r1, c0, c1


class CatalogoLocal:
    """Escenas de toda la zona y de todo el periodo de los incendios, buscadas en una sola consulta.

    Cada incendio filtra aquí las suyas (misma huella, fechas y nubes que pediría al catálogo), en
    lugar de hacer dos consultas propias. Si el filtro no encuentra nada, pregunta al catálogo como
    antes (por ejemplo, para probar la segunda colección).
    """

    def __init__(self, geobox, inicio, fin, nubes_max=NUBES_MAX):
        from shapely.geometry import shape
        self.nubes_max = nubes_max
        self.items = buscar_items(geobox, inicio, fin, nubes_max)
        self.huellas = [shape(it.geometry) for it in self.items]
        self.fechas = [pd.Timestamp(it.properties["datetime"]).tz_convert("UTC").tz_localize(None)
                       for it in self.items]

    def buscar(self, geobox, inicio, fin):
        from shapely.geometry import box
        caja = box(*geobox.geographic_extent.boundingbox)
        # Igual que la consulta inicio/fin: desde las 00:00 de inicio hasta el final del día fin
        t0, t1 = pd.Timestamp(str(inicio)), pd.Timestamp(str(fin)) + pd.Timedelta(days=1)
        res = [it for it, h, t in zip(self.items, self.huellas, self.fechas) if t0 <= t < t1 and h.intersects(caja)]
        return res or buscar_items(geobox, inicio, fin, self.nubes_max)


def dnbr_incendio(geobox_total, geom, fecha, nubes_max=NUBES_MAX, catalogo=None):
    """dNBR = NBR antes - NBR después, en la ventana del polígono (alineada a la malla total)."""
    w = ventana_incendio(geobox_total, geom)
    if w is None:
        return None
    r0, r1, c0, c1 = w
    sub = geobox_total[r0:r1, c0:c1]
    buscar = catalogo.buscar if catalogo else (lambda g, i, f: buscar_items(g, i, f, nubes_max))
    antes = buscar(sub, (fecha - timedelta(days=75)).date(), (fecha - timedelta(days=5)).date())
    despues = buscar(sub, (fecha + timedelta(days=10)).date(), (fecha + timedelta(days=70)).date())
    if not antes or not despues:
        return None
    dnbr = compuesto_indice(antes, "nbr", sub) - compuesto_indice(despues, "nbr", sub)
    return (slice(r0, r1), slice(c0, c1)), dnbr


# ==========================================================================
# 4. Cálculo por bloques
# ==========================================================================
@dataclass(frozen=True)
class Bloque:
    """Rectángulo de la malla total: filas r0:r1, columnas c0:c1."""
    r0: int
    r1: int
    c0: int
    c1: int
    malla: str = ""  # tesela a cuya malla interna está alineado

    @property
    def id(self):
        return f"f{self.r0}_c{self.c0}"

    @property
    def forma(self):
        return (self.r1 - self.r0, self.c1 - self.c0)

    @property
    def ventana(self):
        return slice(self.r0, self.r1), slice(self.c0, self.c1)

    def geobox(self, geobox_total):
        return geobox_total[self.r0:self.r1, self.c0:self.c1]


def _cortes(a, b, origen, tam):
    """Tramos de [a, b) cortados en las líneas origen + k * tam."""
    lineas = [a]
    k = (a - origen) // tam + 1
    while origen + k * tam < b:
        lineas.append(origen + k * tam)
        k += 1
    lineas.append(b)
    return list(zip(lineas[:-1], lineas[1:]))


def _origen_10m(item):
    """Esquina superior izquierda de la malla de 10 m (B04) de la escena, según proj:transform."""
    asset = item.assets.get("red")
    if asset is None:
        return None
    campos = {**item.properties, **asset.extra_fields}
    tr, epsg = campos.get("proj:transform"), campos.get("proj:epsg")
    codigo = campos.get("proj:code") or (f"EPSG:{epsg}" if epsg else None)
    if not tr or str(codigo).upper() != CRS or abs(tr[0] - RES) > 1e-6 or abs(tr[4] + RES) > 1e-6:
        return None
    return float(tr[2]), float(tr[5])


def origenes_teselas(items):
    """[(x0, y0, tesela)]: origen de la malla de cada tesela que aparece en las escenas."""
    vistos = defaultdict(Counter)
    for it in items:
        o = _origen_10m(it)
        if o is not None:
            vistos[_tesela(it)][o] += 1
    return [(*c.most_common(1)[0][0], tesela) for tesela, c in sorted(vistos.items())]


def bloques_alineados(geobox, origenes, tam, lado=LADO_TESELA):
    """Divide la malla en bloques de hasta tam x tam píxeles alineados a la malla interna de
    los COG de Sentinel-2. Cada píxel queda en un solo bloque.

    Los COG guardan cada banda en bloques internos de 10.24 km que arrancan en el origen de
    su tesela, y las teselas vecinas tienen la malla desfasada. Criterio: la zona se reparte
    en "dominios", uno por tesela, cortados en los orígenes de las teselas (cada 100 km, más
    o menos 40 m); dentro de cada dominio los bloques siguen la malla de su tesela. Así cada
    bloque interno de una tesela se lee una sola vez dentro de su dominio. Solo se releen,
    en las costuras, los bloques internos con que la tesela vecina se mete en el dominio (la
    franja de ~10 km en que se traslapan las teselas, que de todos modos se lee de las dos).
    Si no hay origen para algún cuadro, se usa la línea de 100 km.

    origenes: [(x0, y0, nombre)] esquinas superiores izquierdas de las teselas, en el CRS.
    """
    tr = geobox.affine
    res, X0, Y0 = tr.a, tr.c, tr.f
    ny, nx = geobox.shape
    xs, ys, teselas = defaultdict(list), defaultdict(list), {}
    for x0, y0, nombre in origenes:
        i, k = round(x0 / lado), round(y0 / lado)
        xs[i].append(x0)
        ys[k].append(y0)
        teselas[(i, k)] = (x0, y0, nombre)

    def linea(n, valores):
        return Counter(valores[n]).most_common(1)[0][0] if valores.get(n) else n * lado

    def col(x):
        return min(max(int(round((x - X0) / res)), 0), nx)

    def fila(y):
        return min(max(int(round((Y0 - y) / res)), 0), ny)

    bloques = []
    for k in range(math.ceil(Y0 / lado) + 1, math.floor((Y0 - ny * res) / lado) - 1, -1):
        r_a, r_b = fila(linea(k, ys)), fila(linea(k - 1, ys))  # franja entre las líneas k y k - 1
        if r_a >= r_b:
            continue
        for i in range(math.floor(X0 / lado) - 1, math.ceil((X0 + nx * res) / lado) + 1):
            c_a, c_b = col(linea(i, xs)), col(linea(i + 1, xs))
            if c_a >= c_b:
                continue
            x0, y0, nombre = teselas.get((i, k), (linea(i, xs), linea(k, ys), ""))
            for r0, r1 in _cortes(r_a, r_b, int(round((Y0 - y0) / res)), tam):
                for c0, c1 in _cortes(c_a, c_b, int(round((x0 - X0) / res)), tam):
                    bloques.append(Bloque(r0, r1, c0, c1, nombre))
    return bloques


def _cruce(ventana, b: Bloque):
    """Parte común de una ventana (r0, r1, c0, c1) y un bloque: (en el bloque, en la ventana)."""
    r0, r1, c0, c1 = ventana
    rr0, rr1, cc0, cc1 = max(r0, b.r0), min(r1, b.r1), max(c0, b.c0), min(c1, b.c1)
    if rr0 >= rr1 or cc0 >= cc1:
        return None
    return ((slice(rr0 - b.r0, rr1 - b.r0), slice(cc0 - b.c0, cc1 - b.c0)),
            (slice(rr0 - r0, rr1 - r0), slice(cc0 - c0, cc1 - c0)))


def _a_json(v):
    return v.item() if isinstance(v, np.generic) else v


class Progreso:
    """Avance de una corrida, para retomarla desde el último bloque si se interrumpe.

    Vive en <salida>/progreso_<base>_<actual>/ y se borra al terminar:
      parametros.json   parámetros de la corrida (no se mezclan corridas distintas) y umbral
      incendios.jsonl   una línea por incendio: sus cifras y su máscara de quemado comprimida
      bloques.jsonl     una línea por bloque terminado: conteos por unidad y por incendio
      cambio/<id>.npz   el ráster de cambio de cada bloque (uint8 comprimido); al final se
                        juntan en cambio_<base>_<actual>.tif y pesan lo mismo que ese archivo
    Las líneas JSON pesan pocos KB. Cada línea se escribe completa o se ignora al reanudar.
    """

    def __init__(self, carpeta, firma, reiniciar=False, log=print):
        self.carpeta = Path(carpeta)
        firma = json.loads(json.dumps(firma))
        if reiniciar and self.carpeta.exists():
            shutil.rmtree(self.carpeta)
        self.incendios, self.bloques, self.umbral = {}, {}, None
        ruta = self.carpeta / "parametros.json"
        self.nuevo = not ruta.exists()
        if self.nuevo:
            (self.carpeta / "cambio").mkdir(parents=True, exist_ok=True)
            self.firma = firma
            self._escribir_parametros()
            return
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        if datos["firma"] != firma:
            distintos = sorted(k for k in set(firma) | set(datos["firma"])
                               if firma.get(k) != datos["firma"].get(k))
            sys.exit(f"{self.carpeta} es de una corrida interrumpida con otros parámetros "
                     f"({', '.join(distintos)}). Usa --reiniciar para empezar de nuevo, u otra --salida.")
        self.firma, self.umbral = firma, datos.get("umbral")
        for reg in self._leer("incendios.jsonl"):
            i = reg.pop("i")
            self.incendios[i] = None if reg.get("omitido") else self._decodificar(reg)
        for reg in self._leer("bloques.jsonl"):
            if self.pieza(reg["id"]).exists():
                self.bloques[reg["id"]] = reg
        log(f"Reanudando la corrida guardada en {self.carpeta}: {len(self.incendios)} incendios "
            f"y {len(self.bloques)} bloques ya calculados")

    def pieza(self, id_bloque):
        return self.carpeta / "cambio" / f"{id_bloque}.npz"

    def _escribir_parametros(self):
        tmp = self.carpeta / "parametros.json.tmp"
        tmp.write_text(json.dumps({"firma": self.firma, "umbral": self.umbral}, indent=1), encoding="utf-8")
        os.replace(tmp, self.carpeta / "parametros.json")

    def _leer(self, nombre):
        ruta = self.carpeta / nombre
        if not ruta.exists():
            return []
        regs = []
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            try:
                regs.append(json.loads(linea))
            except json.JSONDecodeError:  # línea a medias de una corrida que se cortó
                pass
        return regs

    def _agregar(self, nombre, reg):
        with open(self.carpeta / nombre, "a", encoding="utf-8") as f:
            f.write(json.dumps(reg) + "\n")
            f.flush()
            os.fsync(f.fileno())

    @staticmethod
    def _decodificar(reg):
        h, w = reg.pop("forma")
        bits = np.frombuffer(zlib.decompress(base64.b64decode(reg.pop("q"))), dtype=np.uint8)
        reg["q"] = np.unpackbits(bits, count=h * w).reshape(h, w).astype(bool)
        reg["ventana"] = tuple(reg["ventana"])
        return reg

    def guardar_umbral(self, umbral):
        if self.umbral != umbral:
            self.umbral = umbral
            self._escribir_parametros()

    def guardar_incendio(self, i, r):
        if r is None:
            self._agregar("incendios.jsonl", {"i": i, "omitido": True})
        else:
            reg = {"i": i, **{k: _a_json(v) for k, v in r.items() if k != "q"}}
            reg["q"] = base64.b64encode(zlib.compress(np.packbits(r["q"]).tobytes(), 6)).decode("ascii")
            reg["forma"] = list(r["q"].shape)
            self._agregar("incendios.jsonl", reg)
        self.incendios[i] = r

    def guardar_bloque(self, b: Bloque, cambio, conteos, parciales, info, vegetacion=None, extra=None):
        """vegetacion: conteos por unidad y clave (conteos_vegetacion); extra: arreglos que van en la
        pieza junto al ráster de cambio (los rasgos del clasificador de destino)."""
        tmp = self.carpeta / "cambio" / f"{b.id}.tmp"
        with open(tmp, "wb") as f:
            np.savez_compressed(f, cambio=cambio, **(extra or {}))
        os.replace(tmp, self.pieza(b.id))
        reg = {"id": b.id, "ventana": [b.r0, b.r1, b.c0, b.c1], **info,
               "conteos": {str(i): conteos[i].tolist() for i in np.flatnonzero(conteos[:, 0]) if i > 0},
               "incendios": {str(i): list(v) for i, v in parciales.items()}}
        if vegetacion is not None:
            reg["vegetacion"] = {str(i): vegetacion[i].tolist() for i in np.flatnonzero(vegetacion[:, 0])}
        self._agregar("bloques.jsonl", reg)  # al final: marca el bloque como terminado
        self.bloques[b.id] = reg

    def borrar(self):
        shutil.rmtree(self.carpeta, ignore_errors=True)


class Indices:
    """Rásters opcionales de NDVI y dNBR (float32), escritos por ventanas (--guardar-indices)."""

    def __init__(self, salida, geobox, anio_base, anio, nuevo):
        import rasterio
        self.rutas = {anio_base: salida / f"ndvi_{anio_base}.tif", anio: salida / f"ndvi_{anio}.tif",
                      "dnbr": salida / "dnbr.tif"}
        for ruta in self.rutas.values():
            if nuevo or not ruta.exists():
                with rasterio.open(ruta, "w", **_perfil_tif(geobox, "float32", nodata=np.nan)):
                    pass

    def escribir(self, clave, filas, cols, arr, mascara=None):
        import rasterio
        from rasterio.windows import Window
        w = Window(cols.start, filas.start, cols.stop - cols.start, filas.stop - filas.start)
        with rasterio.open(self.rutas[clave], "r+") as dst:
            if mascara is not None:  # los incendios que se enciman se sobreponen, como antes
                arr = np.where(mascara, arr, dst.read(1, window=w))
            dst.write(np.asarray(arr, dtype="float32"), 1, window=w)


@dataclass
class Resultado:
    balance: pd.DataFrame
    incendios: pd.DataFrame
    umbral: float
    zona_ha: float
    progreso: Progreso
    vegetacion: pd.DataFrame | None = None   # por unidad y clave de la Serie VII
    tipos: pd.DataFrame | None = None        # por unidad y tipo de bosque
    destino: pd.DataFrame | None = None      # otras pérdidas por unidad y uso al que pasaron
    exactitud: pd.DataFrame | None = None    # del clasificador de destino, con datos reservados
    resumen_destino: dict | None = None


def calcular_por_bloques(geobox, bloques, capas, leer_ndvi, leer_dnbr, incendios, nombres, *,
                         anio_base, anio, umbral, margen, umbral_dnbr, salida, firma,
                         guardar_indices=False, reiniciar=False, hilos=1, log=print,
                         claves=None, descripciones=None, leer_rasgos=None,
                         muestreo=Muestreo()) -> Resultado:
    """Balance, incendios y ráster de cambio, bloque por bloque.

    Procesar de una sola vez es el caso de un solo bloque que cubre toda la malla.
      - Los bloques no se enciman, así que cada píxel se cuenta una vez.
      - Cada incendio se calcula una sola vez en su propia ventana (igual que antes). Su
        máscara de quemado se reparte entre los bloques que toca; lo que depende del bosque
        (quemado en bosque, perdido al cierre) se suma bloque por bloque. Da una fila por
        incendio aunque cruce varios bloques.
      - Con umbral "auto" se leen primero los compuestos del año base de todos los bloques
        y se guardan en memoria solo los valores dentro de la zona (~0.9 GB para el estado);
        luego se calcula Otsu con todos y se sigue con el año actual.
    leer_ndvi(anio, bloque) -> (arreglo float32 del bloque, número de escenas)
    leer_dnbr(geom, fecha) -> ((filas, columnas) en la malla total, dNBR) o None
    hilos: incendios que se leen a la vez. Se procesan y guardan en su orden, así que el
    resultado es idéntico al de leerlos uno por uno.
    claves: claves de la Serie VII con número 1..k en capas (columna "_clave"); con ellas se
    desglosa por clave y por tipo de bosque. None = sin desglose.
    leer_rasgos(bloque, filas, cols) -> rasgos del año actual en esos píxeles del bloque. Con
    él se clasifica el destino de las otras pérdidas: cada bloque guarda los rasgos de sus
    otras pérdidas y de sus puntos de muestreo, y al final se entrena un solo clasificador con
    todas las muestras (ordenadas por posición) y se predice. Así da lo mismo por bloques.
    """
    salida = Path(salida)
    sufijo = f"{anio_base}_{anio}"
    prog = Progreso(salida / f"progreso_{sufijo}", firma, reiniciar, log)
    indices = Indices(salida, geobox, anio_base, anio, prog.nuevo) if guardar_indices else None

    # 1. Incendios: dNBR de cada uno en su ventana, una sola vez
    quemas = {i: r for i, r in prog.incendios.items() if r is not None}
    faltan = [(i, inc) for i, inc in enumerate(incendios) if i not in prog.incendios]
    if incendios:
        log(f"dNBR por incendio ({len(incendios)}; {len(prog.incendios)} ya calculados"
            + (f"; {hilos} a la vez" if hilos > 1 and faltan else "") + ")")
    if hilos > 1 and len(faltan) > 1:
        # Las lecturas corren adelantadas en paralelo; el proceso y el guardado van en orden
        from concurrent.futures import ThreadPoolExecutor
        ejecutor = ThreadPoolExecutor(hilos)
        futuros = {i: ejecutor.submit(leer_dnbr, geom, fecha) for i, (_, fecha, geom) in faltan}
        obtener = lambda i, geom, fecha: futuros[i].result()  # noqa: E731
    else:
        ejecutor = None
        obtener = lambda i, geom, fecha: leer_dnbr(geom, fecha)  # noqa: E731
    try:
        for i, (clave, fecha, geom) in faltan:
            _procesar_incendio(i, clave, fecha, geom, obtener(i, geom, fecha), geobox, umbral_dnbr,
                               indices, prog, quemas, log)
    finally:
        if ejecutor:
            ejecutor.shutdown(wait=True, cancel_futures=True)

    return _calcular_bloques(geobox, bloques, capas, leer_ndvi, nombres, prog, indices, quemas,
                             anio_base=anio_base, anio=anio, umbral=umbral, margen=margen,
                             salida=salida, sufijo=sufijo, log=log, claves=claves,
                             descripciones=descripciones, leer_rasgos=leer_rasgos, muestreo=muestreo)


def _procesar_incendio(i, clave, fecha, geom, res, geobox, umbral_dnbr, indices, prog, quemas, log):
    """Máscara de quemado y cifras de un incendio a partir de su dNBR; lo guarda en el avance."""
    if res is None:
        log(f"  incendio {clave}: sin imágenes antes/después, se omite")
        prog.guardar_incendio(i, None)
        return
    (rs, cs), d = res
    poly = rasterizar([geom], [1], d.shape, geobox[rs, cs].affine, dtype="uint8").astype(bool)
    q = poly & (np.nan_to_num(d, nan=0) >= umbral_dnbr)
    r = {"incendio": clave, "fecha_inicio": f"{fecha:%Y-%m-%d}",
         "poligono_ha": round(poly.sum() * HA_PIXEL, 2),
         "quemado_dnbr_ha": round(q.sum() * HA_PIXEL, 2),
         "dnbr_mediana": round(float(np.nanmedian(np.where(poly, d, np.nan))), 3),
         "ventana": (rs.start, rs.stop, cs.start, cs.stop), "q": q}
    if indices:
        indices.escribir("dnbr", rs, cs, d, poly)
    prog.guardar_incendio(i, r)
    quemas[i] = r
    log(f"  incendio {clave} ({fecha:%Y-%m-%d}): {q.sum() * HA_PIXEL:.1f} ha quemadas")


def _rasgos_bloque(b, gbb, cambio, dentro, zona, r_uni, capas, leer_rasgos, muestreo):
    """Rasgos de las otras pérdidas del bloque (en orden de filas, igual que cambio == PERD_OTRA)
    y de sus puntos de muestreo, para guardarlos en la pieza del bloque."""
    pf, pc = np.nonzero(cambio == PERD_OTRA)
    mf, mc, my = puntos_muestra(b, dentro, zona, capas.etiquetas(gbb), muestreo.paso)
    filas, cols = np.concatenate([pf, mf]), np.concatenate([pc, mc])
    X = leer_rasgos(b, filas, cols) if len(filas) else np.empty((0, len(RASGOS)), dtype="float32")
    X = np.asarray(X, dtype="float32")
    return {"x_perdida": X[:len(pf)], "u_perdida": r_uni[pf, pc].astype(np.int32),
            "x_muestra": X[len(pf):], "y_muestra": my.astype(np.uint8),
            "f_muestra": (mf + b.r0).astype(np.int32), "c_muestra": (mc + b.c0).astype(np.int32)}


def _calcular_bloques(geobox, bloques, capas, leer_ndvi, nombres, prog, indices, quemas, *,
                      anio_base, anio, umbral, margen, salida, sufijo, log, claves=None,
                      descripciones=None, leer_rasgos=None, muestreo=Muestreo()):
    """Pasos 2 a 5 de calcular_por_bloques, con los incendios ya calculados."""
    n = len(nombres)
    nk = len(claves) if claves is not None else 0  # número de claves de la Serie VII

    # 2. Bloques que tocan la zona; de los demás solo importa qué unidades tocan
    pendientes, n_zona = [], 0
    presencia = np.zeros(n + 1, dtype=np.int64)
    for b in bloques:
        if b.id in prog.bloques:
            n_zona += 1
            continue
        gbb = b.geobox(geobox)
        dentro = capas.dentro(gbb)
        if dentro.any():
            pendientes.append(b)
            n_zona += 1
        else:
            presencia += np.bincount(capas.unidades(gbb, dentro).ravel(), minlength=n + 1)
    if len(bloques) > 1:
        log(f"{n_zona} de {len(bloques)} bloques tocan la zona; faltan {len(pendientes)}")

    # 3. Umbral de NDVI
    guardados = {}
    if prog.umbral is not None:
        umbral = prog.umbral
    elif str(umbral).lower() == "auto":
        log(f"Compuesto {anio_base} de toda la zona para el umbral automático")
        for k, b in enumerate(pendientes, 1):
            t0 = time.perf_counter()
            ndvi_b, n_b = leer_ndvi(anio_base, b)
            if indices:
                indices.escribir(anio_base, *b.ventana, ndvi_b)
            guardados[b.id] = (ndvi_b[capas.dentro(b.geobox(geobox))], n_b, time.perf_counter() - t0)
            if len(pendientes) > 1:
                log(f"  [{k}/{len(pendientes)}] bloque {b.id} {b.malla}: {n_b} escenas, "
                    f"{guardados[b.id][2]:.0f} s")
        piezas = [v for v, _, _ in guardados.values()]
        umbral = umbral_otsu(piezas[0] if len(piezas) == 1 else piezas)
        log(f"  Umbral NDVI automático (Otsu, provisional hasta calibrar): {umbral:.2f}")
    else:
        umbral = float(umbral)
    prog.guardar_umbral(umbral)

    # 4. Cada bloque: compuestos, máscaras, quemado, conteos y ráster de cambio
    for b in pendientes:
        t0 = time.perf_counter()
        gbb = b.geobox(geobox)
        dentro, zona, en_refo, r_uni, r_clave = capas.de_bloque(gbb)
        if b.id in guardados:
            vals, n_b, seg_b = guardados.pop(b.id)
            ndvi_base = np.full(b.forma, np.nan, dtype=vals.dtype)
            ndvi_base[dentro] = vals  # fuera de la zona no se usa
        else:
            ndvi_base, n_b = leer_ndvi(anio_base, b)
            seg_b = 0.0
            if indices:
                indices.escribir(anio_base, *b.ventana, ndvi_base)
        ndvi_act, n_a = leer_ndvi(anio, b)
        if indices:
            indices.escribir(anio, *b.ventana, ndvi_act)
        base, actual = mascaras_con_margen(ndvi_base, ndvi_act, umbral, margen, zona)
        del ndvi_base, ndvi_act

        quemado = np.zeros(b.forma, dtype=bool)
        parciales = {}
        for i, r in quemas.items():
            cruce = _cruce(r["ventana"], b)
            if cruce is None:
                continue
            en_b, en_q = cruce
            q = r["q"][en_q]
            quemado[en_b] |= q
            parciales[i] = [int((q & base[en_b]).sum()), int((q & base[en_b] & ~actual[en_b]).sum())]
        cambio = mapa_cambio(base, actual, quemado)
        conteos = conteos_unidades(cambio, base, actual, quemado, en_refo, r_uni, n)
        veg = (conteos_vegetacion(cambio, base, actual, zona, r_uni, r_clave, n, nk)
               if claves is not None else None)
        extra = (_rasgos_bloque(b, gbb, cambio, dentro, zona, r_uni, capas, leer_rasgos, muestreo)
                 if leer_rasgos is not None else None)
        seg = time.perf_counter() - t0 + seg_b
        ram = ram_pico_mb()
        prog.guardar_bloque(b, cambio, conteos, parciales, {
            "malla": b.malla, "zona_px": int(zona.sum()), "escenas_base": n_b, "escenas_actual": n_a,
            "segundos": round(seg, 1), "ram_pico_mb": None if ram is None else round(ram)}, veg, extra)
        if len(bloques) > 1:
            log(f"  [{len(prog.bloques)}/{n_zona}] bloque {b.id} {b.malla}: {n_b} + {n_a} escenas, "
                f"{seg:.0f} s" + ("" if ram is None else f", RAM pico {ram / 1024:.1f} GB"))

    # 5. Sumar los bloques y armar las salidas
    conteos = np.zeros((n + 1, len(COLUMNAS_BALANCE) + 1), dtype=np.int64)
    conteos[:, 0] += presencia
    parciales = defaultdict(lambda: [0, 0])
    zona_px = 0
    for reg in prog.bloques.values():
        for i, fila in reg["conteos"].items():
            conteos[int(i)] += np.asarray(fila, dtype=np.int64)
        for i, (en_bosque, perdido) in reg["incendios"].items():
            parciales[int(i)][0] += en_bosque
            parciales[int(i)][1] += perdido
        zona_px += reg["zona_px"]
    tabla = balance_de_conteos(conteos, nombres)
    filas_inc = [{"incendio": r["incendio"], "fecha_inicio": r["fecha_inicio"],
                  "poligono_ha": r["poligono_ha"], "quemado_dnbr_ha": r["quemado_dnbr_ha"],
                  "quemado_en_bosque_ha": round(np.int64(parciales[i][0]) * HA_PIXEL, 2),
                  "perdido_al_cierre_ha": round(np.int64(parciales[i][1]) * HA_PIXEL, 2),
                  "dnbr_mediana": r["dnbr_mediana"]} for i, r in sorted(quemas.items())]

    vegetacion = tipos = None
    if claves is not None:
        cveg = np.zeros(((n + 1) * (nk + 1), len(COLUMNAS_VEG)), dtype=np.int64)
        for reg in prog.bloques.values():
            for i, fila in reg.get("vegetacion", {}).items():
                cveg[int(i)] += np.asarray(fila, dtype=np.int64)
        vegetacion, tipos = tablas_vegetacion(cveg, nombres, claves, descripciones)

    # Clasificador de destino: un solo modelo con las muestras de todos los bloques
    modelo = destino = exactitud = resumen = None
    if leer_rasgos is not None:
        partes = {"f_muestra": [np.zeros(0, np.int32)], "c_muestra": [np.zeros(0, np.int32)],
                  "y_muestra": [np.zeros(0, np.uint8)], "x_muestra": [np.zeros((0, len(RASGOS)), "float32")]}
        for reg in prog.bloques.values():
            with np.load(prog.pieza(reg["id"])) as z:
                for nombre, lista in partes.items():
                    lista.append(z[nombre].reshape(-1, len(RASGOS)) if nombre == "x_muestra" else z[nombre])
        modelo, exactitud, resumen = entrenar_destino(*(np.concatenate(v) for v in partes.values()),
                                                      geobox.affine, muestreo)
        if modelo is None:
            log("  Aviso: no hay muestras de al menos dos clases de destino; las otras pérdidas quedan "
                "como 'sin dato'")
        cdest = np.zeros((n + 1, len(DESTINOS) + 1), dtype=np.int64)

    import rasterio
    from rasterio.windows import Window
    ruta_destino = salida / f"destino_{sufijo}.tif"
    with rasterio.open(salida / f"cambio_{sufijo}.tif", "w", **_perfil_tif(geobox, "uint8")) as dst, \
            (rasterio.open(ruta_destino, "w", **_perfil_tif(geobox, "uint8")) if leer_rasgos is not None
             else contextlib.nullcontext()) as dst_dest:
        for reg in prog.bloques.values():
            r0, r1, c0, c1 = reg["ventana"]
            ventana = Window(c0, r0, c1 - c0, r1 - r0)
            with np.load(prog.pieza(reg["id"])) as z:
                dst.write(z["cambio"], 1, window=ventana)
                if leer_rasgos is not None:
                    pred = predecir_destino(modelo, z["x_perdida"].reshape(-1, len(RASGOS)))
                    pieza = np.zeros(z["cambio"].shape, dtype=np.uint8)
                    pieza[z["cambio"] == PERD_OTRA] = pred  # mismo orden en que se guardaron los rasgos
                    dst_dest.write(pieza, 1, window=ventana)
                    np.add.at(cdest, (z["u_perdida"], pred), 1)
    if leer_rasgos is not None:
        destino = tabla_destino(cdest, nombres, conteos[:, 0] > 0)
    pd.DataFrame([{"bloque": reg["id"], "malla": reg["malla"], "fila0": reg["ventana"][0],
                   "fila1": reg["ventana"][1], "col0": reg["ventana"][2], "col1": reg["ventana"][3],
                   "zona_ha": round(reg["zona_px"] * HA_PIXEL, 2), "escenas_base": reg["escenas_base"],
                   "escenas_actual": reg["escenas_actual"], "segundos": reg["segundos"],
                   "ram_pico_mb": reg["ram_pico_mb"]} for reg in prog.bloques.values()]
                 ).to_csv(salida / f"bloques_{sufijo}.csv", index=False)
    return Resultado(tabla, pd.DataFrame(filas_inc), umbral, zona_px * HA_PIXEL, prog,
                     vegetacion, tipos, destino, exactitud, resumen)


# ==========================================================================
# 5. Comandos
# ==========================================================================
def cmd_calibrar(a):
    import geopandas as gpd
    _configurar_lectura()
    aoi = gpd.read_file(a.aoi)
    gb = geobox_de(aoi)
    ndvi = ndvi_anual(gb, a.anio, a.nubes_max, a.escenas_max, tuple(a.ventana))

    pts = pd.read_csv(a.puntos)
    g = gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts["lon"], pts["lat"]), crs="EPSG:4326").to_crs(CRS)
    inv = ~gb.affine
    vals = []
    for p in g.geometry:
        col, fila = inv * (p.x, p.y)
        fila, col = int(fila), int(col)
        dentro = 0 <= fila < ndvi.shape[0] and 0 <= col < ndvi.shape[1]
        vals.append(ndvi[fila, col] if dentro else np.nan)
    umbral, tabla = calibrar_umbral(np.array(vals, dtype=float), pts["clase"].to_numpy())
    mejor = tabla[tabla["umbral"] == umbral].iloc[0]
    print(f"\nUmbral recomendado: NDVI >= {umbral:.2f}")
    print(f"  exactitud global {mejor['exactitud_global']:.1%} | bosque bien detectado "
          f"{mejor['sensibilidad']:.1%} | no bosque bien detectado {mejor['especificidad']:.1%}")
    Path(a.salida).mkdir(parents=True, exist_ok=True)
    tabla.to_csv(Path(a.salida) / f"calibracion_{a.anio}.csv", index=False)


def _huella_ids(items):
    return hashlib.sha1("\n".join(sorted(it.id for it in items)).encode()).hexdigest()[:16]


def cmd_correr(a):
    import geopandas as gpd
    if a.tam_bloque <= 0 or a.tam_bloque % BLOQUE_COG:
        sys.exit(f"--tam-bloque debe ser múltiplo de {BLOQUE_COG} (la malla interna de los COG).")
    _configurar_lectura()
    out = Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)

    aoi = gpd.read_file(a.aoi).to_crs(CRS)
    gb = geobox_de(aoi)
    ny, nx = gb.shape
    zona_aoi = aoi.union_all()
    zf = refo = uni = etq = claves = descripciones = None
    if a.zona_forestal:
        usv = gpd.read_file(a.zona_forestal).to_crs(CRS)
        clave_txt = usv[a.campo_clase].astype(str)
        with warnings.catch_warnings():  # pandas avisa que la expresión tiene grupos; no se usan
            warnings.simplefilter("ignore", UserWarning)
            forestal = clave_txt.str.contains(a.clases_forestales, regex=True)
        zf = usv[forestal].copy()
        claves = sorted(clave_txt[forestal].unique())
        zf["_clave"] = clave_txt[forestal].map({c: i for i, c in enumerate(claves, start=1)}).astype("int16")
        if CAMPO_DESCRIPCION in usv.columns:
            descripciones = (usv[forestal].assign(_c=clave_txt[forestal])
                             .groupby("_c")[CAMPO_DESCRIPCION].first().astype(str).to_dict())
        print(f"Zona forestal: {len(claves)} claves de {a.campo_clase} con {a.clases_forestales!r}: "
              + ", ".join(claves))
        if a.clasificar_destino is not False:
            etq = usv[~forestal].copy()
            etq["_destino"] = [clase_destino(c, a.clases_agricola, a.clases_pecuario, a.clases_urbano)
                               for c in clave_txt[~forestal]]
    elif a.clasificar_destino:
        sys.exit("--clasificar-destino necesita --zona-forestal (sus zonas no forestales son las etiquetas).")
    if a.reforestacion:
        refo = gpd.read_file(a.reforestacion).to_crs(CRS)
    if a.unidades:
        uni = gpd.read_file(a.unidades).to_crs(CRS)
        uni = uni[uni.intersects(zona_aoi)].reset_index(drop=True)
        nombres = uni[a.campo_unidad].astype(str).tolist()
    else:
        nombres = ["zona piloto"]
    capas = CapasVector(aoi, zf, refo, uni, etq)

    incendios = []
    if a.incendios:
        inc = gpd.read_file(a.incendios).to_crs(CRS)
        inc = inc[inc.intersects(zona_aoi)].copy()
        inc["_fecha"] = leer_fechas(inc[a.campo_fecha])
        # Periodo del balance: del inicio del compuesto base al inicio del compuesto actual
        ini, fin = pd.Timestamp(f"{a.anio_base}-{a.ventana[0]}"), pd.Timestamp(f"{a.anio}-{a.ventana[0]}")
        fuera = inc[(inc["_fecha"] >= fin)]
        inc = inc[(inc["_fecha"] >= ini) & (inc["_fecha"] < fin)]
        print(f"Incendios en el periodo {ini:%Y-%m-%d} a {fin - pd.Timedelta(days=1):%Y-%m-%d}: {len(inc)}")
        if len(fuera):
            print(f"  ({len(fuera)} incendio(s) posteriores al {fin:%Y-%m-%d} quedan para el siguiente periodo)")
        for i, (_, fila) in enumerate(inc.iterrows(), start=1):
            clave = fila.get(a.campo_id, i) if a.campo_id else i
            incendios.append((clave, fila["_fecha"], fila.geometry))

    print("Cobertura base y actual")
    escenas = {anio: Escenas(items_anuales(gb, anio, a.nubes_max, a.escenas_max, tuple(a.ventana)), gb.crs)
               for anio in (a.anio_base, a.anio)}
    if a.bloques:
        origenes = origenes_teselas(escenas[a.anio_base].items + escenas[a.anio].items)
        bloques = bloques_alineados(gb, origenes, a.tam_bloque)
        print(f"Bloques de {a.tam_bloque} px ({a.tam_bloque * RES / 1000:.2f} km) alineados a la malla de "
              f"{len(origenes)} teselas: {', '.join(t for *_, t in origenes) or 'ninguna (malla de 100 km)'}")
    else:
        bloques = [Bloque(0, ny, 0, nx)]
        if ny * nx > 100e6:
            print(f"Aviso: la zona mide {ny * nx / 1e6:.0f} millones de píxeles; de una sola vez necesita "
                  f"unos {ny * nx * 4 * 3 / 2**30:.0f} GB de RAM o más. Para zonas así conviene --bloques.")

    def leer_ndvi(anio, b):
        gbb = b.geobox(gb)
        its = escenas[anio].en(gbb)
        if not its:
            return np.full(b.forma, np.nan, dtype="float32"), 0
        return compuesto_indice(its, "ndvi", gbb), len(its)

    catalogo = None
    if len(incendios) > 1:
        fechas = [f for _, f, _ in incendios]
        catalogo = CatalogoLocal(gb, (min(fechas) - timedelta(days=75)).date(),
                                 (max(fechas) + timedelta(days=70)).date(), a.nubes_max)
        print(f"Escenas para el dNBR, buscadas una vez: {len(catalogo.items)}")

    def leer_dnbr(geom, fecha):
        return dnbr_incendio(gb, geom, fecha, a.nubes_max, catalogo)

    def leer_rasgos(b, filas, cols):
        gbb = b.geobox(gb)
        return rasgos_en_puntos(escenas[a.anio].en(gbb), gbb, filas, cols)

    guardar = a.guardar_indices if a.guardar_indices is not None else not a.bloques
    # Lo que no cambia el resultado no entra en la firma (se puede reanudar con otro valor)
    firma = {k: v for k, v in vars(a).items() if k not in ("cmd", "salida", "reiniciar", "hilos_incendios")}
    firma["escenas"] = {str(anio): _huella_ids(e.items) for anio, e in escenas.items()}
    firma["malla_bloques"] = hashlib.sha1(",".join(b.id for b in bloques).encode()).hexdigest()[:16]
    res = calcular_por_bloques(gb, bloques, capas, leer_ndvi, leer_dnbr, incendios, nombres,
                               anio_base=a.anio_base, anio=a.anio, umbral=a.umbral_ndvi,
                               margen=a.margen_cambio, umbral_dnbr=a.umbral_dnbr, salida=out,
                               firma=firma, guardar_indices=guardar, reiniciar=a.reiniciar,
                               hilos=a.hilos_incendios, claves=claves, descripciones=descripciones,
                               leer_rasgos=leer_rasgos if etq is not None else None)
    if a.zona_forestal:
        print(f"  Zona forestal de referencia: {res.zona_ha:,.0f} ha")

    sufijo = f"{a.anio_base}_{a.anio}"
    tabla = res.balance
    if refo is not None and uni is not None:
        esp = recuperacion_esperada(refo, uni, a.campo_unidad, a.campo_anio, a.campo_sobrev,
                                    a.anio_base, a.anio, a.sobrev_default)
        tabla = tabla.merge(esp, on="unidad", how="left").fillna(0)
    tabla.insert(1, "umbral_ndvi", res.umbral)
    tabla.to_csv(out / f"balance_{sufijo}.csv", index=False)
    if len(res.incendios):
        res.incendios.to_csv(out / "incendios_dnbr.csv", index=False)
    if res.vegetacion is not None:
        res.vegetacion.to_csv(out / f"vegetacion_{sufijo}.csv", index=False)
        res.tipos.to_csv(out / f"tipo_bosque_{sufijo}.csv", index=False)
    if res.destino is not None:
        res.destino.to_csv(out / f"destino_perdidas_{sufijo}.csv", index=False)
        res.exactitud.to_csv(out / f"destino_exactitud_{sufijo}.csv", index=False)
    # Cómo se hizo la corrida (lo lee src/mapa_interactivo.py)
    from datetime import datetime
    (out / f"corrida_{sufijo}.json").write_text(json.dumps({
        "anio_base": a.anio_base, "anio": a.anio, "ventana": list(a.ventana),
        "umbral_ndvi": round(float(res.umbral), 4), "umbral_pedido": str(a.umbral_ndvi),
        "escenas": {str(k): len(e.items) for k, e in escenas.items()},
        "incendios": len(incendios), "nubes_max": a.nubes_max, "escenas_max": a.escenas_max,
        "bloques": a.bloques, "fecha": datetime.now().isoformat(timespec="seconds"),
        "clases_forestales": a.clases_forestales if a.zona_forestal else None,
        "zona_forestal_ha": round(res.zona_ha, 2) if a.zona_forestal else None,
        "destino": res.resumen_destino,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    res.progreso.borrar()
    print("\n" + tabla.to_string(index=False))
    if res.tipos is not None:
        tot = res.tipos.groupby("tipo_bosque", sort=False)[COLUMNAS_VEG[1:] + ["cambio_neto_ha"]].sum()
        print("\nPor tipo de bosque (ha):\n" + tot.round(1).to_string())
    if res.destino is not None:
        tot = res.destino.drop(columns="unidad").sum()
        print("\nUso al que pasaron las otras pérdidas (ha): "
              + ", ".join(f"{d} {tot[f'{d}_ha']:,.1f}" for d in DESTINOS))
        r = res.resumen_destino
        if r.get("exactitud_global") is not None:
            print(f"  Clasificador: exactitud {r['exactitud_global']:.1%} (kappa {r['kappa']}) con "
                  f"{r['muestras_prueba']:,} muestras reservadas y {r['muestras_entrenamiento']:,} de "
                  "entrenamiento. Mide el acuerdo con la Serie VII, anterior a 2023, no con el campo.")
    print(f"\nResultados en {out.resolve()}")
    print("Códigos del ráster de cambio: 0 sin bosque, 1 bosque estable, 2 pérdida por incendio, "
          "3 otra pérdida, 4 ganancia")
    if res.destino is not None:
        print("Códigos del ráster de destino: 0 no aplica, 1 agrícola, 2 pecuario, 3 urbano, 4 otro, 5 sin dato")
    ram = ram_pico_mb()
    if ram is not None:
        print(f"RAM pico del proceso: {ram / 1024:.1f} GB")


def comprobar_bloques():
    """Comprobación sintética: procesar por bloques da exactamente lo mismo que de una sola vez.

    Compara contra el cálculo original sobre arreglos completos: balance, ráster de cambio e
    incendios, con umbral fijo y automático, saltando bloques fuera de la zona, con incendios
    que cruzan bloques o se enciman, y con corridas interrumpidas y reanudadas.
    """
    import tempfile

    import geopandas as gpd
    import rasterio
    from odc.geo.geobox import GeoBox
    from rasterio.transform import from_origin
    from shapely.geometry import box

    n, x0, y0, tam = 300, 450_000, 2_150_000, 64
    gb = GeoBox((n, n), from_origin(x0, y0, RES, RES), CRS)

    def caja(c0, r0, c1, r1):  # en filas/columnas -> polígono en metros
        return box(x0 + c0 * RES, y0 - r1 * RES, x0 + c1 * RES, y0 - r0 * RES)

    rng = np.random.default_rng(11)
    base = np.where(np.arange(n)[None, :] < 180, 0.78, 0.30) + rng.normal(0, 0.06, (n, n))
    act = base + rng.normal(0, 0.06, (n, n))
    act[20:90, 20:100] = 0.25 + rng.normal(0, 0.1, (70, 80))  # incendio
    act[200:240, 120:160] = 0.28                               # tala
    act[40:80, 200:280] = 0.66                                 # reforestación visible
    ndvi = {2023: base.astype("float32"), 2024: act.astype("float32")}
    ndvi[2023][150:155, 30:60] = np.nan                        # píxeles sin dato
    dnbr = rng.normal(0.02, 0.03, (n, n)).astype("float32")
    dnbr[20:90, 20:100] += 0.45
    dnbr[60:110, 90:130] += rng.uniform(0, 0.6, (50, 40)).astype("float32")
    dnbr[165:200, 185:225] += 0.35
    dnbr[205:250, 130:170] += 0.30

    aoi = gpd.GeoDataFrame(geometry=[caja(0, 0, n, n).difference(caja(200, 180, n, n))], crs=CRS)
    zf = gpd.GeoDataFrame({"CLAVE": ["BP", "VSA/BQ", "SBC", "BC"]},
                          geometry=[caja(0, 0, 100, n), caja(100, 0, 190, 200), caja(195, 30, 290, 130),
                                    caja(100, 200, 190, n)], crs=CRS)
    claves = sorted(zf["CLAVE"])
    zf["_clave"] = zf["CLAVE"].map({c: i for i, c in enumerate(claves, start=1)}).astype("int16")
    # La segunda reforestación queda en parte fuera de la zona forestal (clave 0)
    refo = gpd.GeoDataFrame(geometry=[caja(200, 40, 280, 120), caja(150, 260, 200, 290)], crs=CRS)
    # Zonas no forestales que entrenan el clasificador de destino
    etq = gpd.GeoDataFrame({"CLAVE": ["TA", "H2O", "AH", "PI", "RA"]},
                           geometry=[caja(190, 0, n, 30), caja(190, 30, 195, 130), caja(290, 30, n, 130),
                                     caja(190, 130, n, 220), caja(190, 220, n, n)], crs=CRS)
    etq["_destino"] = [clase_destino(c) for c in etq["CLAVE"]]
    assert etq["_destino"].tolist() == [1, 4, 3, 2, 1]
    lab = rasterizar(etq.geometry, etq["_destino"].tolist(), (n, n), gb.affine, dtype="uint8")
    centros = rng.uniform(0, 1, (5, len(RASGOS)))  # 0 = bosque, 1..4 = destinos
    rasgos = (centros[lab] + rng.normal(0, 0.15, (n, n, len(RASGOS)))).astype("float32")
    rasgos[200:240, 120:140] = centros[1] + rng.normal(0, 0.15, (40, 20, len(RASGOS)))  # tala hacia cultivo
    rasgos[200:240, 140:160] = centros[3] + rng.normal(0, 0.15, (40, 20, len(RASGOS)))  # y hacia urbano
    rasgos[200:203, 120:160] = np.nan                                                  # sin dato
    rasgos[::11, ::13, 2] = np.nan                                                     # muestras sin dato
    muestreo = Muestreo(paso=7, max_por_grupo=40, region_m=1000, celda_prueba_m=300, arboles=30)
    # "Esquina" toca la zona solo con una astilla: no tiene píxeles dentro, pero sí fila (en ceros).
    # "Rincón" solo tiene píxeles en un bloque que se salta: también lleva su fila en ceros.
    uni = gpd.GeoDataFrame({"nombre": ["Norte", "Sur", "Esquina", "Rincón"]},
                           geometry=[caja(0, 0, n, 150), caja(0, 150, n, n), caja(199.8, 179.8, n, n),
                                     caja(275, 275, n, n)], crs=CRS)
    nombres = uni["nombre"].tolist()
    sin_imagenes = caja(150, 10, 160, 20)
    incendios = [("A", pd.Timestamp("2024-03-01"), caja(20, 20, 100, 90)),     # cruza varios bloques
                 ("B", pd.Timestamp("2024-03-20"), caja(90, 60, 130, 110)),    # se encima con A
                 ("C", pd.Timestamp("2024-04-02"), caja(185, 165, 225, 200)),  # sale de la zona
                 ("D", pd.Timestamp("2024-04-10"), sin_imagenes),             # sin imágenes
                 ("E", pd.Timestamp("2024-05-05"), caja(130, 205, 170, 250))]  # sobre la tala

    def leer_dnbr(geom, fecha):
        w = None if geom.equals(sin_imagenes) else ventana_incendio(gb, geom)
        if w is None:
            return None
        r0, r1, c0, c1 = w
        return (slice(r0, r1), slice(c0, c1)), dnbr[r0:r1, c0:c1].copy()

    def leer_ndvi(anio, b):
        return ndvi[anio][b.r0:b.r1, b.c0:b.c1].copy(), 1

    def leer_rasgos(b, filas, cols):
        return rasgos[b.r0 + filas, b.c0 + cols].copy()

    def referencia(umbral):
        """El cálculo original de `correr`, sobre arreglos completos."""
        dentro = rasterizar(aoi.geometry, [1], (n, n), gb.affine, dtype="uint8").astype(bool)
        en_refo = rasterizar(refo.geometry, [1] * len(refo), (n, n), gb.affine, dtype="uint8").astype(bool)
        zona = dentro & (rasterizar(zf.geometry, [1] * len(zf), (n, n), gb.affine, dtype="uint8").astype(bool)
                         | en_refo)
        if umbral == "auto":
            umbral = umbral_otsu(ndvi[2023][dentro])
        b, a = mascaras_con_margen(ndvi[2023], ndvi[2024], umbral, 0.10, zona)
        quemado, filas = np.zeros((n, n), dtype=bool), []
        for clave, fecha, geom in incendios:
            res = leer_dnbr(geom, fecha)
            if res is None:
                continue
            (rs, cs), d = res
            poly = rasterizar([geom], [1], d.shape, gb[rs, cs].affine, dtype="uint8").astype(bool)
            q = poly & (np.nan_to_num(d, nan=0) >= UMBRAL_DNBR)
            quemado[rs, cs] |= q
            filas.append({"incendio": clave, "fecha_inicio": f"{fecha:%Y-%m-%d}",
                          "poligono_ha": round(poly.sum() * HA_PIXEL, 2),
                          "quemado_dnbr_ha": round(q.sum() * HA_PIXEL, 2),
                          "quemado_en_bosque_ha": round((q & b[rs, cs]).sum() * HA_PIXEL, 2),
                          "perdido_al_cierre_ha": round((q & b[rs, cs] & ~a[rs, cs]).sum() * HA_PIXEL, 2),
                          "dnbr_mediana": round(float(np.nanmedian(np.where(poly, d, np.nan))), 3)})
        r_uni = rasterizar(uni.geometry, range(1, len(uni) + 1), (n, n), gb.affine)
        cambio = mapa_cambio(b, a, quemado)
        bal = balance(b, a, quemado, en_refo, r_uni, nombres)

        # Por clave y tipo de bosque, contando unidad por unidad y clave por clave
        r_clave = rasterizar(zf.geometry, zf["_clave"].tolist(), (n, n), gb.affine, dtype="int16")
        r_clave[~zona] = 0
        k = len(claves)
        cveg = np.zeros(((len(nombres) + 1) * (k + 1), len(COLUMNAS_VEG)), dtype=np.int64)
        for i in range(1, len(nombres) + 1):
            for kk in range(k + 1):
                m = (r_uni == i) & (r_clave == kk) & zona
                cveg[i * (k + 1) + kk] = [m.sum(), (m & b).sum(), (m & (cambio == PERD_INCENDIO)).sum(),
                                          (m & (cambio == PERD_OTRA)).sum(), (m & (cambio == GANANCIA)).sum(),
                                          (m & a).sum()]
        veg, tipos = tablas_vegetacion(cveg, nombres, claves)

        # Destino: muestras en la retícula de toda la malla, un modelo, predicción de cada pérdida
        rr = np.arange(muestreo.paso // 2, n, muestreo.paso)
        mf, mc = (x.ravel() for x in np.meshgrid(rr, rr, indexing="ij"))
        ok = dentro[mf, mc] & ~zona[mf, mc] & (lab[mf, mc] > 0)
        mf, mc = mf[ok], mc[ok]
        modelo, exactitud, _ = entrenar_destino(mf, mc, lab[mf, mc], rasgos[mf, mc], gb.affine, muestreo)
        pf, pc = np.nonzero(cambio == PERD_OTRA)
        pred = predecir_destino(modelo, rasgos[pf, pc])
        destino_r = np.zeros((n, n), dtype=np.uint8)
        destino_r[pf, pc] = pred
        cdest = np.zeros((len(nombres) + 1, len(DESTINOS) + 1), dtype=np.int64)
        np.add.at(cdest, (r_uni[pf, pc], pred), 1)
        destino = tabla_destino(cdest, nombres, np.bincount(r_uni.ravel(), minlength=len(nombres) + 1) > 0)

        # Los desgloses cuadran con el balance
        suma = veg.groupby("unidad")[COLUMNAS_VEG[1:]].sum().reindex(bal["unidad"]).fillna(0)
        assert np.allclose(suma.to_numpy(), bal.set_index("unidad")[COLUMNAS_VEG[1:]].to_numpy()), \
            "El desglose por clave no cuadra con el balance"
        assert np.allclose(destino["otras_perdidas_ha"], bal["otras_perdidas_ha"]), \
            "El destino no cuadra con las otras pérdidas"
        assert set(destino_r[pf, pc]) >= {1, 3, SIN_DATO_DESTINO}, "El demo debe tener destinos variados"
        return {"balance": bal, "incendios": pd.DataFrame(filas), "cambio": cambio, "umbral": umbral,
                "vegetacion": veg, "tipos": tipos, "destino": destino, "exactitud": exactitud,
                "destino_r": destino_r}

    # Bloques alineados a tres "teselas" con mallas desfasadas (en cuadros de 1 km)
    origenes = [(x0 - 20, y0 + 20, "T1"), (x0 + 960, y0, "T2"), (x0 + 1980, y0 - 980, "T3")]
    bloques = bloques_alineados(gb, origenes, tam, lado=1000)
    cobertura = np.zeros((n, n), dtype=int)
    for b in bloques:
        cobertura[b.ventana] += 1
    assert (cobertura == 1).all(), "Los bloques se enciman o dejan huecos"
    capas = CapasVector(aoi, zf, refo, uni, etq)
    dentro = {b: capas.dentro(b.geobox(gb)) for b in bloques}
    saltados = [b for b in bloques if not dentro[b].any()]
    rincon = rasterizar([caja(275, 275, n, n)], [1], (n, n), gb.affine, dtype="uint8").astype(bool)
    assert saltados and rincon.any() and not any(rincon[b.ventana].any() for b in bloques if dentro[b].any()), \
        "El demo debe tener bloques fuera de la zona, y el Rincón solo en ellos"
    # Otsu por bloques: el histograma sumado por pedazos es idéntico al de todos los valores juntos
    dentro_total = rasterizar(aoi.geometry, [1], (n, n), gb.affine, dtype="uint8").astype(bool)
    h1, e1 = histograma_ndvi(ndvi[2023][dentro_total])
    h2, e2 = histograma_ndvi([ndvi[2023][b.ventana][dentro[b]] for b in bloques if dentro[b].any()])
    assert np.array_equal(h1, h2) and np.array_equal(e1, e2), "El histograma de Otsu por bloques no coincide"
    saltados = len(saltados)
    cruzan = sum(sum(_cruce(ventana_incendio(gb, g), b) is not None for b in bloques) > 1
                 for _, _, g in incendios if not g.equals(sin_imagenes))

    class Corte(Exception):
        pass

    def cortar_tras(funcion, llamadas):
        cuenta = [0]

        def envuelta(*args):
            cuenta[0] += 1
            if cuenta[0] > llamadas:
                raise Corte()
            return funcion(*args)
        return envuelta

    with tempfile.TemporaryDirectory() as tmp:
        def calcular(nombre, bloques_, umbral, ndvi_=leer_ndvi, dnbr_=leer_dnbr, hilos=1):
            salida = Path(tmp) / nombre
            res = calcular_por_bloques(gb, bloques_, capas, ndvi_, dnbr_, incendios, nombres,
                                       anio_base=2023, anio=2024, umbral=umbral, margen=0.10,
                                       umbral_dnbr=UMBRAL_DNBR, salida=salida,
                                       firma={"demo": umbral}, hilos=hilos, log=lambda *x: None,
                                       claves=claves, leer_rasgos=leer_rasgos, muestreo=muestreo)
            res.progreso.borrar()
            with rasterio.open(salida / "cambio_2023_2024.tif") as src, \
                    rasterio.open(salida / "destino_2023_2024.tif") as src_d:
                return res, src.read(1), src_d.read(1)

        def igual(nombre, umbral, res, cambio, destino_r):
            ref = referencia(umbral)
            assert res.umbral == ref["umbral"], f"{nombre}: umbral distinto"
            for campo in ("balance", "incendios", "vegetacion", "tipos", "destino", "exactitud"):
                pd.testing.assert_frame_equal(getattr(res, campo), ref[campo], check_exact=True,
                                              obj=f"{nombre}: {campo}")
            assert np.array_equal(cambio, ref["cambio"]), f"{nombre}: el ráster de cambio no coincide"
            assert np.array_equal(destino_r, ref["destino_r"]), f"{nombre}: el ráster de destino no coincide"
            assert res.incendios["incendio"].is_unique, f"{nombre}: incendio contado dos veces"

        for umbral in (0.55, "auto"):
            igual("una sola vez", umbral, *calcular(f"una_{umbral}", [Bloque(0, n, 0, n)], umbral))
            igual("por bloques", umbral, *calcular(f"bloques_{umbral}", bloques, umbral))
            igual("por bloques, incendios en paralelo", umbral,
                  *calcular(f"hilos_{umbral}", bloques, umbral, hilos=3))

        # Corridas interrumpidas (en los incendios y a media corrida) y luego reanudadas. Con
        # "auto" se lee primero el año base de todos los bloques y luego el actual de cada uno.
        en_zona = len(bloques) - saltados
        for umbral, nombre, cortes, hilos in [
                (0.55, "corte_inc", {"dnbr_": cortar_tras(leer_dnbr, 2)}, 1),
                (0.55, "corte_inc_hilos", {"dnbr_": cortar_tras(leer_dnbr, 2)}, 3),
                (0.55, "corte_bloques", {"ndvi_": cortar_tras(leer_ndvi, 15)}, 1),
                ("auto", "corte_auto", {"ndvi_": cortar_tras(leer_ndvi, en_zona + 3)}, 1)]:
            try:
                calcular(nombre, bloques, umbral, hilos=hilos, **cortes)
                raise AssertionError(f"{nombre}: la corrida no se interrumpió")
            except Corte:
                pass
            assert (Path(tmp) / nombre / "progreso_2023_2024").exists()
            igual(f"{nombre} reanudada", umbral, *calcular(nombre, bloques, umbral, hilos=hilos))
            assert not (Path(tmp) / nombre / "progreso_2023_2024").exists()

    print(f"Por bloques = de una sola vez: {len(bloques)} bloques ({saltados} fuera de la zona, "
          f"saltados), {len(incendios)} incendios ({cruzan} cruzan bloques), umbral fijo y automático, "
          "incendios uno por uno y en paralelo, corridas interrumpidas y reanudadas: mismo balance, "
          "mismo ráster de cambio, una fila por incendio, mismo desglose por clave y tipo de bosque, "
          "mismo clasificador y mismo destino de las otras pérdidas")


def cmd_demo(a):
    """Datos inventados para comprobar que el balance cuadra. No descarga nada."""
    import geopandas as gpd
    from rasterio.transform import from_origin
    from shapely.geometry import box

    rng = np.random.default_rng(7)
    n = 300  # 300 x 300 píxeles de 10 m = 3 x 3 km
    tr = from_origin(450_000, 2_150_000, RES, RES)

    def caja(c0, r0, c1, r1):  # en filas/columnas -> polígono en metros
        return box(450_000 + c0 * RES, 2_150_000 - r1 * RES, 450_000 + c1 * RES, 2_150_000 - r0 * RES)

    ndvi_base = np.where(np.arange(n)[None, :] < 180, 0.78, 0.30) + rng.normal(0, 0.04, (n, n))
    ndvi_base = np.broadcast_to(ndvi_base, (n, n)).copy()
    ndvi_act = ndvi_base.copy()
    dnbr = rng.normal(0.02, 0.03, (n, n))

    incendio = caja(20, 20, 100, 90)       # 80 x 70 px en bosque = 56 ha
    tala = caja(120, 200, 160, 240)        # 40 x 40 px en bosque = 16 ha
    refo = caja(200, 40, 280, 120)         # 80 x 80 px fuera de bosque = 64 ha
    ndvi_act[20:90, 20:100] = 0.25 + rng.normal(0, 0.05, (70, 80))
    ndvi_act[20:40, 20:100] = 0.70          # franja quemada que conservó copa
    dnbr[20:90, 20:100] = 0.50
    ndvi_act[200:240, 120:160] = 0.28
    ndvi_act[40:80, 200:280] = 0.66         # mitad de la reforestación ya visible

    base, actual = mascaras_con_margen(ndvi_base, ndvi_act, 0.55, 0.10, np.ones((n, n), bool))
    quemado = rasterizar([incendio], [1], (n, n), tr, dtype="uint8").astype(bool) & (dnbr >= UMBRAL_DNBR)
    en_refo = rasterizar([refo], [1], (n, n), tr, dtype="uint8").astype(bool)

    unidades = gpd.GeoDataFrame({"municipio": ["Norte", "Sur"]},
                                geometry=[caja(0, 0, n, 150), caja(0, 150, n, n)], crs=CRS)
    r_uni = rasterizar(unidades.geometry, [1, 2], (n, n), tr)
    tabla = balance(base, actual, quemado, en_refo, r_uni, unidades["municipio"].tolist())

    refo_gdf = gpd.GeoDataFrame({"ANIO": [2024], "SOBREV": [72]}, geometry=[refo], crs=CRS)
    esp = recuperacion_esperada(refo_gdf, unidades, "municipio", "ANIO", "SOBREV", 2023, 2025, 0.7)
    tabla = tabla.merge(esp, on="unidad", how="left").fillna(0)
    print(tabla.to_string(index=False))

    # Comprobaciones
    calc = tabla.bosque_base_ha - tabla.perdida_incendio_ha - tabla.otras_perdidas_ha + tabla.ganancia_ha
    assert np.allclose(calc, tabla.bosque_actual_ha), "El balance no cuadra"
    tot = tabla.sum(numeric_only=True)
    print(f"\nBalance cuadra: {tot.bosque_base_ha:.2f} - {tot.perdida_incendio_ha:.2f} - "
          f"{tot.otras_perdidas_ha:.2f} + {tot.ganancia_ha:.2f} = {tot.bosque_actual_ha:.2f} ha")
    print(f"Recuperación esperada {tot.recuperacion_esperada_ha:.2f} ha vs observada "
          f"{tot.ganancia_en_reforestacion_ha:.2f} ha")

    vals = np.concatenate([rng.normal(0.75, 0.06, 60), rng.normal(0.35, 0.10, 60)])
    clases = np.r_[np.ones(60), np.zeros(60)]
    u, t = calibrar_umbral(vals, clases)
    print(f"Calibración con 120 puntos simulados: umbral {u:.2f}, "
          f"exactitud balanceada {t.exactitud_balanceada.max():.1%}")

    comprobar_bloques()

    if a.salida:
        out = Path(a.salida)
        out.mkdir(parents=True, exist_ok=True)
        tabla.to_csv(out / "balance_demo.csv", index=False)
        guardar_tif(out / "cambio_demo.tif", mapa_cambio(base, actual, quemado), tr)
        print(f"Archivos de prueba en {out.resolve()}")


def _mes_dia(texto):
    """Valida una fecha MM-DD para --ventana."""
    try:
        pd.Timestamp(f"2001-{texto}")
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{texto}' no es una fecha MM-DD válida")
    return texto


def main():
    p = argparse.ArgumentParser(description="Prototipo de la Calculadora de masa forestal (PROBOSQUE)")
    sp = p.add_subparsers(dest="cmd", required=True)

    def lectura(sub):
        sub.add_argument("--nubes-max", type=float, default=NUBES_MAX,
                         help=f"%% máximo de nubes por escena (eo:cloud_cover); por defecto {NUBES_MAX}. "
                              "En correr se aplica también a las escenas del dNBR")
        sub.add_argument("--escenas-max", type=int, default=None,
                         help="máximo de escenas por tesela para cada compuesto anual (las menos "
                              "nubladas); por defecto todas")
        sub.add_argument("--ventana", nargs=2, metavar=("INICIO", "FIN"), type=_mes_dia,
                         default=list(VENTANA_COBERTURA),
                         help="días del año del compuesto, MM-DD MM-DD (por defecto 11-01 12-31). Las dos "
                              "fechas de un balance deben usar la misma ventana; otra temporada da otras "
                              "hectáreas, que no se comparan con las de nov-dic")

    d = sp.add_parser("demo", help="probar la lógica con datos inventados")
    d.add_argument("--salida", default=None)

    c = sp.add_parser("calibrar", help="elegir el umbral de NDVI con puntos de referencia")
    c.add_argument("--aoi", required=True)
    c.add_argument("--anio", type=int, required=True)
    c.add_argument("--puntos", required=True)
    c.add_argument("--salida", default="resultados")
    lectura(c)

    r = sp.add_parser("correr", help="calcular el balance de masa forestal")
    r.add_argument("--aoi", required=True)
    r.add_argument("--anio-base", type=int, required=True)
    r.add_argument("--anio", type=int, required=True)
    r.add_argument("--umbral-ndvi", required=True,
                   help="número (p. ej. 0.55) o 'auto' para el umbral de Otsu provisional")
    r.add_argument("--umbral-dnbr", type=float, default=UMBRAL_DNBR)
    r.add_argument("--margen-cambio", type=float, default=0.10,
                   help="cambio mínimo de NDVI para contar pérdida o ganancia")
    r.add_argument("--zona-forestal", help="polígonos de uso de suelo (p. ej. INEGI Serie VII)")
    r.add_argument("--campo-clase", default="CLAVE")
    r.add_argument("--clases-forestales", default=CLASES_FORESTALES,
                   help="expresión regular de las claves que cuentan como zona forestal; por defecto "
                        f"{CLASES_FORESTALES.replace('%', '%%')}: bosques, selva baja caducifolia, matorrales "
                        "y vegetación secundaria arbórea (512,577 ha en el Estado de México). Hasta el "
                        "3-nov-2026 era ^(B|VSA/) (484,695 ha)")
    r.add_argument("--clasificar-destino", action=argparse.BooleanOptionalAction, default=None,
                   help="clasificar en agrícola, pecuario, urbano u otro el terreno de las otras pérdidas "
                        "(CF-DEV-07); por defecto sí cuando hay --zona-forestal. Lee 6 bandas más del año "
                        "actual")
    r.add_argument("--clases-agricola", default=CLASES_AGRICOLA,
                   help=f"claves no forestales que entrenan 'agrícola'; por defecto {CLASES_AGRICOLA}")
    r.add_argument("--clases-pecuario", default=CLASES_PECUARIO,
                   help=f"claves que entrenan 'pecuario'; por defecto {CLASES_PECUARIO}")
    r.add_argument("--clases-urbano", default=CLASES_URBANO,
                   help=f"claves que entrenan 'urbano'; por defecto {CLASES_URBANO}. Las demás no "
                        "forestales entrenan 'otro'")
    r.add_argument("--incendios")
    r.add_argument("--campo-fecha", default="FECHAINIC")
    r.add_argument("--campo-id", default="CLAVEINC", help="campo que identifica cada incendio")
    r.add_argument("--reforestacion")
    r.add_argument("--campo-anio", default="ANIO")
    r.add_argument("--campo-sobrev", default=None)
    r.add_argument("--sobrev-default", type=float, default=0.7,
                   help="sobrevivencia supuesta si el polígono no la trae (0-1)")
    r.add_argument("--unidades")
    r.add_argument("--campo-unidad", default="NOMGEO")
    r.add_argument("--salida", default="resultados")
    lectura(r)
    r.add_argument("--bloques", action="store_true",
                   help="procesar por bloques en memoria (para zonas grandes, como todo el estado)")
    r.add_argument("--tam-bloque", type=int, default=2 * BLOQUE_COG,
                   help=f"lado del bloque en píxeles de 10 m, múltiplo de {BLOQUE_COG}; por defecto "
                        f"{2 * BLOQUE_COG} (20.48 km)")
    r.add_argument("--guardar-indices", action=argparse.BooleanOptionalAction, default=None,
                   help="guardar los rásters de NDVI y dNBR (float32, ~1.5 GB cada uno para el estado); "
                        "por defecto sí de una sola vez y no con --bloques")
    r.add_argument("--hilos-incendios", type=int, default=HILOS_INCENDIOS,
                   help=f"incendios cuyo dNBR se lee a la vez; por defecto {HILOS_INCENDIOS}. No cambia "
                        "el resultado; 1 = uno por uno")
    r.add_argument("--reiniciar", action="store_true",
                   help="descartar el avance de una corrida interrumpida y empezar de nuevo")

    a = p.parse_args()
    {"demo": cmd_demo, "calibrar": cmd_calibrar, "correr": cmd_correr}[a.cmd](a)


if __name__ == "__main__":
    main()
