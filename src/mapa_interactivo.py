#!/usr/bin/env python3
"""
Página HTML interactiva con los resultados de una o varias corridas
===================================================================

Arma la página para explorar el balance de masa forestal, de dos formas que comparten la misma
plantilla, el mismo código de la página y los mismos datos:

  - `--salida ARCHIVO.html`: un solo archivo (sin servidor) con todos los datos dentro;
  - `--sitio CARPETA` (desde 0.8.0): un sitio estático, listo para GitHub Pages, con la página sin
    datos (`index.html`) y los datos en archivos separados que la página pide con `fetch` solo al
    consultarlos:

        datos/indice.json                  lo mínimo para arrancar (años, comparaciones, totales
                                           estatales por año, umbral, validación)
        datos/municipios.topojson          municipios y contorno estatal, EPSG:32614
        datos/anios/AAAA.json              cifras del año por municipio y tipo de bosque
        datos/tendencias.json              tendencia de la serie por municipio y tipo
        datos/comparaciones/<id>.json      una comparación entre dos años
        datos/incendios/<id>.json          los incendios de esa comparación, con su ubicación y fecha
                                           (HU-7.3; solo se piden al consultar la capa o la tabla)
        datos/cuadriculas/*.png            cuadrícula de 90 m (clase x paso en gris)

La página tiene:

  - la evolución del bosque del Estado año con año (CF-DEV-01 de las Tablas v12), siempre a la vista;
  - modo "Comparar años" (Desde → Hasta): el ráster de cambio (con capas que se prenden y apagan),
    el cambio neto por unidad en porcentaje o el año de pérdida; cifras, detalle y tabla de la
    comparación elegida;
  - modo "Un año" (CF-DEV-10, si hay una serie): el bosque de ese año en el mapa, sus cifras, su
    cambio desde el año anterior y la tendencia, con tabla por municipio y por tipo de bosque;
  - capa del año de pérdida (CF-DEV-12) y, en el detalle de cada municipio, su serie y su tendencia
    (CF-DEV-08);
  - sección "Alcances" (CF-DEV-14): qué mide, dónde, cuándo, con qué fuentes y qué no puede afirmar.

Cada carpeta puede traer una comparación (`correr`) o varias (`serie`: una por par de años, más
serie_*.csv, tendencia_*.csv, bosque_por_anio.tif y anio_perdida.tif). Si dos carpetas traen el mismo
par de años y la misma temporada, se usa la de la serie. Todas deben ser de la misma zona (mismo
--aoi), para que sus rásters coincidan. Solo las librerías D3 y TopoJSON se cargan de internet
(cdnjs).

Uso (desde la raíz del repositorio):
    python src/mapa_interactivo.py resultados/edomex_serie_2023_2025 resultados/edomex_2025_2026_sepoct \
        --unidades datos/edomex/municipios_edomex.gpkg --campo-unidad NOM_MUN \
        --titulo "Estado de México" --validacion resultados/validacion_hansen \
        --salida docs/mapa_edomex.html --sitio docs/calculadora

Con --fragmento escribe el archivo único sin <html>/<head>/<body>, para publicarlo como Artifact.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mapa_cambio import leer_cambio_agregado  # noqa: E402
from prototipo_masa_forestal import DESTINOS, TIPOS_ORDEN  # noqa: E402

VERSION_DATOS = 1  # forma de los archivos de datos/ (subirla si cambia)
BOSQUE_MINIMO_HA = 500
CAMPOS = {"bosque_base_ha": "base", "perdida_incendio_ha": "inc", "otras_perdidas_ha": "otras",
          "ganancia_ha": "gan", "bosque_afectado_por_fuego_ha": "afect", "bosque_actual_ha": "actual",
          "cambio_neto_ha": "neto"}
# Desglose por tipo de bosque (tipo_bosque_<base>_<actual>.csv, desde 0.6.0)
CAMPOS_TIPO = {"bosque_base_ha": "base", "perdida_incendio_ha": "inc", "otras_perdidas_ha": "otras",
               "ganancia_ha": "gan", "bosque_actual_ha": "actual", "cambio_neto_ha": "neto"}
# Serie (serie_*.csv, desde 0.7.0): por año
CAMPOS_SERIE = {"zona_forestal_ha": "zona", "bosque_ha": "bosque", "perdida_incendio_ha": "inc",
                "otras_perdidas_ha": "otras", "ganancia_ha": "gan", "cambio_neto_ha": "neto"}
TODOS = "Todos"
TOTAL = "Total"  # unidad del total estatal en tendencia_*.csv
# Clases del bosque de un año en la malla reducida: parte de la celda con bosque
CORTES_DENSIDAD = [0.25, 0.5, 0.75]
PASO_CLASES, PASO_PERDIDA = 50, 25
# Incendios (HU-7.3): último año con capa de CONAFOR si no se puede leer el GeoPackage, y campos de la lista
ULTIMO_ANIO_CONAFOR = 2024
CAMPOS_INCENDIO = ["clave", "fecha", "municipio", "municipio_conafor", "lon", "lat", "px", "py",
                   "poligono_ha", "quemado_ha", "en_bosque_ha", "perdido_ha"]


def _tipos(carpeta, clave):
    """{"filas": {unidad: {tipo: [cifras]}}, "tot": {tipo: [cifras]}} o None si la corrida no lo tiene."""
    ruta = Path(carpeta) / f"tipo_bosque_{clave}.csv"
    if not ruta.exists():
        return None
    t = pd.read_csv(ruta)
    filas = {}
    for _, r in t.iterrows():
        filas.setdefault(str(r["unidad"]), {})[r["tipo_bosque"]] = [round(float(r[c]), 2) for c in CAMPOS_TIPO]
    tot = t.groupby("tipo_bosque")[list(CAMPOS_TIPO)].sum()
    tot = {tipo: [round(float(v), 2) for v in tot.loc[tipo]] for tipo in TIPOS_ORDEN if tipo in tot.index}
    return {"filas": filas, "tot": tot}


def _png_clases(arr, paso=PASO_CLASES) -> bytes:
    """Ráster de clases como PNG en escala de grises (valor x paso)."""
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray((arr * paso).astype(np.uint8), mode="L").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _escenas(carpeta, anio):
    log = Path(carpeta) / "correr.log"
    if not log.exists():
        return None
    m = re.search(rf"(\d+) escenas para el compuesto de {anio}", log.read_text(encoding="utf-8", errors="replace"))
    return int(m.group(1)) if m else None


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
VENTANA_NORMAL = ["11-01", "12-31"]


def _texto_ventana(ventana):
    (m0, d0), (m1, d1) = [(int(x) for x in v.split("-")) for v in ventana]
    if ventana == VENTANA_NORMAL:
        return "de noviembre-diciembre", "nov-dic"
    return (f"del {d0} de {MESES[m0 - 1]} al {d1} de {MESES[m1 - 1]}",
            f"{MESES[m0 - 1][:3]}-{MESES[m1 - 1][:3]}")


def _incendios(carpeta, clave):
    """Incendios de la comparación: incendios_dnbr_<clave>.csv (comparaciones largas de una serie),
    o incendios_dnbr.csv filtrado por su columna periodo (desde 0.7.0), o completo (antes)."""
    carpeta = Path(carpeta)
    if (carpeta / f"incendios_dnbr_{clave}.csv").exists():
        return pd.read_csv(carpeta / f"incendios_dnbr_{clave}.csv")
    if not (carpeta / "incendios_dnbr.csv").exists():
        return None
    i = pd.read_csv(carpeta / "incendios_dnbr.csv")
    if "periodo" in i.columns:
        i = i[i["periodo"].astype(str) == clave]
    return i if len(i) else None


# Uso al que pasó el terreno perdido (HU-7.4 / CF-DEV-04): estimación por clasificación de imágenes
PASO_DESTINO = 50  # 1 agrícola, 2 pecuario, 3 urbano, 4 otro, 5 sin dato (0 no aplica)
CAMPOS_DESTINO = ["otras", "agricola", "pecuario", "urbano", "otro", "sin_dato"]
FUENTE_DESTINO = ("Clasificación de imágenes Sentinel-2 L2A del año final de cada periodo (bosque aleatorio), "
                  "entrenada con las zonas no forestales de la Serie VII de uso del suelo y vegetación de INEGI (2021)")


def _exactitud_destino(carpeta, a, b):
    """Exactitud del clasificador de destino a→b según destino_exactitud_<a>_<b>.csv, o None."""
    ruta = Path(carpeta) / f"destino_exactitud_{a}_{b}.csv"
    if not ruta.exists():
        return None
    e = pd.read_csv(ruta)
    g = e[e["clase"] == "global"].iloc[0]
    return {"anio": b, "global": _num(g["exactitud_global"], 4), "kappa": _num(g["kappa"], 4),
            "prueba": int(g["prueba"]), "entrenamiento": int(g["entrenamiento"]),
            "clases": {str(r["clase"]): [_num(r["exactitud_productor"], 4), _num(r["exactitud_usuario"], 4)]
                       for _, r in e[e["clase"] != "global"].iterrows()}}


def _clase_dominante(c):
    """Clase 1..5 más frecuente de cada celda (0 si ninguna aplica; en empate, la de menor número)."""
    cuentas = np.stack([(c == k).sum(axis=(1, 3)) for k in range(1, 6)])
    yield np.where(cuentas.max(axis=0) == 0, 0, cuentas.argmax(axis=0) + 1).astype(np.uint8)


def preparar_destino(carpeta, clave, base, actual, etiquetas_anio, f):
    """Datos de la tarjeta «A qué uso pasó el terreno perdido» de una comparación y su cuadrícula.
    Regresa (dict, png o None). Sin destino_perdidas_<clave>.csv el periodo queda «sin dato»."""
    carpeta = Path(carpeta)
    ruta = carpeta / f"destino_perdidas_{clave}.csv"
    exact = [x for x in (_exactitud_destino(carpeta, a, a + 1) for a in range(base, actual)) if x]
    if not exact:  # el preliminar de otra temporada guarda el par completo (p. ej. 2025_2026)
        x = _exactitud_destino(carpeta, base, actual)
        exact = [x] if x else []
    clasificados = {x["anio"] for x in exact}
    anios = [{"anio": a, "etiqueta": etiquetas_anio[a],
              "estado": "clasificado" if a in clasificados else "sin_dato",
              "motivo": ("" if a in clasificados else
                         "año base: no hay pérdida que clasificar" if a == base else "no se clasificó")}
             for a in range(base, actual + 1)]
    d = {"clave": clave, "campos": CAMPOS_DESTINO, "fuente": FUENTE_DESTINO, "anios": anios,
         "exactitud": exact, "anio_imagenes": sorted(clasificados), "serie_inegi": 2021}
    if not ruta.exists():
        return {**d, "estado": "sin_datos", "filas": {}, "total": None}, None
    t = pd.read_csv(ruta)
    cols = ["otras_perdidas_ha", "agricola_ha", "pecuario_ha", "urbano_ha", "otro_ha", "sin_dato_ha"]
    d["filas"] = {str(r["unidad"]): [_num(r[c]) for c in cols] for _, r in t.iterrows()}
    d["total"] = [round(float(t[c].sum()), 2) for c in cols]
    d["estado"] = "completo"
    tif = carpeta / f"destino_{clave}.tif"
    png = _png_clases(leer_por_celdas(tif, f, _clase_dominante)[0], paso=PASO_DESTINO)         if tif.exists() else None
    return d, png


def preparar_periodo(carpeta, clave, ancho_px):
    """Una comparación entre dos años. Las claves que empiezan con "_" no van a la página."""
    carpeta = Path(carpeta)
    base, actual = (int(x) for x in clave.split("_"))
    bal = pd.read_csv(carpeta / f"balance_{clave}.csv")
    ruta_corrida = carpeta / f"corrida_{clave}.json"
    corrida = json.loads(ruta_corrida.read_text(encoding="utf-8")) if ruta_corrida.exists() else {}
    ventana = corrida.get("ventana", VENTANA_NORMAL)
    preliminar = ventana != VENTANA_NORMAL
    meses, meses_corto = _texto_ventana(ventana)
    escenas = corrida.get("escenas")
    escenas = [escenas.get(str(base)), escenas.get(str(actual))] if escenas else \
        [_escenas(carpeta, base), _escenas(carpeta, actual)]
    cambio, f, limites, crs = leer_cambio_agregado(carpeta / f"cambio_{clave}.tif", ancho_px)
    tot = {CAMPOS[c]: round(float(bal[c].sum()), 2) for c in CAMPOS}
    filas = {str(r["unidad"]): [round(float(r[c]), 2) for c in CAMPOS] for _, r in bal.iterrows()}

    inc = {"n": 0}
    notas = []
    if preliminar:
        notas.append(f"Preliminar: compara {meses} de {base} con lo mismo de {actual}, las imágenes más "
                     f"recientes que hay. Es otra temporada que la de los balances anuales (noviembre-"
                     f"diciembre) y usa su propio umbral de NDVI, así que sus hectáreas no se suman ni se "
                     f"comparan con las de esos balances. Sirve para ver dónde cambió el bosque en el último año.")
    i = _incendios(carpeta, clave)
    if i is not None:
        anios = pd.to_datetime(i["fecha_inicio"], errors="coerce").dt.year
        inc = {"n": int(len(i)), "poligono": round(float(i["poligono_ha"].sum())),
               "quemado": round(float(i["quemado_dnbr_ha"].sum())),
               "en_bosque": round(float(i["quemado_en_bosque_ha"].sum())),
               "perdido": round(float(i["perdido_al_cierre_ha"].sum()))}
        if (anios == actual).sum() == 0:
            notas.append(f"No hay polígonos de incendios de {actual} (CONAFOR aún no los publica). La pérdida "
                         f"por incendio no incluye lo que se quemó en {actual}; eso quedó dentro de "
                         f"“otras pérdidas”.")
    else:
        notas.append("No hay polígonos de incendios de CONAFOR para este periodo (aún no se publican), así "
                     "que toda la pérdida aparece como “otras pérdidas”.")
    sufijo = f" ({meses_corto})" if preliminar else ""
    # Identificador de archivo: el par de años, y la ventana si no es la de nov-dic (para que un
    # preliminar no choque con el balance anual del mismo par)
    ident = clave if not preliminar else f"{clave}_{ventana[0].replace('-', '')}_{ventana[1].replace('-', '')}"
    tipos = _tipos(carpeta, clave)
    etq_anio = {a: (f"{a} ({meses_corto})" if preliminar else str(a)) for a in range(base, actual + 1)}
    destino, png_destino = preparar_destino(carpeta, clave, base, actual, etq_anio, f)
    return {"id": ident, "clave": clave, "base": base, "actual": actual, "preliminar": preliminar,
            "serie": bool(corrida.get("serie")),
            "etiqueta": f"{base} → {actual}", "meses": meses,
            "base_txt": f"{meses_corto} {base}" if preliminar else str(base),
            "actual_txt": f"{meses_corto} {actual}" if preliminar else str(actual),
            "corto": f"{str(base)[2:]}→{str(actual)[2:]}{'*' if preliminar else ''}", "sufijo": sufijo,
            "umbral": round(float(bal["umbral_ndvi"].iloc[0]), 2), "escenas": escenas,
            "fuego_incompleto": any("incendios" in n for n in notas), "tiene_tipos": tipos is not None,
            "tot": tot, "filas": filas, "incendios": inc, "notas": notas, "tipos": tipos,
            "destino_estado": destino["estado"], "_destino": destino, "_png_destino": png_destino,
            "_png": _png_clases(cambio), "_malla": (cambio.shape, f, limites, crs), "_ventana": ventana, "_inc": i}


# Campos de una comparación que van en el índice (los demás van en su archivo)
LIGEROS = ["id", "clave", "base", "actual", "preliminar", "serie", "etiqueta", "meses", "base_txt",
           "actual_txt", "corto", "sufijo", "umbral", "escenas", "fuego_incompleto", "tiene_tipos",
           "anios_sin_capa", "incendios_estado", "destino_estado"]
PESADOS = ["tot", "filas", "incendios", "notas", "tipos"]


def leer_por_celdas(ruta, f, funcion, capas=1):
    """Reduce un ráster uint8 a celdas de f x f píxeles con `funcion(celdas)` (celdas de forma
    (filas, f, columnas, f)), que regresa `capas` arreglos (filas, columnas). Lee por franjas."""
    import rasterio
    from rasterio.windows import Window
    with rasterio.open(ruta) as src:
        alto, ancho = src.height, src.width
        h, w = math.ceil(alto / f), math.ceil(ancho / f)
        salida = [np.zeros((h, w), dtype=np.uint8) for _ in range(capas)]
        paso = f * max(1, 4096 // f)
        for r0 in range(0, alto, paso):
            r1 = min(r0 + paso, alto)
            a = src.read(1, window=Window(0, r0, ancho, r1 - r0))
            filas = math.ceil((r1 - r0) / f)
            a = np.pad(a, ((0, filas * f - (r1 - r0)), (0, w * f - ancho)))
            for k, v in enumerate(funcion(a.reshape(filas, f, w, f))):
                salida[k][r0 // f:r0 // f + filas] = v
    return salida


def _num(v, nd=2):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), nd)


def preparar_serie(carpeta, f):
    """Datos del modo "Un año", de la evolución y de la capa del año de pérdida.

    Regresa (ligero, anios, tendencias, pngs): `ligero` va en el índice (totales estatales por año);
    `anios[t]` es el archivo de cada año; `pngs` las cuadrículas {nombre: bytes}."""
    carpeta = Path(carpeta)
    ruta = sorted(carpeta.glob("serie_*.csv"))[0]
    cola = ruta.stem.removeprefix("serie_")
    s = pd.read_csv(ruta)
    meta = json.loads((carpeta / f"serie_{cola}.json").read_text(encoding="utf-8"))
    tend = pd.read_csv(carpeta / f"tendencia_{cola}.csv")
    anios = [int(x) for x in meta["anios"]]
    N = len(anios)
    escenas = [meta["escenas"].get(str(a)) for a in anios]
    hay_sin_enc = "bosque_sin_encadenar_ha" in s.columns

    # Un archivo por año. Cada uno trae las mismas unidades y tipos (con None si el tipo no tiene
    # cifras ese año), para que la página pueda armar la serie de cualquier unidad.
    por_anio = [{"anio": a, "t": t, "campos": list(CAMPOS_SERIE.values()), "destinos": DESTINOS,
                 "escenas": escenas[t], "filas": {}, "destino": {}, "sin_encadenar": {}} for t, a in enumerate(anios)]
    for (u, tipo), g in s.groupby(["unidad", "tipo_bosque"], sort=False):
        g = g.set_index("anio").reindex(anios)
        for t, (_, r) in enumerate(g.iterrows()):
            por_anio[t]["filas"].setdefault(str(u), {})[tipo] = [_num(r[c]) for c in CAMPOS_SERIE]
            if tipo == TODOS:
                por_anio[t]["destino"][str(u)] = [_num(r[f"{d}_ha"]) for d in DESTINOS]
                if hay_sin_enc:
                    por_anio[t]["sin_encadenar"][str(u)] = _num(r["bosque_sin_encadenar_ha"])
    tot = {}
    for tipo, g in s.groupby("tipo_bosque", sort=False):
        suma = g.groupby("anio")[list(CAMPOS_SERIE)].sum(min_count=1).reindex(anios)
        tot[tipo] = [[_num(r[c], 2) for c in CAMPOS_SERIE] for _, r in suma.iterrows()]
    sd = s[s["tipo_bosque"] == TODOS].groupby("anio")[[f"{d}_ha" for d in DESTINOS]].sum(min_count=1).reindex(anios)
    destino_tot = [[_num(v, 2) for v in r] for _, r in sd.iterrows()]
    sin_enc = (s[s["tipo_bosque"] == TODOS].groupby("anio")["bosque_sin_encadenar_ha"].sum()
               .reindex(anios).round(2).tolist() if hay_sin_enc else None)
    for t in range(N):
        por_anio[t]["estado"] = {tipo: filas[t] for tipo, filas in tot.items()}
        por_anio[t]["destino_estado"] = destino_tot[t]
        por_anio[t]["sin_encadenar_estado"] = sin_enc[t] if sin_enc else None
    tendencias = {}
    for _, r in tend.iterrows():
        tendencias.setdefault(str(r["unidad"]), {})[r["tipo_bosque"]] = [_num(r["tendencia_ha_anio"]),
                                                                         _num(r["tendencia_pct_anio"], 3)]

    # Bosque de cada año: parte de la celda con bosque, en 5 clases (0 nada, 1 <25 %, ... 4 >=75 %)
    def densidad(c):
        for t in range(N):
            frac = ((c >> t) & 1).mean(axis=(1, 3))
            yield np.where(frac == 0, 0, 1 + np.searchsorted(CORTES_DENSIDAD, frac, side="right")).astype(np.uint8)
    pngs = {f"bosque_{a}.png": _png_clases(arr)
            for a, arr in zip(anios, leer_por_celdas(carpeta / "bosque_por_anio.tif", f, densidad, N))}

    # Año de pérdida: el más reciente de la celda, como índice t del año (1..N-1)
    codigos = np.zeros(256, dtype=np.uint8)
    for t in range(1, N):
        codigos[anios[t] - 2000] = t

    def ultimo(c):
        yield codigos[c.max(axis=(1, 3))]
    pngs["anio_perdida.png"] = _png_clases(leer_por_celdas(carpeta / "anio_perdida.tif", f, ultimo)[0],
                                           paso=PASO_PERDIDA)
    exactitud = {k: ({"global": v.get("exactitud_global"), "kappa": v.get("kappa"),
                      "prueba": v.get("muestras_prueba")} if v else None)
                 for k, v in (meta.get("destino") or {}).items()}
    ligero = {"anios": anios, "clave": cola, "umbral": round(float(meta["umbral_ndvi"]), 2),
              "escenas": escenas, "incendios": meta.get("incendios_por_periodo"),
              "zona_ha": meta.get("zona_forestal_ha"), "clases": meta.get("clases_forestales"),
              "campos": list(CAMPOS_SERIE.values()), "tot": tot, "destino_tot": destino_tot,
              "destinos": DESTINOS, "tend_total": tendencias.get(TOTAL, {}), "sin_encadenar": sin_enc,
              "exactitud": exactitud, "paso_perdida": PASO_PERDIDA, "fecha": meta.get("fecha")}
    return ligero, por_anio, tendencias, pngs


def preparar_unidades(ruta, campo, nombres, malla):
    """Municipios y contorno estatal como TopoJSON en EPSG:32614 (metros), simplificados a media
    celda sobre los arcos compartidos (sin huecos entre municipios). La página los proyecta a los
    píxeles de la cuadrícula con d3.geoIdentity, con los datos de `malla` del índice."""
    import geopandas as gpd
    import topojson as tp
    (alto, ancho), f, (izq, abajo, der, arriba), crs = malla
    tam = 10 * f  # metros por píxel de la malla reducida
    uni = gpd.read_file(ruta).to_crs(crs)
    uni = uni[uni[campo].astype(str).isin(nombres)].reset_index(drop=True)
    uni = gpd.GeoDataFrame({"nombre": uni[campo].astype(str)}, geometry=uni.geometry, crs=crs)
    estado = gpd.GeoDataFrame({"nombre": ["Estado"]}, geometry=[uni.union_all()], crs=crs)
    topo = tp.Topology([uni, estado], object_name=["municipios", "estado"], prequantize=1e5,
                       toposimplify=tam * 0.5, topology=True)
    datos = json.loads(topo.to_json())
    for obj in datos["objects"].values():
        for g in obj["geometries"]:
            g.pop("id", None)
    epsg = crs.to_epsg()
    return datos, {"crs": f"EPSG:{epsg}" if epsg else str(crs), "izq": izq, "arriba": arriba, "tam": tam}


def preparar_incendios_conafor(ruta, malla, unidades, campo, claves):
    """Ubicación de los incendios (HU-7.3): {clave: {...}} para las `claves` pedidas, y los años con capa.

    Lee el GeoPackage de CONAFOR (datos/edomex/incendios_conafor_edomex.gpkg). La ubicación es el
    centroide del polígono, en la malla de la página (px, py) y en lon/lat. El municipio es el de la
    capa de unidades con más superficie dentro del polígono (algunos incendios tocan otro estado o
    el límite); `municipio_conafor` es el que reportó CONAFOR."""
    import geopandas as gpd
    (alto, ancho), f, (izq, abajo, der, arriba), crs = malla
    tam = 10 * f
    g = gpd.read_file(ruta)
    anios = sorted(int(a) for a in g["ANIO_CAPA"].dropna().unique())
    g = g[g["CLAVEINC"].isin(set(claves))].drop_duplicates("CLAVEINC").to_crs(crs).reset_index(drop=True)
    uni = gpd.read_file(unidades).to_crs(crs)[[campo, "geometry"]]
    cruce = gpd.overlay(gpd.GeoDataFrame({"clave": g["CLAVEINC"]}, geometry=g.geometry, crs=crs), uni, how="intersection")
    cruce["area"] = cruce.geometry.area
    municipio = cruce.sort_values("area", ascending=False).drop_duplicates("clave").set_index("clave")[campo].astype(str)
    c = g.geometry.centroid
    # Sin superficie dentro de ninguna unidad (el polígono cae en el borde): la unidad más cercana al centroide
    faltan = g[~g["CLAVEINC"].isin(municipio.index)]
    if len(faltan):
        pts = gpd.GeoDataFrame({"clave": faltan["CLAVEINC"].values}, geometry=c[faltan.index].values, crs=crs)
        cerca = gpd.sjoin_nearest(pts, uni, how="left").drop_duplicates("clave").set_index("clave")[campo].astype(str)
        municipio = pd.concat([municipio, cerca])
    ll = c.to_crs(4326)
    datos = {}
    for k, r in g.iterrows():
        cl = r["CLAVEINC"]
        datos[cl] = {"municipio": municipio.get(cl), "municipio_conafor": None if pd.isna(r["MUNICIPIO"]) else str(r["MUNICIPIO"]),
                     "lon": round(float(ll.iloc[k].x), 4), "lat": round(float(ll.iloc[k].y), 4),
                     "px": round(float((c.iloc[k].x - izq) / tam), 1), "py": round(float((arriba - c.iloc[k].y) / tam), 1)}
    return datos, anios


def lista_incendios(i, ubic):
    """Filas de incendios_<periodo>.json: una por incendio con su ubicación (si se encontró)."""
    filas = []
    for _, r in i.iterrows():
        u = ubic.get(str(r["incendio"]))
        if u is None:
            continue
        filas.append([str(r["incendio"]), str(r["fecha_inicio"]), u["municipio"], u["municipio_conafor"], u["lon"], u["lat"],
                      u["px"], u["py"], round(float(r["poligono_ha"]), 2), round(float(r["quemado_dnbr_ha"]), 2),
                      round(float(r["quemado_en_bosque_ha"]), 2), round(float(r["perdido_al_cierre_ha"]), 2)])
    return filas


def _validacion(carpeta):
    """Precisión y exhaustividad contra Hansen por periodo (validacion_estatal.csv), si existe."""
    if not carpeta or not (Path(carpeta) / "validacion_estatal.csv").exists():
        return None
    v = pd.read_csv(Path(carpeta) / "validacion_estatal.csv")
    return [{"periodo": str(r["periodo"]), "precision": _num(r.get("precision"), 3),
             "exhaustividad": _num(r.get("exhaustividad"), 3)} for _, r in v.iterrows()]


def armar_datos(carpetas, unidades, campo_unidad, titulo, ancho_px, validacion, conafor=None, infys=None):
    """Todos los archivos de datos de la página: {ruta relativa a datos/: dict (JSON) o bytes (PNG)}.
    Los dos modos de salida usan exactamente estos archivos."""
    periodos, carpeta_serie = {}, None
    for c in carpetas:
        claves = sorted(x.stem.removeprefix("balance_") for x in Path(c).glob("balance_*.csv"))
        if not claves:
            sys.exit(f"No hay balance_*.csv en {c}.")
        if list(Path(c).glob("serie_*.csv")):
            if carpeta_serie:
                sys.exit("Solo puede haber una carpeta de serie.")
            carpeta_serie = c
        for clave in claves:
            pp = preparar_periodo(c, clave, ancho_px)
            llave = (clave, tuple(pp["_ventana"]))
            # La comparación de la serie gana sobre una corrida directa del mismo par y temporada
            if llave not in periodos or (pp["serie"] and not periodos[llave]["serie"]):
                periodos[llave] = pp
    periodos = list(periodos.values())
    # Primero los balances anuales (los de un año, luego los más largos) y al final los preliminares
    periodos.sort(key=lambda x: (x["preliminar"], x["actual"] - x["base"], x["base"]))
    mallas = {(pp["_malla"][0], pp["_malla"][1], tuple(round(v) for v in pp["_malla"][2])) for pp in periodos}
    if len(mallas) > 1:
        sys.exit("Las corridas no tienen la misma malla (¿distinto --aoi?).")
    malla = periodos[0]["_malla"]
    (alto, ancho), f = malla[0], malla[1]
    nombres = sorted({n for pp in periodos for n in pp["filas"]})
    topo, georef = preparar_unidades(unidades, campo_unidad, nombres, malla)

    # Incendios (HU-7.3): ubicación de cada uno, y qué años no tienen capa de CONAFOR todavía
    ubic, anios_pub = {}, None
    if conafor and Path(conafor).exists():
        claves = {str(c) for pp in periodos if pp["_inc"] is not None for c in pp["_inc"]["incendio"]}
        ubic, anios_pub = preparar_incendios_conafor(conafor, malla, unidades, campo_unidad, claves)
    else:
        print(f"Aviso: no se encontró {conafor}; la página no tendrá la ubicación de los incendios.")
    ultimo = max(anios_pub) if anios_pub else ULTIMO_ANIO_CONAFOR

    archivos = {"municipios.topojson": topo}
    # Especies registradas en el INFyS (HU-7.5): agregado por municipio, archivo propio que se pide al consultarlo
    inventario = None
    if infys and Path(infys).exists():
        import especies_infys
        esp = especies_infys.construir(infys, nombres)
        archivos["especies.json"] = esp
        inventario = {k: esp[k] for k in ("fuente", "periodo", "anios_campo", "malla_km", "nota", "licencia", "resumen", "textos_situacion")}
    else:
        print(f"Aviso: no se encontró {infys}; la página no tendrá las especies del inventario.")
    for pp in periodos:
        # Años de la ventana del periodo sin capa de CONAFOR: sus incendios no se conocen (no son cero)
        pp["anios_sin_capa"] = [a for a in range(pp["base"], pp["actual"] + 1) if a > ultimo]
        pp["incendios_estado"] = ("completo" if not pp["anios_sin_capa"]
                                  else "parcial" if pp["incendios"].get("n") else "sin_datos")
        lista = lista_incendios(pp["_inc"], ubic) if pp["_inc"] is not None else []
        archivos[f"incendios/{pp['id']}.json"] = {
            "id": pp["id"], "clave": pp["clave"], "etiqueta": pp["etiqueta"], "preliminar": pp["preliminar"],
            "estado": pp["incendios_estado"], "anios_sin_capa": pp["anios_sin_capa"], "ultimo_anio_conafor": ultimo,
            "campos": CAMPOS_INCENDIO, "lista": lista,
            "sin_ubicacion": (0 if pp["_inc"] is None else int(len(pp["_inc"]) - len(lista)))}
        archivos[f"comparaciones/{pp['id']}.json"] = {
            "id": pp["id"], "clave": pp["clave"], "etiqueta": pp["etiqueta"], "preliminar": pp["preliminar"],
            "campos": list(CAMPOS.values()), "campos_tipo": list(CAMPOS_TIPO.values()),
            **{k: pp[k] for k in PESADOS}}
        archivos[f"cuadriculas/cambio_{pp['id']}.png"] = pp["_png"]
        archivos[f"destino/{pp['id']}.json"] = {"id": pp["id"], "etiqueta": pp["etiqueta"], "preliminar": pp["preliminar"],
                                                "tiene_cuadricula": pp["_png_destino"] is not None, **pp["_destino"]}
        if pp["_png_destino"] is not None:
            archivos[f"cuadriculas/destino_{pp['id']}.png"] = pp["_png_destino"]

    serie = None
    if carpeta_serie:
        serie, por_anio, tendencias, pngs = preparar_serie(carpeta_serie, f)
        for d in por_anio:
            archivos[f"anios/{d['anio']}.json"] = d
        archivos["tendencias.json"] = {"anios": serie["anios"], "tendencias": tendencias}
        for nombre, png in pngs.items():
            archivos[f"cuadriculas/{nombre}"] = png
        anios = serie["anios"]
        IS = {c: i for i, c in enumerate(serie["campos"])}
        evolucion = [{"anio": a, "zona_ha": r[IS["zona"]], "bosque_ha": r[IS["bosque"]],
                      "cambio_neto_ha": r[IS["neto"]]} for a, r in zip(anios, serie["tot"][TODOS])]
    else:
        anios = sorted({a for pp in periodos if not pp["preliminar"] for a in (pp["base"], pp["actual"])})
        evolucion = None
    articulo = "del" if titulo.lower().startswith("estado") else "de"
    archivos["indice.json"] = {
        "version_datos": VERSION_DATOS, "generado": datetime.now().isoformat(timespec="seconds"),
        "titulo": titulo, "nombre": f"Masa forestal {articulo} {titulo}",
        "ancho": ancho, "alto": alto, "celda": 10 * f, "malla": georef,
        "minimo": BOSQUE_MINIMO_HA, "campos": list(CAMPOS.values()),
        "campos_tipo": list(CAMPOS_TIPO.values()), "tipos": TIPOS_ORDEN,
        "anios": anios, "evolucion_estatal": evolucion,
        "conafor": {"anios": anios_pub or list(range(2019, ultimo + 1)), "ultimo": ultimo},
        "comparaciones": [{k: pp[k] for k in LIGEROS} for pp in periodos],
        "serie": serie, "validacion": _validacion(validacion), "inventario": inventario,
        "pasos": {"clases": PASO_CLASES, "perdida": PASO_PERDIDA, "destino": PASO_DESTINO},
        "destinos": DESTINOS,
        "archivos": sorted(k for k in archivos if k != "indice.json")}
    return archivos


def _json(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _pagina(plantilla, nombre, titulo, datos_embebidos, fragmento):
    """La plantilla con o sin los datos dentro. Sin datos, la página los pide a datos/."""
    html = plantilla.replace("__NOMBRE__", nombre).replace("__TITULO__", titulo)
    if datos_embebidos is None:
        html = re.sub(r'<script type="application/json" id="datos">__DATOS__</script>\n?', "", html)
    else:
        html = html.replace("__DATOS__", datos_embebidos.replace("</", "<\\/"))
    if not fragmento:
        return ('<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                + html.replace("<!--FIN_HEAD-->", "</head>\n<body>") + "\n</body>\n</html>\n")
    return html.replace("<!--FIN_HEAD-->", "")


def escribir_archivo_unico(archivos, plantilla, salida, fragmento):
    embebidos = {k: ("data:image/png;base64," + base64.b64encode(v).decode("ascii")) if isinstance(v, bytes) else v
                 for k, v in archivos.items()}
    idx = archivos["indice.json"]
    html = _pagina(plantilla, idx["nombre"], idx["titulo"], _json({"archivos": embebidos}), fragmento)
    Path(salida).parent.mkdir(parents=True, exist_ok=True)
    Path(salida).write_text(html, encoding="utf-8")
    return len(html.encode())


def escribir_sitio(archivos, plantilla, carpeta):
    """index.html + datos/. Borra antes la carpeta datos/ del sitio (solo la genera este script)."""
    carpeta = Path(carpeta)
    datos = carpeta / "datos"
    if datos.exists():
        shutil.rmtree(datos)
    tam = {}
    for ruta, v in archivos.items():
        destino = datos / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        contenido = v if isinstance(v, bytes) else _json(v).encode("utf-8")
        destino.write_bytes(contenido)
        tam[ruta] = len(contenido)
    idx = archivos["indice.json"]
    html = _pagina(plantilla, idx["nombre"], idx["titulo"], None, False)
    (carpeta / "index.html").write_text(html, encoding="utf-8")
    tam["index.html"] = len(html.encode())
    return tam


def main():
    p = argparse.ArgumentParser(description="Página HTML interactiva de una o varias corridas")
    p.add_argument("carpetas", nargs="+", help="carpetas de resultados (de correr o de serie)")
    p.add_argument("--unidades", required=True)
    p.add_argument("--campo-unidad", default="NOM_MUN")
    p.add_argument("--titulo", default="Estado de México")
    p.add_argument("--ancho-px", type=int, default=2400, help="resolución del ráster en la página")
    p.add_argument("--validacion", help="carpeta de src/validar_hansen.py, para citar sus cifras en Alcances")
    p.add_argument("--salida", help="archivo HTML único, con los datos dentro")
    p.add_argument("--fragmento", action="store_true",
                   help="con --salida: sin <html>/<head>/<body> (para publicarla como Artifact)")
    p.add_argument("--sitio", help="carpeta del sitio estático (index.html + datos/), p. ej. docs/calculadora")
    p.add_argument("--infys", default="datos/edomex/infys",
                   help="carpeta con los CSV del INFyS 2015-2020 (ver su LEEME.md), para las especies por municipio")
    p.add_argument("--incendios", default="datos/edomex/incendios_conafor_edomex.gpkg",
                   help="polígonos de incendios de CONAFOR (src/descargar_capas.py), para ubicar cada incendio")
    a = p.parse_args()
    if not a.salida and not a.sitio:
        p.error("falta --salida, --sitio o los dos")

    archivos = armar_datos(a.carpetas, a.unidades, a.campo_unidad, a.titulo, a.ancho_px, a.validacion, a.incendios, a.infys)
    idx = archivos["indice.json"]
    plantilla = (Path(__file__).resolve().parent / "plantilla_mapa.html").read_text(encoding="utf-8")
    resumen = (f"{len(idx['comparaciones'])} comparación(es)"
               f"{', con serie ' + idx['serie']['clave'] if idx['serie'] else ''}")
    if a.salida:
        n = escribir_archivo_unico(archivos, plantilla, a.salida, a.fragmento)
        print(f"Página en {Path(a.salida).resolve()} ({n / 1e6:.1f} MB, {resumen})")
    if a.sitio:
        tam = escribir_sitio(archivos, plantilla, a.sitio)
        inicial = tam["index.html"] + tam["indice.json"] + tam["municipios.topojson"]
        print(f"Sitio en {Path(a.sitio).resolve()} ({len(tam)} archivos, {sum(tam.values()) / 1e6:.1f} MB en total; "
              f"index + índice + municipios = {inicial / 1e3:.0f} kB; {resumen})")


if __name__ == "__main__":
    main()
