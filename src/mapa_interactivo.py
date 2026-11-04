#!/usr/bin/env python3
"""
Página HTML interactiva con los resultados de una o varias corridas
===================================================================

Arma un solo archivo HTML (sin servidor) para explorar el balance de masa forestal:

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
--aoi), para que sus rásters coincidan. Los datos van dentro del archivo; solo la librería D3 se
carga de internet (cdnjs).

Uso (desde la raíz del repositorio):
    python src/mapa_interactivo.py resultados/edomex_serie_2023_2025 resultados/edomex_2025_2026_sepoct \
        --unidades datos/edomex/municipios_edomex.gpkg --campo-unidad NOM_MUN \
        --titulo "Estado de México" --validacion resultados/validacion_hansen --salida docs/mapa_edomex.html

Con --fragmento escribe la página sin <html>/<head>/<body>, para publicarla como Artifact.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mapa_cambio import leer_cambio_agregado  # noqa: E402
from prototipo_masa_forestal import DESTINOS, TIPOS_ORDEN  # noqa: E402

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
# Clases del bosque de un año en la malla reducida: parte de la celda con bosque
CORTES_DENSIDAD = [0.25, 0.5, 0.75]


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
    tot = {tipo: [round(float(v), 1) for v in tot.loc[tipo]] for tipo in TIPOS_ORDEN if tipo in tot.index}
    return {"filas": filas, "tot": tot}


def _png_clases(arr, paso=50) -> str:
    """Ráster de clases como PNG en escala de grises (valor x paso), en data URI."""
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray((arr * paso).astype(np.uint8), mode="L").save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


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


def preparar_periodo(carpeta, clave, ancho_px):
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
    tot = {CAMPOS[c]: round(float(bal[c].sum()), 1) for c in CAMPOS}
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
    return {"clave": clave, "base": base, "actual": actual, "preliminar": preliminar,
            "serie": bool(corrida.get("serie")),
            "etiqueta": f"{base} → {actual}", "meses": meses,
            "base_txt": f"{meses_corto} {base}" if preliminar else str(base),
            "actual_txt": f"{meses_corto} {actual}" if preliminar else str(actual),
            "corto": f"{str(base)[2:]}→{str(actual)[2:]}{'*' if preliminar else ''}", "sufijo": sufijo,
            "umbral": round(float(bal["umbral_ndvi"].iloc[0]), 2), "escenas": escenas,
            "tot": tot, "filas": filas, "incendios": inc, "notas": notas, "tipos": _tipos(carpeta, clave),
            "fuego_incompleto": any("incendios" in n for n in notas),
            "img": _png_clases(cambio), "_malla": (cambio.shape, f, limites, crs), "_ventana": ventana}


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
    """Datos del modo "Un año", de la serie y de la capa del año de pérdida."""
    carpeta = Path(carpeta)
    ruta = sorted(carpeta.glob("serie_*.csv"))[0]
    cola = ruta.stem.removeprefix("serie_")
    s = pd.read_csv(ruta)
    meta = json.loads((carpeta / f"serie_{cola}.json").read_text(encoding="utf-8"))
    tend = pd.read_csv(carpeta / f"tendencia_{cola}.csv")
    anios = [int(x) for x in meta["anios"]]
    N = len(anios)

    def lista(g):
        g = g.set_index("anio").reindex(anios)
        return [[_num(r[c]) for c in CAMPOS_SERIE] for _, r in g.iterrows()]

    filas, destino = {}, {}
    for (u, tipo), g in s.groupby(["unidad", "tipo_bosque"], sort=False):
        filas.setdefault(str(u), {})[tipo] = lista(g)
        if tipo == TODOS:
            gd = g.set_index("anio").reindex(anios)
            destino[str(u)] = [[_num(r[f"{d}_ha"]) for d in DESTINOS] for _, r in gd.iterrows()]
    tot = {}
    for tipo, g in s.groupby("tipo_bosque", sort=False):
        suma = g.groupby("anio")[list(CAMPOS_SERIE)].sum(min_count=1).reindex(anios)
        tot[tipo] = [[_num(r[c], 1) for c in CAMPOS_SERIE] for _, r in suma.iterrows()]
    sd = s[s["tipo_bosque"] == TODOS].groupby("anio")[[f"{d}_ha" for d in DESTINOS]].sum(min_count=1).reindex(anios)
    destino_tot = [[_num(v, 1) for v in r] for _, r in sd.iterrows()]
    tendencias = {}
    for _, r in tend.iterrows():
        tendencias.setdefault(str(r["unidad"]), {})[r["tipo_bosque"]] = [_num(r["tendencia_ha_anio"]),
                                                                         _num(r["tendencia_pct_anio"], 3)]
    sin_enc = (s[s["tipo_bosque"] == TODOS].groupby("anio")["bosque_sin_encadenar_ha"].sum()
               .reindex(anios).round(1).tolist() if "bosque_sin_encadenar_ha" in s.columns else None)

    # Bosque de cada año: parte de la celda con bosque, en 5 clases (0 nada, 1 <25 %, ... 4 >=75 %)
    def densidad(c):
        for t in range(N):
            frac = ((c >> t) & 1).mean(axis=(1, 3))
            yield np.where(frac == 0, 0, 1 + np.searchsorted(CORTES_DENSIDAD, frac, side="right")).astype(np.uint8)
    imgs_bosque = [_png_clases(a) for a in leer_por_celdas(carpeta / "bosque_por_anio.tif", f, densidad, N)]

    # Año de pérdida: el más reciente de la celda, como índice t del año (1..N-1)
    codigos = np.zeros(256, dtype=np.uint8)
    for t in range(1, N):
        codigos[anios[t] - 2000] = t

    def ultimo(c):
        yield codigos[c.max(axis=(1, 3))]
    img_perdida = _png_clases(leer_por_celdas(carpeta / "anio_perdida.tif", f, ultimo)[0], paso=25)
    exactitud = {k: ({"global": v.get("exactitud_global"), "kappa": v.get("kappa"),
                      "prueba": v.get("muestras_prueba")} if v else None)
                 for k, v in (meta.get("destino") or {}).items()}
    return {"anios": anios, "clave": cola, "umbral": round(float(meta["umbral_ndvi"]), 2),
            "escenas": [meta["escenas"].get(str(a)) for a in anios],
            "incendios": meta.get("incendios_por_periodo"), "zona_ha": meta.get("zona_forestal_ha"),
            "clases": meta.get("clases_forestales"), "campos": list(CAMPOS_SERIE.values()),
            "filas": filas, "tot": tot, "destino": destino, "destino_tot": destino_tot,
            "destinos": DESTINOS, "tend": tendencias, "sin_encadenar": sin_enc, "exactitud": exactitud,
            "img_bosque": imgs_bosque, "img_perdida": img_perdida, "paso_perdida": 25,
            "fecha": meta.get("fecha")}


def preparar_unidades(ruta, campo, nombres, malla):
    import geopandas as gpd
    from shapely.geometry import MultiPolygon, Polygon
    (alto, ancho), f, (izq, abajo, der, arriba), crs = malla
    tam = 10 * f  # metros por píxel de la malla reducida
    uni = gpd.read_file(ruta).to_crs(crs)
    uni = uni[uni[campo].astype(str).isin(nombres)].reset_index(drop=True)
    uni["geometry"] = uni.geometry.simplify(tam * 0.5, preserve_topology=True)

    def a_px(x, y):
        return (x - izq) / tam, (arriba - y) / tam

    def ruta_svg(geom):
        partes = []
        polis = geom.geoms if isinstance(geom, MultiPolygon) else [geom] if isinstance(geom, Polygon) else []
        for p in polis:
            for anillo in [p.exterior, *p.interiors]:
                pts = [a_px(x, y) for x, y in anillo.coords]
                partes.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + "Z")
        return "".join(partes)

    salida = []
    for _, r in uni.iterrows():
        g = r.geometry
        x0, y0, x1, y1 = g.bounds
        pt = g.representative_point()
        cx, cy = a_px(pt.x, pt.y)
        bx0, by1 = a_px(x0, y0)
        bx1, by0 = a_px(x1, y1)
        salida.append({"nombre": str(r[campo]), "d": ruta_svg(g), "c": [round(cx, 1), round(cy, 1)],
                       "bbox": [round(bx0, 1), round(by0, 1), round(bx1, 1), round(by1, 1)]})
    contorno = ruta_svg(uni.dissolve().geometry.iloc[0])
    return salida, contorno


def _validacion(carpeta):
    """Precisión y exhaustividad contra Hansen por periodo (validacion_estatal.csv), si existe."""
    if not carpeta or not (Path(carpeta) / "validacion_estatal.csv").exists():
        return None
    v = pd.read_csv(Path(carpeta) / "validacion_estatal.csv")
    return [{"periodo": str(r["periodo"]), "precision": _num(r.get("precision"), 3),
             "exhaustividad": _num(r.get("exhaustividad"), 3)} for _, r in v.iterrows()]


def main():
    p = argparse.ArgumentParser(description="Página HTML interactiva de una o varias corridas")
    p.add_argument("carpetas", nargs="+", help="carpetas de resultados (de correr o de serie)")
    p.add_argument("--unidades", required=True)
    p.add_argument("--campo-unidad", default="NOM_MUN")
    p.add_argument("--titulo", default="Estado de México")
    p.add_argument("--ancho-px", type=int, default=2400, help="resolución del ráster en la página")
    p.add_argument("--validacion", help="carpeta de src/validar_hansen.py, para citar sus cifras en Alcances")
    p.add_argument("--salida", required=True)
    p.add_argument("--fragmento", action="store_true",
                   help="sin <html>/<head>/<body> (para publicarla como Artifact)")
    a = p.parse_args()

    periodos, carpeta_serie = {}, None
    for c in a.carpetas:
        claves = sorted(x.stem.removeprefix("balance_") for x in Path(c).glob("balance_*.csv"))
        if not claves:
            sys.exit(f"No hay balance_*.csv en {c}.")
        if list(Path(c).glob("serie_*.csv")):
            if carpeta_serie:
                sys.exit("Solo puede haber una carpeta de serie.")
            carpeta_serie = c
        for clave in claves:
            pp = preparar_periodo(c, clave, a.ancho_px)
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
    serie = preparar_serie(carpeta_serie, malla[1]) if carpeta_serie else None
    nombres = sorted({n for pp in periodos for n in pp["filas"]})
    unidades, contorno = preparar_unidades(a.unidades, a.campo_unidad, nombres, malla)
    for pp in periodos:
        del pp["_malla"], pp["_ventana"]
    (alto, ancho), f = malla[0], malla[1]
    datos = {"titulo": a.titulo, "ancho": ancho, "alto": alto, "celda": 10 * f,
             "minimo": BOSQUE_MINIMO_HA, "campos": list(CAMPOS.values()),
             "campos_tipo": list(CAMPOS_TIPO.values()), "tipos": TIPOS_ORDEN,
             "unidades": unidades, "contorno": contorno, "periodos": periodos, "serie": serie,
             "validacion": _validacion(a.validacion)}

    plantilla = (Path(__file__).resolve().parent / "plantilla_mapa.html").read_text(encoding="utf-8")
    articulo = "del" if a.titulo.lower().startswith("estado") else "de"
    html = (plantilla.replace("__NOMBRE__", f"Masa forestal {articulo} {a.titulo}")
            .replace("__TITULO__", a.titulo)
            .replace("__DATOS__", json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")))
    if not a.fragmento:
        html = ('<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                + html.replace("<!--FIN_HEAD-->", "</head>\n<body>") + "\n</body>\n</html>\n")
    else:
        html = html.replace("<!--FIN_HEAD-->", "")
    Path(a.salida).parent.mkdir(parents=True, exist_ok=True)
    Path(a.salida).write_text(html, encoding="utf-8")
    print(f"Página en {Path(a.salida).resolve()} ({len(html.encode()) / 1e6:.1f} MB, {len(periodos)} "
          f"comparación(es){', con serie ' + serie['clave'] if serie else ''})")


if __name__ == "__main__":
    main()
