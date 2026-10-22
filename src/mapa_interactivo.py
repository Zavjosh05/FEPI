#!/usr/bin/env python3
"""
Página HTML interactiva con los resultados de una o varias corridas
===================================================================

Arma un solo archivo HTML (sin servidor) para explorar el balance de masa forestal:

  - mapa con zoom y arrastre: el ráster de cambio (con capas que se prenden y apagan) o el
    cambio neto por unidad, en porcentaje;
  - al pasar o tocar una unidad, sus cifras; al elegirla, su detalle en todos los periodos;
  - selector de periodo (una corrida por periodo, p. ej. 2023 → 2024 y 2024 → 2025);
  - tabla ordenable de todas las unidades.

Todas las corridas deben ser de la misma zona (mismo --aoi), para que sus rásters coincidan.
Los datos van dentro del archivo; solo la librería D3 se carga de internet (cdnjs).

Uso (desde la raíz del repositorio):
    python src/mapa_interactivo.py resultados/edomex_2023_2024 resultados/edomex_2024_2025 \
        --unidades datos/edomex/municipios_edomex.gpkg --campo-unidad NOM_MUN \
        --titulo "Estado de México" --salida resultados/mapa_edomex.html

Con --fragmento escribe la página sin <html>/<head>/<body>, para publicarla como Artifact.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mapa_cambio import leer_cambio_agregado  # noqa: E402

BOSQUE_MINIMO_HA = 500
CAMPOS = {"bosque_base_ha": "base", "perdida_incendio_ha": "inc", "otras_perdidas_ha": "otras",
          "ganancia_ha": "gan", "bosque_afectado_por_fuego_ha": "afect", "bosque_actual_ha": "actual",
          "cambio_neto_ha": "neto"}


def _png_clases(arr) -> str:
    """Ráster de clases (0-4) como PNG en escala de grises (valor x 50), en data URI."""
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray((arr * 50).astype(np.uint8), mode="L").save(buf, "PNG", optimize=True)
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


def preparar_periodo(carpeta, ancho_px):
    carpeta = Path(carpeta)
    candidatos = sorted(carpeta.glob("balance_*.csv"))
    if len(candidatos) != 1:
        sys.exit(f"Se esperaba un balance_*.csv en {carpeta} y hay {len(candidatos)}.")
    clave = candidatos[0].stem.removeprefix("balance_")
    base, actual = (int(x) for x in clave.split("_"))
    bal = pd.read_csv(candidatos[0])
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
    ruta_inc = carpeta / "incendios_dnbr.csv"
    if ruta_inc.exists():
        i = pd.read_csv(ruta_inc)
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
            "etiqueta": f"{base} → {actual}", "meses": meses,
            "base_txt": f"{meses_corto} {base}" if preliminar else str(base),
            "actual_txt": f"{meses_corto} {actual}" if preliminar else str(actual),
            "corto": f"{str(base)[2:]}→{str(actual)[2:]}{'*' if preliminar else ''}", "sufijo": sufijo,
            "umbral": round(float(bal["umbral_ndvi"].iloc[0]), 2), "escenas": escenas,
            "tot": tot, "filas": filas, "incendios": inc, "notas": notas,
            "fuego_incompleto": any("incendios" in n for n in notas),
            "img": _png_clases(cambio), "_malla": (cambio.shape, f, limites, crs)}


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


def main():
    p = argparse.ArgumentParser(description="Página HTML interactiva de una o varias corridas")
    p.add_argument("carpetas", nargs="+", help="carpetas de resultados (una por periodo)")
    p.add_argument("--unidades", required=True)
    p.add_argument("--campo-unidad", default="NOM_MUN")
    p.add_argument("--titulo", default="Estado de México")
    p.add_argument("--ancho-px", type=int, default=2400, help="resolución del ráster en la página")
    p.add_argument("--salida", required=True)
    p.add_argument("--fragmento", action="store_true",
                   help="sin <html>/<head>/<body> (para publicarla como Artifact)")
    a = p.parse_args()

    periodos = [preparar_periodo(c, a.ancho_px) for c in a.carpetas]
    # Primero los balances anuales (los de un año, luego los más largos) y al final los preliminares
    periodos.sort(key=lambda x: (x["preliminar"], x["actual"] - x["base"], x["base"]))
    mallas = {(pp["_malla"][0], pp["_malla"][1], tuple(round(v) for v in pp["_malla"][2])) for pp in periodos}
    if len(mallas) > 1:
        sys.exit("Las corridas no tienen la misma malla (¿distinto --aoi?).")
    malla = periodos[0]["_malla"]
    nombres = sorted({n for pp in periodos for n in pp["filas"]})
    unidades, contorno = preparar_unidades(a.unidades, a.campo_unidad, nombres, malla)
    for pp in periodos:
        del pp["_malla"]
    (alto, ancho), f = malla[0], malla[1]
    datos = {"titulo": a.titulo, "ancho": ancho, "alto": alto, "celda": 10 * f,
             "minimo": BOSQUE_MINIMO_HA, "campos": list(CAMPOS.values()),
             "unidades": unidades, "contorno": contorno, "periodos": periodos}

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
    print(f"Página en {Path(a.salida).resolve()} ({len(html.encode()) / 1e6:.1f} MB, {len(periodos)} periodo(s))")


if __name__ == "__main__":
    main()
