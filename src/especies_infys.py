"""Especies registradas por municipio en el INFyS 2015-2020 (HU-7.5, CF-DEV-05 de las Tablas v12).

Lee los CSV de datos/edomex/infys/ (ver su LEEME.md: salen del archivo INFyS_2015_2020_Mexico.xlsx que
CONAFOR publica en IDEFOR) y arma el agregado que usa la página: por municipio, las especies con su
nombre científico, nombre común, género, familia, número de árboles y de conglomerados, lo identificado
solo a género aparte, y la situación del municipio en el inventario (con registros, conglomerado sin
arbolado, sin conglomerado).

Solo sale el agregado por municipio: nunca los registros por árbol, ni las coordenadas ni los
identificadores de los conglomerados.

Uso suelto (muestra el resumen):  python src/especies_infys.py [--nombres municipios.gpkg] [--salida archivo.json]
Para rehacer los CSV de origen, ver «Especies del inventario» en el README.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

CARPETA = Path("datos/edomex/infys")
ARBOLADO = "arbolado_edomex_2015_2020.csv"
COBERTURA = "cobertura_municipios_2015_2020.csv"
FUENTE = "Inventario Nacional Forestal y de Suelos 2015–2020 (CONAFOR)"
SITUACIONES = ["con_registros", "conglomerado_sin_arbolado", "sin_conglomerado"]
TEXTO_SITUACION = {
    "con_registros": "Con registros",
    "conglomerado_sin_arbolado": "Conglomerado sin arbolado",
    "sin_conglomerado": "Sin conglomerado",
}


def normalizar(nombre: str) -> str:
    """Nombre sin acentos, en minúsculas y sin signos ni espacios repetidos, para empatar variantes."""
    s = unicodedata.normalize("NFKD", str(nombre))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.casefold()).strip()


def empatar(nombres_fuente, nombres_pagina):
    """{nombre de la fuente: nombre de la página}. Exacto primero y, si no, sin acentos ni mayúsculas.
    Falla con un mensaje claro si algún nombre de la fuente o de la página queda sin pareja."""
    pagina = list(nombres_pagina)
    por_norm = {}
    for n in pagina:
        por_norm.setdefault(normalizar(n), []).append(n)
    ambiguos = {k: v for k, v in por_norm.items() if len(v) > 1}
    if ambiguos:
        sys.exit(f"Municipios de la página con nombres que solo difieren en acentos o mayúsculas: {ambiguos}")
    exactos = set(pagina)
    pares, sin_pareja = {}, []
    for n in sorted(set(nombres_fuente)):
        if n in exactos:
            pares[n] = n
        elif normalizar(n) in por_norm:
            pares[n] = por_norm[normalizar(n)][0]
        else:
            sin_pareja.append(n)
    if sin_pareja:
        sys.exit("Municipios del inventario que no empatan con los de la página: "
                 f"{sin_pareja}. Revisa los nombres en {CARPETA / COBERTURA} y en la capa de municipios.")
    faltan = sorted(set(pagina) - set(pares.values()))
    if faltan:
        sys.exit(f"Municipios de la página que no aparecen en la cobertura del inventario: {faltan}.")
    return pares


def _nombres_comunes(serie: pd.Series) -> str:
    """Nombres comunes distintos, del más frecuente al menos; cada celda puede traer varios con «;»."""
    cuenta: dict[str, int] = {}
    for celda, n in serie.value_counts().items():
        for nombre in str(celda).split(";"):
            nombre = nombre.strip()
            if nombre and not nombre.upper().startswith("INFYS"):
                cuenta[nombre] = cuenta.get(nombre, 0) + int(n)
    return "; ".join(sorted(cuenta, key=lambda k: (-cuenta[k], k)))


def construir(carpeta=CARPETA, nombres_pagina=None):
    """El agregado por municipio. `nombres_pagina`: los municipios de la página (si se da, se empatan
    con los del inventario y se usan sus nombres)."""
    carpeta = Path(carpeta)
    for f in (ARBOLADO, COBERTURA):
        if not (carpeta / f).exists():
            sys.exit(f"Falta {carpeta / f}. Ver datos/edomex/infys/LEEME.md o «Especies del inventario» en el README.")
    arb = pd.read_csv(carpeta / ARBOLADO)
    cob = pd.read_csv(carpeta / COBERTURA)
    pares = empatar(set(cob["NOM_MUN"]) | set(arb["municipio"]),
                    nombres_pagina if nombres_pagina is not None else cob["NOM_MUN"])
    arb["_m"] = arb["municipio"].map(pares)
    cob["_m"] = cob["NOM_MUN"].map(pares)
    if cob["_m"].duplicated().any():
        sys.exit("Dos municipios de la cobertura empatan con el mismo de la página.")
    claves = arb.groupby("_m")["cve_mun_inegi"].first().to_dict()

    municipios = {}
    for _, c in cob.sort_values("_m").iterrows():
        m = c["_m"]
        a = arb[arb["_m"] == m]
        reg = {"situacion": c["estado"], "cgl": [int(c["cgl_total"]), int(c["cgl_muestreados"]), int(c["cgl_con_arbolado"])]}
        if m in claves:
            reg["clave"] = str(int(claves[m]))
        if c["estado"] == "con_registros":
            esp, gen, ident = a[a["nivel"] == "especie"], a[a["nivel"] == "genero"], a[a["nivel"] == "desconocido"]
            if len(a) != int(c["n_arboles"]) or a["id_conglomerado"].nunique() != int(c["cgl_con_arbolado"]):
                sys.exit(f"{m}: el arbolado ({len(a)} árboles, {a['id_conglomerado'].nunique()} conglomerados) no "
                         f"coincide con la cobertura ({int(c['n_arboles'])}, {int(c['cgl_con_arbolado'])}).")

            def filas(df):
                out = []
                for (nombre, gen_, fam), g in df.groupby(["especie", "genero", "familia"]):
                    out.append([nombre, _nombres_comunes(g["nombre_comun"]), fam, gen_, len(g), int(g["id_conglomerado"].nunique())])
                return sorted(out, key=lambda r: (-r[4], r[0]))
            reg.update({"anios": sorted(int(x) for x in a["anio"].unique()), "arboles": len(a), "a_especie": len(esp), "solo_genero": len(gen), "sin_identificar": len(ident),
                        "especies": filas(esp), "generos": filas(gen)})
        elif len(a):
            sys.exit(f"{m} dice «{c['estado']}» pero tiene árboles en el arbolado.")
        municipios[m] = reg

    cuenta = {s: sum(1 for r in municipios.values() if r["situacion"] == s) for s in SITUACIONES}
    resumen = {"municipios": len(municipios), "situacion": cuenta, "arboles": int(len(arb)),
               "a_especie": int((arb["nivel"] == "especie").sum()), "solo_genero": int((arb["nivel"] == "genero").sum()),
               "sin_identificar": int((arb["nivel"] == "desconocido").sum()),
               "especies_distintas": int(arb.loc[arb["nivel"] == "especie", "especie"].nunique()),
               "generos_distintos": int(arb.loc[arb["nivel"] == "genero", "especie"].nunique()),
               "conglomerados": [int(cob["cgl_total"].sum()), int(cob["cgl_muestreados"].sum()), int(cob["cgl_con_arbolado"].sum())]}
    resumen["pct_a_especie"] = round(resumen["a_especie"] / resumen["arboles"], 4)
    meta = {"fuente": FUENTE, "periodo": "2015–2020", "anios_campo": sorted(int(x) for x in arb["anio"].unique()),
            "malla_km": 5,
            "nota": "Muestreo en una malla de 5 km: es la lista de lo registrado, no un inventario completo.",
            "licencia": "La licencia de uso de estos datos está por confirmar.",
            "textos_situacion": TEXTO_SITUACION}
    return {**meta, "resumen": resumen, "municipios": municipios,
            "empate": {"exactos": sum(1 for k, v in pares.items() if k == v), "por_variante": {k: v for k, v in pares.items() if k != v}}}


def main():
    p = argparse.ArgumentParser(description="Agregado de especies por municipio del INFyS 2015-2020")
    p.add_argument("--carpeta", default=str(CARPETA))
    p.add_argument("--nombres", help="capa de municipios (gpkg) con los nombres de la página; por defecto, los de la cobertura")
    p.add_argument("--campo-unidad", default="NOM_MUN")
    p.add_argument("--salida", help="escribe el JSON aquí")
    a = p.parse_args()
    nombres = None
    if a.nombres:
        import geopandas as gpd
        nombres = gpd.read_file(a.nombres)[a.campo_unidad].astype(str).tolist()
    d = construir(a.carpeta, nombres)
    r = d["resumen"]
    print(f"{d['fuente']}: {r['municipios']} municipios; situación {r['situacion']}; {r['arboles']} árboles "
          f"({r['pct_a_especie'] * 100:.1f} % a especie); {r['especies_distintas']} especies y {r['generos_distintos']} géneros distintos.")
    if d["empate"]["por_variante"]:
        print("Empatados por variante de nombre:", d["empate"]["por_variante"])
    if a.salida:
        Path(a.salida).write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
