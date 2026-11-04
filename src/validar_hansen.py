#!/usr/bin/env python3
"""
Validación de la pérdida de bosque del prototipo contra Hansen Global Forest Change
===================================================================================

Parte de CF-DEV-09 ("validación del cálculo") que se puede hacer con fuentes públicas.
Compara el ráster de cambio de `prototipo_masa_forestal.py correr` (10 m, EPSG:32614) con la
capa `lossyear` de Hansen GFC (30 m, EPSG:4326) dentro de la zona forestal de la Serie VII.

**Hansen no es la verdad de campo.** Es otro mapa hecho con satélite (Landsat), con su propia
definición: pérdida = "stand-replacement disturbance", la remoción de la copa de árboles de más
de 5 m. Sirve para ver si las dos fuentes coinciden y dónde no; quién tiene razón en cada
desacuerdo solo lo dicen la fotointerpretación y las visitas de campo.

Qué hace:

1. Recorta del estado las capas `lossyear` y `treecover2000` de la versión de Hansen pedida,
   leyendo por ventanas con /vsicurl (no baja las teselas completas, que pesan hasta 344 MB).
   Guarda los recortes en `datos/edomex/hansen/` (22 MB) y los reutiliza en otras corridas.
2. Lleva Hansen a la malla de 10 m del prototipo por vecino más cercano: cada píxel de 10 m toma
   el valor del píxel de Hansen que contiene su centro. Así las hectáreas del prototipo quedan
   exactamente como en su balance y la superficie de Hansen se conserva en promedio (se revisa
   contra el conteo en su malla original).
3. Por municipio y para el estado cuenta: pérdida del prototipo (clases 2 y 3), pérdida de Hansen
   en los años pedidos, coincidencia (ambos, solo prototipo, solo Hansen), precisión y
   exhaustividad con Hansen como referencia, las mismas con una tolerancia de posición (30 m),
   y cuánta pérdida del prototipo Hansen pone un año antes o un año después.
4. Escribe en `--salida`: `validacion_municipios.csv`, `validacion_estatal.csv`,
   `coincidencia_<periodo>.tif` (uint8, para QGIS), `mapa_coincidencia.png` y `corrida.json`.

Uso (desde la raíz del repositorio; ~2 min, lee ~100 MB de internet la primera vez):
    python src/validar_hansen.py
    python src/validar_hansen.py --comparacion resultados/edomex_2023_2025/cambio_2023_2025.tif 2024,2025
    python src/validar_hansen.py --solo-mapa

Fuente: Hansen/UMD/Google/USGS/NASA (CC BY 4.0). Cita en el LEEME de la salida.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

VERSION = "GFC-2025-v1.13"
URL = "https://storage.googleapis.com/earthenginepartners-hansen/{v}/Hansen_{v}_{capa}_{tesela}.tif"
RES = 0.00025          # 1 segundo de arco
LADO_TESELA = 10       # grados
PX_TESELA = 40000

# Clases del ráster de cambio del prototipo
SIN_BOSQUE, ESTABLE, PERD_INCENDIO, PERD_OTRA, GANANCIA = 0, 1, 2, 3, 4
# Clases del ráster de coincidencia
FUERA, ZONA, AMBOS, SOLO_PROTO, SOLO_HANSEN = 0, 1, 2, 3, 4

# Las comparaciones de un año de la serie estatal (desde 0.7.0; antes, las corridas directas)
PREDETERMINADAS = [("resultados/edomex_serie_2023_2025/cambio_2023_2024.tif", "2024"),
                   ("resultados/edomex_serie_2023_2025/cambio_2024_2025.tif", "2025")]

# Colores (skill dataviz: primeros tres tonos categóricos, validados en todos los pares)
SUPERFICIE = "#fcfcfb"
TINTA, TINTA_2, TINTA_TENUE = "#0b0b0b", "#52514e", "#898781"
FONDO_ZONA, BORDE = "#e1e0d9", "#c3c2b7"
COLOR = {AMBOS: "#2a78d6", SOLO_PROTO: "#eb6834", SOLO_HANSEN: "#1baf7a"}
NOMBRE = {AMBOS: "Ambos", SOLO_PROTO: "Solo prototipo", SOLO_HANSEN: "Solo Hansen"}


def log(*a):
    print(f"[{datetime.now():%H:%M:%S}]", *a, flush=True)


# --------------------------------------------------------------------------
# 1. Recorte de Hansen por ventanas
# --------------------------------------------------------------------------
def nombre_tesela(lat_sup: int, lon_izq: int) -> str:
    """Las teselas se nombran por su esquina superior izquierda: 20N_100W = lat 10–20, lon −100 a −90."""
    return (f"{abs(lat_sup):02d}{'N' if lat_sup >= 0 else 'S'}_"
            f"{abs(lon_izq):03d}{'E' if lon_izq >= 0 else 'W'}")


def malla_recorte(limites, margen=0.005):
    """Índices globales (col0, fila0, col1, fila1) de la malla de Hansen que cubren los límites.
    Los bordes de píxel de Hansen caen en múltiplos de 0.00025° en todo el mundo."""
    minx, miny, maxx, maxy = limites
    c0 = math.floor((minx - margen + 180) / RES)
    c1 = math.ceil((maxx + margen + 180) / RES)
    f0 = math.floor((90 - (maxy + margen)) / RES)
    f1 = math.ceil((90 - (miny - margen)) / RES)
    return c0, f0, c1, f1


def teselas_de(c0, f0, c1, f1):
    t = []
    for tf in range(f0 // PX_TESELA, (f1 - 1) // PX_TESELA + 1):
        for tc in range(c0 // PX_TESELA, (c1 - 1) // PX_TESELA + 1):
            t.append((tf, tc, nombre_tesela(90 - tf * LADO_TESELA, tc * LADO_TESELA - 180)))
    return t


def configurar_gdal():
    os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                      GDAL_HTTP_CONNECTTIMEOUT="30", GDAL_HTTP_LOW_SPEED_TIME="60",
                      GDAL_HTTP_LOW_SPEED_LIMIT="1", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="3",
                      GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES")


def recortar_hansen(version, capa, limites, carpeta: Path, volver=False) -> Path:
    """Recorte de una capa de Hansen (EPSG:4326, 1") que cubre `limites` (lon/lat)."""
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.windows import Window

    ruta = carpeta / f"Hansen_{version}_{capa}_edomex.tif"
    if ruta.exists() and not volver:
        log(f"Recorte ya guardado: {ruta} ({ruta.stat().st_size / 2**20:.1f} MB)")
        return ruta
    c0, f0, c1, f1 = malla_recorte(limites)
    mosaico = np.zeros((f1 - f0, c1 - c0), dtype=np.uint8)
    t = time.time()
    for tf, tc, nombre in teselas_de(c0, f0, c1, f1):
        url = URL.format(v=version, capa=capa, tesela=nombre)
        # Parte del recorte que cae en esta tesela, en coordenadas de la tesela
        a0, a1 = max(c0, tc * PX_TESELA), min(c1, (tc + 1) * PX_TESELA)
        b0, b1 = max(f0, tf * PX_TESELA), min(f1, (tf + 1) * PX_TESELA)
        ventana = Window(a0 - tc * PX_TESELA, b0 - tf * PX_TESELA, a1 - a0, b1 - b0)
        t1 = time.time()
        with rasterio.open(f"/vsicurl/{url}") as src:
            if src.width != PX_TESELA or abs(src.transform.a - RES) > 1e-12:
                sys.exit(f"{url}: malla inesperada {src.width} px, {src.transform.a}°")
            mosaico[b0 - f0:b1 - f0, a0 - c0:a1 - c0] = src.read(1, window=ventana)
        log(f"  {capa} {nombre}: {ventana.height:,} × {ventana.width:,} px en {time.time() - t1:.0f} s")
    carpeta.mkdir(parents=True, exist_ok=True)
    perfil = dict(driver="GTiff", height=mosaico.shape[0], width=mosaico.shape[1], count=1, dtype="uint8",
                  crs="EPSG:4326", transform=from_origin(c0 * RES - 180, 90 - f0 * RES, RES, RES),
                  compress="deflate", predictor=2, tiled=True, blockxsize=512, blockysize=512)
    with rasterio.open(ruta, "w", **perfil) as dst:
        dst.write(mosaico, 1)
    log(f"Recorte {capa}: {mosaico.shape[0]:,} × {mosaico.shape[1]:,} px, {time.time() - t:.0f} s, "
        f"{ruta.stat().st_size / 2**20:.1f} MB en disco")
    return ruta


# --------------------------------------------------------------------------
# 2. Comparación en la malla de 10 m
# --------------------------------------------------------------------------
def dilatar(m: np.ndarray, r: int) -> np.ndarray:
    """Dilatación cuadrada de radio r píxeles (cualquier píxel a ≤ r en filas y columnas)."""
    if r <= 0:
        return m
    out = m.copy()
    for k in range(1, r + 1):
        out[k:] |= m[:-k]
        out[:-k] |= m[k:]
    filas = out.copy()
    for k in range(1, r + 1):
        out[:, k:] |= filas[:, :-k]
        out[:, :-k] |= filas[:, k:]
    return out


def rasterizar(gdf, shape, transform, numerar=False):
    from rasterio.features import rasterize
    from rasterio.transform import array_bounds
    from shapely.geometry import box
    idx = np.sort(gdf.sindex.query(box(*array_bounds(*shape, transform))))  # (oeste, sur, este, norte)
    dtype = "int32" if numerar else "uint8"
    if not len(idx):
        return np.zeros(shape, dtype=dtype)
    vals = (idx + 1).tolist() if numerar else [1] * len(idx)
    return rasterize(zip(gdf.geometry.iloc[idx], vals), out_shape=shape, transform=transform,
                     fill=0, dtype=dtype)


CONTEOS = [  # nombre de la columna en hectáreas
    "zona_forestal_ha", "bosque_base_proto_ha",
    "proto_perdida_ha", "proto_perdida_incendio_ha", "proto_otra_perdida_ha",
    "hansen_perdida_ha", "hansen_en_bosque_proto_ha", "hansen_perdida_tc_ha", "hansen_sin_zona_ha",
    "ambos_ha", "ambos_incendio_ha", "ambos_otra_ha",
    "proto_cerca_hansen_ha", "hansen_cerca_proto_ha",
    "proto_hansen_anio_ant_ha", "proto_hansen_anio_sig_ha", "proto_fuera_zona_ha",
]


def comparar(a, comparaciones, limites_ll):
    import geopandas as gpd
    import rasterio
    from rasterio.warp import reproject, Resampling
    from rasterio.windows import Window

    carpeta = Path(a.recortes)
    rutas = {c: recortar_hansen(a.version, c, limites_ll, carpeta, a.volver_a_bajar)
             for c in ("lossyear", "treecover2000")}
    fuente = {}
    for c, r in rutas.items():
        with rasterio.open(r) as s:
            fuente[c] = (s.read(1), s.transform)

    srcs = [rasterio.open(c["ruta"]) for c in comparaciones]
    ref = srcs[0]
    for s in srcs[1:]:
        if s.shape != ref.shape or s.transform != ref.transform or s.crs != ref.crs:
            sys.exit(f"{s.name} no tiene la misma malla que {ref.name}")
    crs, alto, ancho = ref.crs, ref.height, ref.width
    log(f"Malla del prototipo: {alto:,} × {ancho:,} px de 10 m ({crs.to_string()})")

    aoi = gpd.read_file(a.aoi).to_crs(crs)
    zf = gpd.read_file(a.zona_forestal).to_crs(crs)
    import warnings
    with warnings.catch_warnings():  # "has match groups": solo se usa para filtrar
        warnings.simplefilter("ignore", UserWarning)
        es = zf[a.campo_clase].astype(str).str.contains(a.clases_forestales, regex=True)
    zf = zf[es].reset_index(drop=True)
    uni = gpd.read_file(a.unidades).to_crs(crs)
    uni = uni[uni.intersects(aoi.union_all())].reset_index(drop=True)  # mismo orden que el prototipo
    nombres = uni[a.campo_unidad].astype(str).tolist()
    n = len(uni)
    log(f"Zona forestal: {len(zf):,} polígonos ({a.clases_forestales}); {n} unidades")

    halo = math.ceil(a.tolerancia_m / abs(ref.transform.a))
    ha_px = abs(ref.transform.a * ref.transform.e) / 1e4
    conteos = [{k: np.zeros(n + 1, dtype=np.int64) for k in CONTEOS} for _ in comparaciones]
    salidas = []
    out = Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)
    for c in comparaciones:
        perfil = ref.profile.copy()
        perfil.update(dtype="uint8", nodata=None, compress="deflate", tiled=True, blockxsize=512, blockysize=512)
        salidas.append(rasterio.open(out / f"coincidencia_{c['periodo']}.tif", "w", **perfil))

    t0 = time.time()
    paso = a.filas_bloque
    for r0 in range(0, alto, paso):
        r1 = min(r0 + paso, alto)
        e0, e1 = max(0, r0 - halo), min(alto, r1 + halo)
        ext = Window(0, e0, ancho, e1 - e0)
        tr = ref.window_transform(ext)
        forma = (e1 - e0, ancho)
        nucleo = slice(r0 - e0, r1 - e0)

        dentro = rasterizar(aoi, forma, tr).astype(bool)
        if not dentro.any():
            for s in salidas:
                s.write(np.zeros((r1 - r0, ancho), np.uint8), 1, window=Window(0, r0, ancho, r1 - r0))
            continue
        zona = dentro & rasterizar(zf, forma, tr).astype(bool)
        u = rasterizar(uni, (r1 - r0, ancho), ref.window_transform(Window(0, r0, ancho, r1 - r0)), numerar=True)
        u = np.where(dentro[nucleo], u, 0)  # unidad 0: fuera del estado o en huecos entre municipios

        capas = {}
        for nombre, (arr, src_tr) in fuente.items():
            dst = np.zeros(forma, dtype=np.uint8)
            reproject(arr, dst, src_transform=src_tr, src_crs="EPSG:4326", dst_transform=tr, dst_crs=crs,
                      resampling=Resampling.nearest, num_threads=4)
            capas[nombre] = dst
        ly, tc = capas["lossyear"], capas["treecover2000"]

        for i, (c, src) in enumerate(zip(comparaciones, srcs)):
            cam = src.read(1, window=ext)
            anios = c["anios_hansen"]
            P = (cam == PERD_INCENDIO) | (cam == PERD_OTRA)
            H_estado = dentro & np.isin(ly, anios)
            H = zona & np.isin(ly, anios)
            Hd, Pd = dilatar(H, halo), dilatar(P, halo)
            k = nucleo
            Pk, Hk, camk, zk = P[k], H[k], cam[k], zona[k]
            base = (camk == ESTABLE) | (camk == PERD_INCENDIO) | (camk == PERD_OTRA)
            ant, sig = min(anios) - 1, max(anios) + 1
            mascaras = {
                "zona_forestal_ha": zk & dentro[k],
                "bosque_base_proto_ha": base,
                "proto_perdida_ha": Pk,
                "proto_perdida_incendio_ha": camk == PERD_INCENDIO,
                "proto_otra_perdida_ha": camk == PERD_OTRA,
                "hansen_perdida_ha": Hk,
                "hansen_en_bosque_proto_ha": Hk & base,
                "hansen_perdida_tc_ha": Hk & (tc[k] >= a.cobertura_min),
                "hansen_sin_zona_ha": H_estado[k],
                "ambos_ha": Pk & Hk,
                "ambos_incendio_ha": (camk == PERD_INCENDIO) & Hk,
                "ambos_otra_ha": (camk == PERD_OTRA) & Hk,
                "proto_cerca_hansen_ha": Pk & Hd[k],
                "hansen_cerca_proto_ha": Hk & Pd[k],
                "proto_hansen_anio_ant_ha": Pk & (ly[k] == ant) if ant >= 1 else np.zeros_like(Pk),
                "proto_hansen_anio_sig_ha": Pk & (ly[k] == sig) if sig <= c["anio_max"] else np.zeros_like(Pk),
                "proto_fuera_zona_ha": (camk > 0) & ~zk,
            }
            for nombre, m in mascaras.items():
                conteos[i][nombre] += np.bincount(u[m], minlength=n + 1)
            coin = np.where(zk, ZONA, FUERA).astype(np.uint8)
            coin[Pk & Hk] = AMBOS
            coin[Pk & ~Hk] = SOLO_PROTO
            coin[Hk & ~Pk] = SOLO_HANSEN
            salidas[i].write(coin, 1, window=Window(0, r0, ancho, r1 - r0))
        log(f"  filas {r0:,}–{r1:,} de {alto:,} ({time.time() - t0:.0f} s)")
    for s in salidas + srcs:
        s.close()

    # Revisión del remuestreo: superficie de Hansen dentro del estado en su malla original
    revision = revisar_superficie(fuente["lossyear"], aoi.to_crs("EPSG:4326"), comparaciones)

    filas_m, filas_e = [], []
    for c, cnt in zip(comparaciones, conteos):
        ha = {k: v * ha_px for k, v in cnt.items()}
        tabla = pd.DataFrame({"periodo": c["periodo"], "anios_hansen": c["texto_anios"],
                              "unidad": ["(fuera de los municipios)"] + nombres, **ha})
        filas_m.append(metricas(tabla.iloc[1:]))
        tot = tabla.drop(columns=["periodo", "anios_hansen", "unidad"]).sum()
        estatal = pd.DataFrame([{"periodo": c["periodo"], "anios_hansen": c["texto_anios"],
                                 "unidad": "Estado de México", **tot.to_dict()}])
        estatal["hansen_sin_zona_malla_original_ha"] = revision[c["periodo"]]
        filas_e.append(metricas(estatal))
        fuera = tabla.iloc[0]
        if fuera["proto_perdida_ha"] or fuera["hansen_perdida_ha"]:
            log(f"  {c['periodo']}: fuera de los municipios quedan {fuera['proto_perdida_ha']:.2f} ha del "
                f"prototipo y {fuera['hansen_perdida_ha']:.2f} de Hansen (cuentan solo en el estatal)")
    municipios = pd.concat(filas_m, ignore_index=True)
    estatal = pd.concat(filas_e, ignore_index=True)
    for t in (municipios, estatal):  # hectáreas a 2 decimales, proporciones a 4
        for col in t.columns:
            if pd.api.types.is_float_dtype(t[col]):
                t[col] = t[col].round(2 if col.endswith("_ha") else 4)
    municipios.to_csv(out / "validacion_municipios.csv", index=False)
    estatal.to_csv(out / "validacion_estatal.csv", index=False)
    json.dump({"version_hansen": a.version, "fecha": datetime.now().isoformat(timespec="seconds"),
               "comparaciones": [{k: v for k, v in c.items()} for c in comparaciones],
               "zona_forestal": a.zona_forestal, "clases_forestales": a.clases_forestales,
               "tolerancia_m": a.tolerancia_m, "cobertura_min": a.cobertura_min,
               "recortes": {k: v.as_posix() for k, v in rutas.items()},
               "segundos_comparacion": round(time.time() - t0)},
              open(out / "corrida.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return municipios, estatal


def revisar_superficie(lossyear, aoi_ll, comparaciones):
    """Hectáreas de pérdida de Hansen dentro del estado contadas en la malla original (píxeles de
    1" con el área de su latitud, esfera de radio 6,371,007 m)."""
    from rasterio.features import rasterize
    arr, tr = lossyear
    dentro = rasterize(((g, 1) for g in aoi_ll.geometry), out_shape=arr.shape, transform=tr, dtype="uint8")
    lat = tr.f + tr.e * (np.arange(arr.shape[0]) + 0.5)
    r = 6371007.2
    area_fila = (r * math.radians(RES)) ** 2 * np.cos(np.radians(lat)) / 1e4  # ha
    res = {}
    for c in comparaciones:
        m = (dentro == 1) & np.isin(arr, c["anios_hansen"])
        res[c["periodo"]] = float((m.sum(axis=1) * area_fila).sum())
    return res


def metricas(t: pd.DataFrame) -> pd.DataFrame:
    t = t.copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        t["solo_proto_ha"] = t["proto_perdida_ha"] - t["ambos_ha"]
        t["solo_hansen_ha"] = t["hansen_perdida_ha"] - t["ambos_ha"]
        t["precision"] = t["ambos_ha"] / t["proto_perdida_ha"]
        t["exhaustividad"] = t["ambos_ha"] / t["hansen_perdida_ha"]
        t["f1"] = 2 * t["ambos_ha"] / (t["proto_perdida_ha"] + t["hansen_perdida_ha"])
        t["exhaustividad_en_bosque_proto"] = t["ambos_ha"] / t["hansen_en_bosque_proto_ha"]
        t["precision_incendio"] = t["ambos_incendio_ha"] / t["proto_perdida_incendio_ha"]
        t["precision_otra"] = t["ambos_otra_ha"] / t["proto_otra_perdida_ha"]
        t["precision_tol"] = t["proto_cerca_hansen_ha"] / t["proto_perdida_ha"]
        t["exhaustividad_tol"] = t["hansen_cerca_proto_ha"] / t["hansen_perdida_ha"]
    return t


# --------------------------------------------------------------------------
# 3. Mapa
# --------------------------------------------------------------------------
def leer_coincidencia(ruta, celda_px, min_px):
    """Ráster de coincidencia reducido a celdas de celda_px × celda_px, con la coincidencia a
    escala de celda: la celda es "ambos" si el prototipo y Hansen tienen cada uno al menos min_px
    píxeles de pérdida en ella, "solo prototipo" o "solo Hansen" si solo uno llega, y zona forestal
    (1) o fuera (0) si ninguno. Regresa también los píxeles "ambos" de cada celda, para elegir el
    acercamiento."""
    import rasterio
    from rasterio.windows import Window
    with rasterio.open(ruta) as src:
        alto, ancho, f = src.height, src.width, celda_px
        h, w = math.ceil(alto / f), math.ceil(ancho / f)
        sal = np.zeros((h, w), dtype=np.uint8)
        n_ambos = np.zeros((h, w), dtype=np.int32)
        paso = f * max(1, 2048 // f)
        for r0 in range(0, alto, paso):
            r1 = min(r0 + paso, alto)
            x = src.read(1, window=Window(0, r0, ancho, r1 - r0))
            filas = math.ceil((r1 - r0) / f)
            x = np.pad(x, ((0, filas * f - (r1 - r0)), (0, w * f - ancho))).reshape(filas, f, w, f)
            cuenta = {k: (x == k).sum(axis=(1, 3)) for k in (ZONA, AMBOS, SOLO_PROTO, SOLO_HANSEN)}
            proto = cuenta[AMBOS] + cuenta[SOLO_PROTO] >= min_px
            hansen = cuenta[AMBOS] + cuenta[SOLO_HANSEN] >= min_px
            cat = np.where(sum(cuenta.values()) > 0, ZONA, FUERA).astype(np.uint8)
            cat[proto & ~hansen] = SOLO_PROTO
            cat[hansen & ~proto] = SOLO_HANSEN
            cat[proto & hansen] = AMBOS
            sal[r0 // f:r0 // f + filas] = cat
            n_ambos[r0 // f:r0 // f + filas] = cuenta[AMBOS]
        b, t = src.bounds, src.transform
        limites = (b.left, b.top - h * f * abs(t.e), b.left + w * f * t.a, b.top)
        return sal, n_ambos, limites, src.crs


def elegir_acercamiento(n_ambos, limites, celda_m, lado_m):
    """Cuadro de lado_m con más píxeles de pérdida en ambos (suma por ventana deslizante)."""
    k = max(1, round(lado_m / celda_m))
    s = np.pad(n_ambos.astype(np.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    caja = s[k:, k:] - s[:-k, k:] - s[k:, :-k] + s[:-k, :-k]
    fila, col = np.unravel_index(caja.argmax(), caja.shape)
    izq, arriba = limites[0] + col * celda_m, limites[3] - fila * celda_m
    return izq, arriba - k * celda_m, izq + k * celda_m, arriba


def dibujar_mapa(a, estatal):
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    out = Path(a.salida)
    celda_px = round(a.celda_m / 10)
    min_px = max(1, round(a.min_ha_celda / 0.01))
    import rasterio
    from rasterio.windows import from_bounds
    from matplotlib.patches import Rectangle
    import matplotlib.patheffects as pe

    plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans"], "text.color": TINTA})
    k = len(estatal)
    fig, ejes = plt.subplots(2, k, figsize=(7.6 * k, 15.2), facecolor=SUPERFICIE, layout="constrained",
                             height_ratios=[1.15, 1], squeeze=False)
    cmap = ListedColormap([(0, 0, 0, 0), FONDO_ZONA, COLOR[AMBOS], COLOR[SOLO_PROTO], COLOR[SOLO_HANSEN]])
    lecturas = [leer_coincidencia(out / f"coincidencia_{f['periodo']}.tif", celda_px, min_px)
                for _, f in estatal.iterrows()]
    crs = lecturas[0][3]
    uni = gpd.read_file(a.unidades).to_crs(crs)
    aoi = gpd.read_file(a.aoi).to_crs(crs)
    uni = uni[uni.intersects(aoi.union_all())]
    # Mismo acercamiento en todas las columnas: donde más coinciden en el primer periodo
    zoom = elegir_acercamiento(lecturas[0][1], lecturas[0][2], a.celda_m, a.acercamiento_km * 1000)
    from shapely.geometry import box
    centro = box(*zoom).centroid
    donde = uni[uni.contains(centro)][a.campo_unidad].astype(str).tolist()
    donde = donde[0] if donde else "Estado de México"

    for j, ((_, fila), (cat, _, lim, _)) in enumerate(zip(estatal.iterrows(), lecturas)):
        b0, b1 = fila["periodo"].split("_")
        # --- Arriba: el estado a escala de celda
        ax = ejes[0, j]
        izq, abajo, der, arriba = lim
        ax.imshow(cat, cmap=cmap, vmin=0, vmax=4, interpolation="nearest",
                  extent=(izq, der, abajo, arriba), zorder=2)
        uni.boundary.plot(ax=ax, color=BORDE, linewidth=0.3, zorder=3)
        aoi.boundary.plot(ax=ax, color=TINTA_2, linewidth=0.8, zorder=3)
        ax.add_patch(Rectangle((zoom[0], zoom[1]), zoom[2] - zoom[0], zoom[3] - zoom[1], fill=False,
                               edgecolor=TINTA, linewidth=1.2, zorder=4))
        ax.set_xlim(izq, der)
        ax.set_ylim(abajo, arriba)
        ax.set_axis_off()
        ax.set_title(f"Prototipo {b0} → {b1}  contra  Hansen pérdida {fila['anios_hansen']}",
                     loc="left", fontsize=12, color=TINTA, pad=22)
        ax.text(0, 1.0, f"Precisión {fila['precision']:.0%} · exhaustividad {fila['exhaustividad']:.0%} "
                f"(con tolerancia de {a.tolerancia_m:g} m: {fila['precision_tol']:.0%} y "
                f"{fila['exhaustividad_tol']:.0%}).  Celdas de {a.celda_m:g} m.",
                transform=ax.transAxes, fontsize=9, color=TINTA_2, va="bottom")
        barra_escala(ax, lim)
        # --- Abajo: acercamiento a 10 m
        ax = ejes[1, j]
        with rasterio.open(out / f"coincidencia_{fila['periodo']}.tif") as src:
            x = src.read(1, window=from_bounds(*zoom, transform=src.transform).round_offsets().round_lengths())
        ax.imshow(x, cmap=cmap, vmin=0, vmax=4, interpolation="nearest",
                  extent=(zoom[0], zoom[2], zoom[1], zoom[3]), zorder=2)
        uni.boundary.plot(ax=ax, color=TINTA_TENUE, linewidth=0.6, zorder=3)
        ax.set_xlim(zoom[0], zoom[2])
        ax.set_ylim(zoom[1], zoom[3])
        ax.set_axis_off()
        for _, u in uni[uni.intersects(box(*zoom))].iterrows():
            pt = u.geometry.intersection(box(*zoom)).representative_point()
            ax.annotate(u[a.campo_unidad], (pt.x, pt.y), ha="center", va="center", fontsize=8,
                        color=TINTA_2, zorder=5, path_effects=[pe.withStroke(linewidth=2.5, foreground=SUPERFICIE)])
        ax.set_title(f"Acercamiento ({a.acercamiento_km:g} × {a.acercamiento_km:g} km, píxeles de 10 m) en "
                     f"{donde}", loc="left", fontsize=10, color=TINTA_2)
        barra_escala(ax, zoom)
        leyenda = [
            Patch(color=COLOR[AMBOS], label=f"Pérdida en ambos ({fila['ambos_ha']:,.0f} ha)"),
            Patch(color=COLOR[SOLO_PROTO], label=f"Solo en el prototipo ({fila['solo_proto_ha']:,.0f} ha)"),
            Patch(color=COLOR[SOLO_HANSEN], label=f"Solo en Hansen ({fila['solo_hansen_ha']:,.0f} ha)"),
            Patch(color=FONDO_ZONA, label="Zona forestal sin pérdida"),
        ]
        ax.legend(handles=leyenda, loc="upper left", bbox_to_anchor=(0, 0), ncol=2, fontsize=9.5,
                  frameon=False, labelcolor=TINTA)
    fig.suptitle("Pérdida de bosque: prototipo (Sentinel-2) contra Hansen Global Forest Change · "
                 "Estado de México", x=0.01, ha="left", fontsize=15, color=TINTA)
    fig.text(0.01, 0.962,
             "Dentro de la zona forestal INEGI Serie VII. Arriba, coincidencia por celda: una celda es "
             f"\"ambos\" si cada fuente tiene al menos {a.min_ha_celda:g} ha de pérdida en ella, así que "
             "las manchas se ven más grandes de lo que son. Abajo, coincidencia píxel a píxel; las hectáreas "
             "de la leyenda son las de los píxeles. Hansen es otro mapa satelital, no verdad de campo.  "
             f"Fuente: Hansen/UMD/Google/USGS/NASA ({a.version}, CC BY 4.0); contiene datos modificados "
             "de Copernicus Sentinel; INEGI.", fontsize=8.5, color=TINTA_2, wrap=True)
    fig.get_layout_engine().set(rect=(0, 0, 1, 0.95))
    ruta = out / "mapa_coincidencia.png"
    fig.savefig(ruta, dpi=150, facecolor=SUPERFICIE)
    log(f"Mapa en {ruta}")


def barra_escala(ax, limites):
    izq, abajo, der, arriba = limites
    objetivo = (der - izq) / 5
    n = 10 ** math.floor(math.log10(objetivo))
    largo = max(m * n for m in (1, 2, 5) if m * n <= objetivo)
    x0, y0 = izq + (der - izq) * 0.04, abajo + (arriba - abajo) * 0.04
    ax.plot([x0, x0 + largo], [y0, y0], color=TINTA, lw=2, solid_capstyle="butt", zorder=4)
    ax.text(x0 + largo / 2, y0 + (arriba - abajo) * 0.012, f"{largo / 1000:g} km", ha="center",
            va="bottom", fontsize=8, color=TINTA_2, zorder=4)


# --------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Compara la pérdida del prototipo con Hansen GFC")
    p.add_argument("--comparacion", nargs=2, action="append", metavar=("CAMBIO_TIF", "ANIOS"),
                   help="ráster de cambio del prototipo y año(s) de pérdida de Hansen (p. ej. 2024 o "
                        "2024,2025); se puede repetir. Por defecto 2023→2024 contra 2024 y 2024→2025 "
                        "contra 2025")
    p.add_argument("--version", default=VERSION, help="versión de Hansen GFC (p. ej. GFC-2025-v1.13)")
    p.add_argument("--aoi", default="datos/edomex/estado_mexico.gpkg")
    p.add_argument("--zona-forestal", default="datos/edomex/usv_serie7_edomex.gpkg")
    p.add_argument("--campo-clase", default="CLAVE")
    p.add_argument("--clases-forestales", default=r"^(B|S|M|VSA/)",
                   help="las mismas que usó la corrida del prototipo (desde 0.6.0, ^(B|S|M|VSA/); las corridas "
                        "directas anteriores usaban ^(B|VSA/))")
    p.add_argument("--unidades", default="datos/edomex/municipios_edomex.gpkg")
    p.add_argument("--campo-unidad", default="NOM_MUN")
    p.add_argument("--tolerancia-m", type=float, default=30,
                   help="distancia para contar como coincidencia cercana (desfase entre sensores)")
    p.add_argument("--cobertura-min", type=int, default=30,
                   help="cobertura de copa 2000 (%%) para la columna hansen_perdida_tc_ha")
    p.add_argument("--recortes", default="datos/edomex/hansen", help="carpeta de los recortes de Hansen")
    p.add_argument("--volver-a-bajar", action="store_true", help="rehace los recortes aunque existan")
    p.add_argument("--filas-bloque", type=int, default=1024)
    p.add_argument("--celda-m", type=float, default=250, help="celda del mapa PNG")
    p.add_argument("--min-ha-celda", type=float, default=0.1,
                   help="pérdida mínima de cada fuente para que cuente en una celda del mapa")
    p.add_argument("--acercamiento-km", type=float, default=8, help="lado del cuadro de acercamiento")
    p.add_argument("--solo-mapa", action="store_true", help="redibuja el PNG con las salidas ya calculadas")
    p.add_argument("--salida", default="resultados/validacion_hansen")
    a = p.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    configurar_gdal()

    if a.solo_mapa:
        dibujar_mapa(a, pd.read_csv(Path(a.salida) / "validacion_estatal.csv"))
        return

    import geopandas as gpd
    anio_max = 2000 + int(a.version.split("-")[1][2:])  # GFC-2025-v1.13 -> 2025
    comparaciones = []
    for ruta, anios in (a.comparacion or PREDETERMINADAS):
        lista = sorted({int(x) for x in str(anios).split(",")})
        if max(lista) > anio_max or min(lista) < 2001:
            sys.exit(f"{a.version} trae pérdida de 2001 a {anio_max}; se pidió {anios}")
        if not Path(ruta).exists():
            sys.exit(f"No existe {ruta}")
        comparaciones.append({"ruta": ruta, "periodo": Path(ruta).stem.removeprefix("cambio_"),
                              "anios_hansen": [x - 2000 for x in lista], "anio_max": anio_max - 2000,
                              "texto_anios": "+".join(str(x) for x in lista)})
    limites = tuple(gpd.read_file(a.aoi).to_crs("EPSG:4326").total_bounds)
    log(f"Hansen {a.version}; estado {', '.join(f'{x:.3f}' for x in limites)}")
    _, estatal = comparar(a, comparaciones, limites)
    cols = ["periodo", "proto_perdida_ha", "hansen_perdida_ha", "ambos_ha", "precision", "exhaustividad",
            "precision_tol", "exhaustividad_tol", "hansen_sin_zona_ha", "hansen_sin_zona_malla_original_ha"]
    print(estatal[cols].to_string(index=False))
    dibujar_mapa(a, estatal)


if __name__ == "__main__":
    main()
