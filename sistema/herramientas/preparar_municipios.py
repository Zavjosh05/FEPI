"""Convierte la capa de municipios de IDEFOR a un GeoJSON simplificado para el catálogo.

Uso (desde la raíz del repositorio, con el entorno de la calculadora):

    .venv\\Scripts\\python.exe sistema\\herramientas\\preparar_municipios.py

Entrada: datos/edomex/municipios_edomex.gpkg (125 municipios, campos NOM_ENT y NOM_MUN).
Salida:  sistema/datos/municipios_edomex.geojson (EPSG:4326).

La capa de IDEFOR no trae la clave INEGI del municipio. Se asigna una clave interna
provisional (``M001`` … ``M125``, en orden alfabético del nombre) que se puede reemplazar
por la clave INEGI cuando se tenga la capa con ``CVE_MUN``.
"""
from pathlib import Path

import geopandas as gpd

RAIZ = Path(__file__).resolve().parents[2]
ENTRADA = RAIZ / "datos" / "edomex" / "municipios_edomex.gpkg"
SALIDA = RAIZ / "sistema" / "datos" / "municipios_edomex.geojson"

# Tolerancia en metros (se simplifica en UTM 14N para no deformar).
TOLERANCIA_M = 40


def main():
    capa = gpd.read_file(ENTRADA)
    capa = capa.sort_values("NOM_MUN").reset_index(drop=True)
    capa["clave"] = [f"M{i + 1:03d}" for i in range(len(capa))]
    capa["nombre"] = capa["NOM_MUN"].str.strip()
    utm = capa.to_crs(32614)
    utm["geometry"] = utm.geometry.simplify(TOLERANCIA_M, preserve_topology=True).buffer(0)
    salida = utm.to_crs(4326)[["clave", "nombre", "geometry"]]
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    salida.to_file(SALIDA, driver="GeoJSON", COORDINATE_PRECISION=5)
    print(f"{len(salida)} municipios -> {SALIDA} ({SALIDA.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
