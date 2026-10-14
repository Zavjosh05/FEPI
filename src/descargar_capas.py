#!/usr/bin/env python3
"""
Descarga de capas vectoriales del Estado de México - IDEFOR (CONAFOR)
=====================================================================

Baja del WFS de IDEFOR las capas que usa prototipo_masa_forestal.py para todo
el Estado de México. No pide cuenta. Se guardan en EPSG:4326, como las publica
IDEFOR (el prototipo las reproyecta solo).

    estado_mexico.gpkg            Límite estatal (INEGI 2025)
    municipios_edomex.gpkg        125 municipios (campos NOM_ENT, NOM_MUN)
    usv_serie7_edomex.gpkg        INEGI Uso de suelo y vegetación Serie VII, recortada al estado
    incendios_conafor_edomex.gpkg Polígonos de incendio CONAFOR que tocan el estado, todos los
                                  años en una sola capa (campo ANIO_CAPA). Así un balance que
                                  cruza de año (1-nov a 31-oct) tiene los incendios de ambos.
    descarga.json                 Fecha, filtros y número de polígonos de cada capa

Uso:
    python src/descargar_capas.py                       # todo; incendios 2019-2024
    python src/descargar_capas.py --anios 2023 2024     # solo esos años de incendios
    python src/descargar_capas.py --capas incendios     # solo una capa (si otra falló)

Notas sobre IDEFOR:
    - El filtro BBOX se manda con 'EPSG:4326' explícito; sin él GeoServer espera el orden
      lat/lon y no regresa nada.
    - Se pide por páginas y se verifica que lleguen todos los polígonos que reporta el servidor.
    - Todavía no hay capa de incendios 2025.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

WFS = "https://idefor.cnf.gob.mx/geoserver/ows"
BBOX_EDOMEX = (-100.62, 18.36, -98.59, 20.29)  # lon/lat con margen
PAGINA = 1000
SALIDA_DEFAULT = Path(__file__).resolve().parents[1] / "datos" / "edomex"

CAPA_ESTADO = "lim_estatal_inegi_2025"
CAPA_MUNICIPIOS = "municipios"
CAPA_USV = "cdv_usuev250svii_cnal_wgs84"
CAPAS_INCENDIOS = {
    2019: "_2019_incendios_forestales",
    2020: "_2020_incendios_forestales",
    2021: "_2021_incendios_forestales",
    2022: "_2022_incendios_forestales_wgs84",
    2023: "_2023_incendios_forestales_wgs84",
    2024: "_2024_incendios_forestales",
}
FILTRO_BBOX = "BBOX(the_geom,{},{},{},{},'EPSG:4326')".format(*BBOX_EDOMEX)


# --------------------------------------------------------------------------
# WFS
# --------------------------------------------------------------------------
def _pedir(params: dict, intentos: int = 3) -> bytes:
    query = urllib.parse.urlencode({"service": "WFS", "version": "2.0.0", **params},
                                   quote_via=urllib.parse.quote)
    for i in range(intentos):
        try:
            with urllib.request.urlopen(f"{WFS}?{query}", timeout=300) as r:
                return r.read()
        except OSError as e:  # incluye URLError y timeout
            if i == intentos - 1:
                raise
            print(f"    reintento {i + 1} ({e})")
            time.sleep(5 * (i + 1))


def contar(capa: str, filtro: str) -> int:
    xml = _pedir({"request": "GetFeature", "typeNames": f"geonode:{capa}",
                  "resultType": "hits", "CQL_FILTER": filtro}).decode("utf-8", "replace")
    m = re.search(r'numberMatched="(\d+)"', xml)
    if not m:
        raise RuntimeError(f"IDEFOR no respondió el conteo de {capa}: {xml[:300]}")
    return int(m.group(1))


def descargar(capa: str, filtro: str, campos: list[str] | None = None) -> gpd.GeoDataFrame:
    """Todos los polígonos de `capa` que cumplen `filtro` (CQL), por páginas."""
    total = contar(capa, filtro)
    print(f"  {capa}: {total} polígonos")
    feats, vistos = [], set()
    for inicio in range(0, total, PAGINA):
        params = {"request": "GetFeature", "typeNames": f"geonode:{capa}",
                  "outputFormat": "application/json", "CQL_FILTER": filtro,
                  "count": PAGINA, "startIndex": inicio}
        if campos:
            params["propertyName"] = ",".join(["the_geom", *campos])
        for f in json.loads(_pedir(params))["features"]:
            if f.get("id") not in vistos:
                vistos.add(f.get("id"))
                feats.append(f)
    if len(feats) != total:
        raise RuntimeError(f"{capa}: llegaron {len(feats)} de {total} polígonos")
    if not feats:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    return gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")


def guardar(gdf: gpd.GeoDataFrame, ruta: Path, registro: list, capa: str, filtro: str):
    gdf.to_file(ruta, driver="GPKG")
    registro.append({"archivo": ruta.name, "capa_idefor": capa, "filtro": filtro,
                     "poligonos": len(gdf)})
    print(f"    -> {ruta.name} ({len(gdf)} polígonos, {ruta.stat().st_size / 1e6:.1f} MB)")


# --------------------------------------------------------------------------
# Capas
# --------------------------------------------------------------------------
def capa_estado(salida, registro) -> gpd.GeoDataFrame:
    filtro = "CVE_ENT='15'"
    estado = descargar(CAPA_ESTADO, filtro, ["CVEGEO", "CVE_ENT", "NOMGEO"])
    if len(estado) != 1:
        raise RuntimeError(f"Se esperaba 1 polígono estatal, llegaron {len(estado)}")
    guardar(estado, salida / "estado_mexico.gpkg", registro, CAPA_ESTADO, filtro)
    return estado


def capa_municipios(salida, registro):
    filtro = "NOM_ENT='México'"
    mun = descargar(CAPA_MUNICIPIOS, filtro, ["NOM_ENT", "NOM_MUN"])
    if len(mun) != 125:
        print(f"    AVISO: se esperaban 125 municipios y llegaron {len(mun)}")
    guardar(mun, salida / "municipios_edomex.gpkg", registro, CAPA_MUNICIPIOS, filtro)


def capa_usv(salida, registro, estado):
    usv = descargar(CAPA_USV, FILTRO_BBOX, ["CLAVE", "DESCRIPCIO"])
    usv["geometry"] = usv.geometry.make_valid()
    usv = gpd.clip(usv, estado.geometry.make_valid(), keep_geom_type=True)
    usv = usv[~usv.geometry.is_empty].reset_index(drop=True)
    guardar(usv, salida / "usv_serie7_edomex.gpkg", registro, CAPA_USV,
            FILTRO_BBOX + " recortado al límite estatal")


def capa_incendios(salida, registro, estado, anios):
    limite = estado.geometry.make_valid().union_all()
    partes = []
    for anio in anios:
        inc = descargar(CAPAS_INCENDIOS[anio], FILTRO_BBOX)
        inc = inc[inc.geometry.notna() & inc.geometry.make_valid().intersects(limite)].copy()
        inc.insert(0, "ANIO_CAPA", anio)
        # La capa 2020 trae fechas con hora y zona (2020-04-03T12:00:00Z); mezcladas con las
        # de otros años rompen la lectura de fechas del prototipo. Se dejan como AAAA-MM-DD.
        for campo in ("FECHAINIC", "FECHALIQ"):
            if campo in inc.columns:
                inc[campo] = inc[campo].astype("string").str.slice(0, 10)
        print(f"    {len(inc)} tocan el Estado de México")
        partes.append(inc)
    todos = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs="EPSG:4326")
    capas = ", ".join(CAPAS_INCENDIOS[a] for a in anios)
    guardar(todos, salida / "incendios_conafor_edomex.gpkg", registro, capas,
            FILTRO_BBOX + " y que intersectan el límite estatal")


# --------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Descarga capas del Estado de México desde IDEFOR")
    p.add_argument("--salida", default=str(SALIDA_DEFAULT))
    p.add_argument("--capas", nargs="+", default=["municipios", "usv", "incendios"],
                   choices=["municipios", "usv", "incendios"],
                   help="el límite estatal siempre se descarga (se usa para recortar)")
    p.add_argument("--anios", nargs="+", type=int, default=sorted(CAPAS_INCENDIOS),
                   choices=sorted(CAPAS_INCENDIOS), help="años de incendios CONAFOR")
    a = p.parse_args()

    salida = Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    registro = []
    print(f"Descargando de {WFS}")
    estado = capa_estado(salida, registro)
    if "municipios" in a.capas:
        capa_municipios(salida, registro)
    if "usv" in a.capas:
        capa_usv(salida, registro, estado)
    if "incendios" in a.capas:
        capa_incendios(salida, registro, estado, sorted(a.anios))

    # Se conserva lo de descargas anteriores de otras capas
    ruta_meta = salida / "descarga.json"
    previas = json.loads(ruta_meta.read_text(encoding="utf-8"))["capas"] if ruta_meta.exists() else []
    hoy = datetime.now().isoformat(timespec="seconds")
    for r in registro:
        r["fecha_descarga"] = hoy
    nuevos = {r["archivo"] for r in registro}
    capas = [r for r in previas if r["archivo"] not in nuevos] + registro
    ruta_meta.write_text(json.dumps({"servicio": WFS, "capas": capas}, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"\nListo: {salida.resolve()}")


if __name__ == "__main__":
    main()
