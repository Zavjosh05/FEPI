"""Genera los archivos de datos de prueba del sprint 1 (polígonos, documentos y fichas de solicitudes).

Se corre desde la raíz del repositorio con el entorno de la Calculadora (geopandas, pyogrio, matplotlib):

    python datos_prueba/sprint_1/generar_datos_prueba.py

Los polígonos se construyen sobre la misma capa de municipios que carga el sistema
(`sistema/datos/municipios_edomex.geojson`) y en la proyección de trabajo (UTM 14N, EPSG:32614), igual que la
demostración, así que caen donde dice su nombre. Todo es ficticio y sin validez oficial.
"""
import csv
import math
import pathlib
import zipfile

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parents[2]
SALIDA = pathlib.Path(__file__).resolve().parent
UTM = 32614

municipios = gpd.read_file(RAIZ / "sistema" / "datos" / "municipios_edomex.geojson").to_crs(UTM)


def municipio(nombre):
    fila = municipios[municipios["nombre"] == nombre]
    assert len(fila) == 1, nombre
    return fila.geometry.iloc[0]


def centro(nombre):
    """El mismo punto que usa la demostración: un punto sobre la superficie del municipio."""
    return municipio(nombre).representative_point()


def cuadro(x, y, hectareas):
    h = math.sqrt(hectareas * 10000) / 2
    return Polygon([(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h), (x - h, y - h)])


def guardar(nombre, geometria, descripcion, formatos=("geojson",)):
    capa = gpd.GeoDataFrame({"nombre": [nombre], "descripcion": [descripcion]}, geometry=[geometria], crs=UTM)
    carpeta = SALIDA / "poligonos"
    carpeta.mkdir(exist_ok=True)
    wgs = capa.to_crs(4326)
    if "geojson" in formatos:
        wgs.to_file(carpeta / f"{nombre}.geojson", driver="GeoJSON")
    if "kml" in formatos:
        wgs.to_file(carpeta / f"{nombre}.kml", driver="KML")
    if "shp" in formatos:
        temporal = carpeta / f"_{nombre}"
        temporal.mkdir(exist_ok=True)
        wgs.to_file(temporal / f"{nombre}.shp", driver="ESRI Shapefile")
        with zipfile.ZipFile(carpeta / f"{nombre}_shapefile.zip", "w", zipfile.ZIP_DEFLATED) as z:
            for parte in sorted(temporal.iterdir()):
                z.write(parte, parte.name)
                parte.unlink()
        temporal.rmdir()
    return geometria.area / 10000


def poligonos():
    filas = []
    ame = municipio("Amecameca")
    c = centro("Amecameca")
    # 01: válido, dentro de Amecameca y lejos del polígono de la demostración (que está en Tlalmanalco).
    base = None
    for dx, dy in [(1500, 0), (-1500, 0), (0, 1500), (0, -1500), (1000, 1000)]:
        p = cuadro(c.x + dx, c.y + dy, 12)
        if ame.contains(p):
            base = (c.x + dx, c.y + dy)
            break
    assert base, "no se encontró un lugar dentro de Amecameca"
    p01 = cuadro(*base, 12)
    ha = guardar("01_amecameca_12ha", p01, "Predio válido de 12 ha dentro de Amecameca", ("geojson", "kml", "shp"))
    filas.append(("01_amecameca_12ha (.geojson, .kml, _shapefile.zip)", "Amecameca", ha,
                  "Primer polígono: se acepta, «Dentro del municipio». Los tres formatos dan la misma superficie."))
    # 02: corrección (se mueve 40 m: traslape alto con el anterior).
    p02 = cuadro(base[0] + 40, base[1] + 20, 12.5)
    ha = guardar("02_amecameca_correccion", p02, "Mismo predio corregido 40 m")
    filas.append(("02_amecameca_correccion.geojson", "Amecameca", ha,
                  "Cambio de polígono con motivo: el historial lo marca «Corrección» (traslape mayor a 50 %)."))
    # 03: cambio de lugar (2 km).
    for dx, dy in [(-2500, 0), (2500, 0), (0, 2500), (0, -2500)]:
        p03 = cuadro(base[0] + dx, base[1] + dy, 12)
        if ame.contains(p03):
            break
    ha = guardar("03_amecameca_cambio_de_lugar", p03, "Predio movido a 2.5 km")
    filas.append(("03_amecameca_cambio_de_lugar.geojson", "Amecameca", ha,
                  "Cambio de polígono con motivo: el historial lo marca «Cambio de lugar» (traslape menor a 50 %)."))
    # 04: a caballo del límite municipal (se guarda con aviso).
    borde = ame.exterior.interpolate(0.25, normalized=True) if ame.geom_type == "Polygon" else \
        max(ame.geoms, key=lambda g: g.area).exterior.interpolate(0.25, normalized=True)
    p04 = cuadro(borde.x, borde.y, 10)
    ha = guardar("04_fuera_del_municipio", p04, "Cuadro centrado en el límite de Amecameca")
    fuera = 100 * (1 - p04.intersection(ame).area / p04.area)
    filas.append(("04_fuera_del_municipio.geojson", "Amecameca", ha,
                  f"Se guarda con aviso: {fuera:.0f} % del polígono queda fuera del municipio."))
    # 05: inválido (moño que se cruza a sí mismo).
    x, y = base
    p05 = Polygon([(x - 150, y - 150), (x + 150, y + 150), (x + 150, y - 150), (x - 150, y + 150), (x - 150, y - 150)])
    gpd.GeoDataFrame({"nombre": ["05_invalido_se_cruza"]}, geometry=[p05], crs=UTM).to_crs(4326).to_file(
        SALIDA / "poligonos" / "05_invalido_se_cruza.geojson", driver="GeoJSON")
    filas.append(("05_invalido_se_cruza.geojson", "Amecameca", "—",
                  "Se rechaza: la geometría se cruza a sí misma (no es válida)."))
    # 06: traslapa con Los Encinos del Monte y La Joya Alta (demostración, Juchitepec).
    cj = centro("Juchitepec")
    p06 = cuadro(cj.x + 120, cj.y + 60, 6)
    ha = guardar("06_juchitepec_traslapa_demo", p06, "Predio en Juchitepec que se traslapa con la demostración")
    encinos, joya = cuadro(cj.x, cj.y, 9), cuadro(cj.x + 180, cj.y + 120, 5)
    filas.append(("06_juchitepec_traslapa_demo.geojson", "Juchitepec", ha,
                  f"El dictamen técnico muestra traslapes con Los Encinos del Monte (~{p06.intersection(encinos).area / 1e4:.1f} ha) "
                  f"y La Joya Alta (~{p06.intersection(joya).area / 1e4:.1f} ha)."))
    # 07: fuera del rango del programa (más de 200 ha).
    for dx, dy in [(0, 0), (1500, 0), (-1500, 0), (0, 1500), (0, -1500)]:
        p07 = cuadro(c.x + dx, c.y + dy, 250)
        if ame.contains(p07):
            break
    ha = guardar("07_amecameca_250ha_fuera_de_rango", p07, "Predio de 250 ha (el rango de CC es 1 a 200 ha)")
    filas.append(("07_amecameca_250ha_fuera_de_rango.geojson", "Amecameca", ha,
                  "El análisis del dictamen técnico dice «fuera» del rango de 1 a 200 ha."))
    return filas


def documentos():
    carpeta = SALIDA / "documentos"
    carpeta.mkdir(exist_ok=True)
    nombres = [
        ("solicitud_unica_FO-PB-501-A", "Solicitud Única (FO-PB-501-A)"),
        ("registro_de_informacion_FO-PB-502", "Formato de Registro de Información (FO-PB-502)"),
        ("identificacion_oficial", "Identificación oficial con fotografía"),
        ("comprobante_de_domicilio", "Comprobante de domicilio"),
        ("curp", "Clave Única de Registro de Población"),
        ("acreditacion_de_la_propiedad", "Acreditación de la propiedad o posesión del predio"),
        ("acta_de_asamblea", "Acta de asamblea del núcleo agrario"),
        ("documento_generico", "Documento de prueba para cualquier requisito"),
    ]
    for archivo, titulo in nombres:
        fig = plt.figure(figsize=(8.5, 11))
        fig.text(0.1, 0.9, "PROBOSQUE · DATOS DE PRUEBA", fontsize=11, color="#666")
        fig.text(0.1, 0.84, titulo, fontsize=16, weight="bold")
        fig.text(0.1, 0.78, "Documento ficticio para probar el sistema.\nNo tiene validez oficial.", fontsize=12)
        fig.text(0.5, 0.45, "DOCUMENTO DE PRUEBA", fontsize=40, color="#d33", alpha=0.25, rotation=30,
                 ha="center", va="center")
        fig.savefig(carpeta / f"{archivo}.pdf")
        plt.close(fig)
    return [n for n, _ in nombres]


def fichas():
    campos = ["escenario", "entra_como", "tipo_persona", "modalidad", "refrendo", "con_representante_legal",
              "municipio", "predio", "superficie_ha", "localidad", "persona_solicitante", "curp", "rfc", "telefono",
              "correo", "representante", "poligono", "resultado_esperado"]
    filas = [
        ["A. Camino completo", "del_amecameca", "Persona física", "Reforestación (de cuatro o más años)", "no", "no",
         "Amecameca", "Predio Las Palomas", "12", "San Diego Huehuecalco", "Teresa Aguilar Montes",
         "AUMT780214MMCGNR03", "AUMT780214AB1", "5550000001", "teresa.prueba@example.com", "",
         "01_amecameca_12ha", "Se registra con acuse y llega a «Aprobada» en la Lista de Personas Beneficiarias."],
        ["B. Faltantes y reenvío", "del_amecameca", "Persona física", "Plantación forestal comercial navideña (árboles de Navidad)",
         "no", "no", "Amecameca", "Rancho Los Abetos", "4", "Santa Isabel Chalma", "Felipe Robles Ibarra",
         "ROIF850930HMCBBL07", "ROIF850930CD2", "5550000002", "felipe.prueba@example.com", "", "",
         "La Dirección marca un faltante, la Delegación notifica y reenvía, y la Dirección valida."],
        ["C. Municipio de otra Delegación", "del_amecameca", "Persona física", "Reforestación (de cuatro o más años)",
         "no", "no", "Zinacantepec", "Predio El Capulín Alto", "6", "San Juan de las Huertas", "Laura Peña Ortiz",
         "PEOL900101MMCXRR04", "", "5550000003", "", "", "",
         "No se registra: el formulario avisa que lo atiende la Delegación Regional Forestal Toluca."],
        ["E. Núcleo agrario con traslape", "del_amecameca", "Núcleo agrario (ejido o comunidad)",
         "Reforestación (de cuatro o más años)", "no", "sí", "Juchitepec", "Ejido Juchitepec, paraje Las Cruces", "6",
         "Juchitepec", "Ejido Juchitepec", "", "", "5550000004", "",
         "Comisariado ejidal: Presidencia, Secretaría y Tesorería", "06_juchitepec_traslapa_demo",
         "El dictamen técnico muestra los traslapes con Los Encinos del Monte y La Joya Alta."],
        ["G. Persona en el Listado de Incumplidas", "del_valle", "Persona física", "Reforestación (de cuatro o más años)",
         "no", "no", "Villa de Allende", "Predio La Loma Seca", "8", "San Ildefonso", "Rogelio Bautista Núñez",
         "BANR600101HMCTXG09", "", "5550000005", "", "", "",
         "El cotejo del dictamen jurídico encuentra a la persona en el Listado de Incumplidas y no deja dictaminar procedente."],
        ["F. Fuera del rango del programa", "del_amecameca", "Persona física", "Reforestación (de cuatro o más años)",
         "no", "no", "Amecameca", "Predio Gran Ladera", "250", "Amecameca", "Óscar Nava Linares", "NALO700707HMCVNS06",
         "", "5550000006", "", "", "07_amecameca_250ha_fuera_de_rango",
         "El análisis del dictamen técnico marca la superficie fuera del rango de 1 a 200 ha."],
    ]
    with open(SALIDA / "fichas_solicitudes.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(campos)
        w.writerows(filas)
    return len(filas)


if __name__ == "__main__":
    resumen = poligonos()
    docs = documentos()
    n = fichas()
    with open(SALIDA / "poligonos" / "LEEME.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["archivo", "municipio", "superficie_ha", "que_debe_pasar"])
        for archivo, mun, ha, que in resumen:
            w.writerow([archivo, mun, ha if isinstance(ha, str) else f"{ha:.2f}", que])
    for fila in resumen:
        print(fila)
    print(len(docs), "documentos;", n, "fichas")
