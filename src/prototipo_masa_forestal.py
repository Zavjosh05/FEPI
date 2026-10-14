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
    pip install pystac-client odc-stac dask geopandas rasterio numpy pandas xarray

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
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
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
NUBES_MAX = 60

# Códigos del ráster de cambio
SIN_BOSQUE, ESTABLE, PERD_INCENDIO, PERD_OTRA, GANANCIA = 0, 1, 2, 3, 4


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
    """Balance en hectáreas por unidad.

    unidades: ráster entero (0 = fuera de cualquier unidad, 1..n = índice en nombres).
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


def umbral_otsu(valores: np.ndarray, bins: int = 200) -> float:
    """Umbral de Otsu: separa los dos picos del histograma de NDVI (bosque / no bosque).
    Sirve como valor provisional mientras no haya puntos de referencia para calibrar."""
    v = valores[np.isfinite(valores)]
    v = v[(v > -0.2) & (v < 1)]
    hist, bordes = np.histogram(v, bins=bins)
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


# ==========================================================================
# 3. Descarga y compuestos Sentinel-2 (Earth Search, sin cuenta)
# ==========================================================================
def _configurar_lectura():
    from odc.stac import configure_rio
    configure_rio(cloud_defaults=True, aws={"aws_unsigned": True})


def geobox_de(gdf):
    from odc.geo.geobox import GeoBox
    minx, miny, maxx, maxy = gdf.to_crs(CRS).total_bounds
    return GeoBox.from_bbox((minx, miny, maxx, maxy), CRS, resolution=RES)


def buscar_items(geobox, inicio, fin):
    from pystac_client import Client
    bbox = list(geobox.geographic_extent.boundingbox)
    cat = Client.open(STAC_URL)
    for col in COLECCIONES:
        items = list(cat.search(collections=[col], bbox=bbox, datetime=f"{inicio}/{fin}",
                                query={"eo:cloud_cover": {"lt": NUBES_MAX}}).items())
        if items:
            return items
    return []


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


def ndvi_anual(geobox, anio) -> np.ndarray:
    ini, fin = VENTANA_COBERTURA
    items = buscar_items(geobox, f"{anio}-{ini}", f"{anio}-{fin}")
    if not items:
        sys.exit(f"No hay imágenes Sentinel-2 para nov-dic {anio} en la zona.")
    print(f"  {len(items)} escenas para el compuesto de {anio}")
    return compuesto_indice(items, "ndvi", geobox)


def dnbr_incendio(geobox_total, geom, fecha) -> tuple[tuple[slice, slice], np.ndarray] | None:
    """dNBR = NBR antes - NBR después, en la ventana del polígono (alineada a la malla total)."""
    from rasterio.windows import from_bounds

    minx, miny, maxx, maxy = geom.buffer(200).bounds
    w = from_bounds(minx, miny, maxx, maxy, transform=geobox_total.affine)
    ny, nx = geobox_total.shape
    r0, c0 = max(int(np.floor(w.row_off)), 0), max(int(np.floor(w.col_off)), 0)
    r1 = min(int(np.ceil(w.row_off + w.height)), ny)
    c1 = min(int(np.ceil(w.col_off + w.width)), nx)
    if r1 <= r0 or c1 <= c0:
        return None
    sub = geobox_total[r0:r1, c0:c1]
    antes = buscar_items(sub, (fecha - timedelta(days=75)).date(), (fecha - timedelta(days=5)).date())
    despues = buscar_items(sub, (fecha + timedelta(days=10)).date(), (fecha + timedelta(days=70)).date())
    if not antes or not despues:
        return None
    dnbr = compuesto_indice(antes, "nbr", sub) - compuesto_indice(despues, "nbr", sub)
    return (slice(r0, r1), slice(c0, c1)), dnbr


# ==========================================================================
# 4. Comandos
# ==========================================================================
def cmd_calibrar(a):
    import geopandas as gpd
    _configurar_lectura()
    aoi = gpd.read_file(a.aoi)
    gb = geobox_de(aoi)
    ndvi = ndvi_anual(gb, a.anio)

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


def cmd_correr(a):
    import geopandas as gpd
    _configurar_lectura()
    out = Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)

    aoi = gpd.read_file(a.aoi).to_crs(CRS)
    gb = geobox_de(aoi)
    shape, tr = tuple(gb.shape), gb.affine
    dentro_aoi = rasterizar(aoi.geometry, [1] * len(aoi), shape, tr, dtype="uint8").astype(bool)

    print("Cobertura base y actual")
    ndvi_base, ndvi_act = ndvi_anual(gb, a.anio_base), ndvi_anual(gb, a.anio)
    if str(a.umbral_ndvi).lower() == "auto":
        umbral = umbral_otsu(ndvi_base[dentro_aoi])
        print(f"  Umbral NDVI automático (Otsu, provisional hasta calibrar): {umbral:.2f}")
    else:
        umbral = float(a.umbral_ndvi)

    zona = dentro_aoi.copy()
    if a.zona_forestal:
        zf = gpd.read_file(a.zona_forestal).to_crs(CRS)
        zf = zf[zf[a.campo_clase].astype(str).str.contains(a.clases_forestales, regex=True)]
        en_zf = rasterizar(zf.geometry, [1] * len(zf), shape, tr, dtype="uint8").astype(bool)
        if a.reforestacion:  # lo reforestado fuera de la zona forestal también cuenta
            rf = gpd.read_file(a.reforestacion).to_crs(CRS)
            en_zf |= rasterizar(rf.geometry, [1] * len(rf), shape, tr, dtype="uint8").astype(bool)
        zona &= en_zf
        print(f"  Zona forestal de referencia: {zona.sum() * HA_PIXEL:,.0f} ha")
    base, actual = mascaras_con_margen(ndvi_base, ndvi_act, umbral, a.margen_cambio, zona)

    quemado = np.zeros(shape, dtype=bool)
    dnbr_total = np.full(shape, np.nan, dtype="float32")
    resumen_inc = []
    if a.incendios:
        inc = gpd.read_file(a.incendios).to_crs(CRS)
        inc = inc[inc.intersects(aoi.union_all())].copy()
        inc["_fecha"] = leer_fechas(inc[a.campo_fecha])
        # Periodo del balance: del inicio del compuesto base al inicio del compuesto actual
        ini, fin = pd.Timestamp(a.anio_base, 11, 1), pd.Timestamp(a.anio, 11, 1)
        fuera = inc[(inc["_fecha"] >= fin)]
        inc = inc[(inc["_fecha"] >= ini) & (inc["_fecha"] < fin)]
        print(f"Incendios en el periodo {ini:%Y-%m-%d} a {fin - pd.Timedelta(days=1):%Y-%m-%d}: {len(inc)}")
        if len(fuera):
            print(f"  ({len(fuera)} incendio(s) posteriores al 1 de noviembre de {a.anio} quedan para el siguiente periodo)")
        for i, (_, fila) in enumerate(inc.iterrows(), start=1):
            geom, fecha = fila.geometry, fila["_fecha"]
            clave = fila.get(a.campo_id, i) if a.campo_id else i
            res = dnbr_incendio(gb, geom, fecha)
            if res is None:
                print(f"  incendio {clave}: sin imágenes antes/después, se omite")
                continue
            (rs, cs), d = res
            poly = rasterizar([geom], [1], d.shape, gb[rs, cs].affine, dtype="uint8").astype(bool)
            q = poly & (np.nan_to_num(d, nan=0) >= a.umbral_dnbr)
            dnbr_total[rs, cs] = np.where(poly, d, dnbr_total[rs, cs])
            quemado[rs, cs] |= q
            resumen_inc.append({
                "incendio": clave, "fecha_inicio": f"{fecha:%Y-%m-%d}",
                "poligono_ha": round(poly.sum() * HA_PIXEL, 2),
                "quemado_dnbr_ha": round(q.sum() * HA_PIXEL, 2),
                "quemado_en_bosque_ha": round((q & base[rs, cs]).sum() * HA_PIXEL, 2),
                "perdido_al_cierre_ha": round((q & base[rs, cs] & ~actual[rs, cs]).sum() * HA_PIXEL, 2),
                "dnbr_mediana": round(float(np.nanmedian(np.where(poly, d, np.nan))), 3),
            })
            print(f"  incendio {clave} ({fecha:%Y-%m-%d}): {q.sum() * HA_PIXEL:.1f} ha quemadas")
        if resumen_inc:
            pd.DataFrame(resumen_inc).to_csv(out / "incendios_dnbr.csv", index=False)

    en_refo = np.zeros(shape, dtype=bool)
    refo = None
    if a.reforestacion:
        refo = gpd.read_file(a.reforestacion).to_crs(CRS)
        en_refo = rasterizar(refo.geometry, [1] * len(refo), shape, tr, dtype="uint8").astype(bool)

    if a.unidades:
        uni = gpd.read_file(a.unidades).to_crs(CRS)
        uni = uni[uni.intersects(aoi.union_all())].reset_index(drop=True)
        nombres = uni[a.campo_unidad].astype(str).tolist()
        r_uni = rasterizar(uni.geometry, range(1, len(uni) + 1), shape, tr)
    else:
        uni, nombres, r_uni = None, ["zona piloto"], dentro_aoi.astype("int32")

    tabla = balance(base, actual, quemado, en_refo, r_uni, nombres)
    if refo is not None and uni is not None:
        esp = recuperacion_esperada(refo, uni, a.campo_unidad, a.campo_anio, a.campo_sobrev,
                                    a.anio_base, a.anio, a.sobrev_default)
        tabla = tabla.merge(esp, on="unidad", how="left").fillna(0)

    tabla.insert(1, "umbral_ndvi", umbral)
    tabla.to_csv(out / f"balance_{a.anio_base}_{a.anio}.csv", index=False)
    guardar_tif(out / f"ndvi_{a.anio_base}.tif", ndvi_base.astype("float32"), tr, nodata=np.nan)
    guardar_tif(out / f"ndvi_{a.anio}.tif", ndvi_act.astype("float32"), tr, nodata=np.nan)
    guardar_tif(out / "dnbr.tif", dnbr_total, tr, nodata=np.nan)
    guardar_tif(out / f"cambio_{a.anio_base}_{a.anio}.tif", mapa_cambio(base, actual, quemado), tr)
    print("\n" + tabla.to_string(index=False))
    print(f"\nResultados en {out.resolve()}")
    print("Códigos del ráster de cambio: 0 sin bosque, 1 bosque estable, 2 pérdida por incendio, "
          "3 otra pérdida, 4 ganancia")


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

    if a.salida:
        out = Path(a.salida)
        out.mkdir(parents=True, exist_ok=True)
        tabla.to_csv(out / "balance_demo.csv", index=False)
        guardar_tif(out / "cambio_demo.tif", mapa_cambio(base, actual, quemado), tr)
        print(f"Archivos de prueba en {out.resolve()}")


def main():
    p = argparse.ArgumentParser(description="Prototipo de la Calculadora de masa forestal (PROBOSQUE)")
    sp = p.add_subparsers(dest="cmd", required=True)

    d = sp.add_parser("demo", help="probar la lógica con datos inventados")
    d.add_argument("--salida", default=None)

    c = sp.add_parser("calibrar", help="elegir el umbral de NDVI con puntos de referencia")
    c.add_argument("--aoi", required=True)
    c.add_argument("--anio", type=int, required=True)
    c.add_argument("--puntos", required=True)
    c.add_argument("--salida", default="resultados")

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
    r.add_argument("--clases-forestales", default=r"^(B|VSA/)",
                   help="expresión regular de las claves que cuentan como zona forestal")
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

    a = p.parse_args()
    {"demo": cmd_demo, "calibrar": cmd_calibrar, "correr": cmd_correr}[a.cmd](a)


if __name__ == "__main__":
    main()
