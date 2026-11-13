"""Lectura y revisión de polígonos (HU-1.3): GeoJSON, KML, Shapefile en zip o dibujo en el mapa."""
import json
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path

from django.contrib.gis.gdal import DataSource, GDALException, OGRGeometry, SpatialReference
from django.contrib.gis.geos import GEOSException, GEOSGeometry, MultiPolygon, Polygon
from django.core.exceptions import ValidationError

SRID_TRABAJO = 32614  # UTM 14N: superficie en hectáreas
EXTENSIONES = {".geojson": "geojson", ".json": "geojson", ".kml": "kml", ".zip": "shp"}


def _a_multipoligono(geoms):
    poligonos = []
    for g in geoms:
        if isinstance(g, Polygon):
            poligonos.append(g)
        elif isinstance(g, MultiPolygon):
            poligonos.extend(list(g))
        elif g.geom_type == "GeometryCollection":
            poligonos.extend(p for p in g if isinstance(p, Polygon))
    if not poligonos:
        raise ValidationError("El archivo no contiene ningún polígono (solo puntos o líneas).")
    return MultiPolygon(poligonos, srid=4326)


def _de_ogr(geom_ogr, srs):
    geom_ogr.coord_dim = 2
    if srs is not None:
        geom_ogr.srs = srs
        if srs.srid != 4326:
            geom_ogr.transform(4326)
    geos = geom_ogr.geos
    geos.srid = 4326
    return geos


def leer_archivo(archivo):
    """Lee un archivo subido y devuelve (MultiPolygon en EPSG:4326, origen)."""
    nombre = Path(archivo.name).name
    ext = Path(nombre).suffix.lower()
    if ext not in EXTENSIONES:
        raise ValidationError("Formato no admitido. Use GeoJSON (.geojson/.json), KML (.kml) o Shapefile en .zip.")
    origen = EXTENSIONES[ext]
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / nombre
        with open(ruta, "wb") as f:
            for parte in archivo.chunks():
                f.write(parte)
        if origen == "shp":
            try:
                with zipfile.ZipFile(ruta) as z:
                    shp = [n for n in z.namelist() if n.lower().endswith(".shp") and not n.startswith("__MACOSX")]
            except zipfile.BadZipFile:
                raise ValidationError("El archivo .zip está dañado.")
            if not shp:
                raise ValidationError("El .zip no trae ningún archivo .shp.")
            ruta_gdal = f"/vsizip/{ruta}/{shp[0]}"
        else:
            ruta_gdal = str(ruta)
        try:
            fuente = DataSource(ruta_gdal)
        except GDALException:
            raise ValidationError("No se pudo leer el archivo como capa geográfica.")
        geoms = []
        for capa in fuente:
            srs = capa.srs
            if srs is None and origen == "shp":
                srs = None  # sin .prj: se revisa abajo si parecen coordenadas UTM
            for elemento in capa:
                g = elemento.geom.clone()
                if srs is None and origen == "shp" and abs(g.extent[0]) > 180:
                    g.srs = SpatialReference(SRID_TRABAJO)
                    g.transform(4326)
                    geos = g.geos
                    geos.srid = 4326
                    geoms.append(geos)
                    continue
                geoms.append(_de_ogr(g, srs))
    return _a_multipoligono(geoms), origen


def leer_geojson_texto(texto):
    """Geometría GeoJSON (Geometry, Feature o FeatureCollection) dibujada en el mapa."""
    try:
        datos = json.loads(texto)
    except (TypeError, json.JSONDecodeError):
        raise ValidationError("El dibujo no es un GeoJSON válido.")
    if datos.get("type") == "FeatureCollection":
        geometrias = [f["geometry"] for f in datos.get("features", []) if f.get("geometry")]
    elif datos.get("type") == "Feature":
        geometrias = [datos["geometry"]]
    else:
        geometrias = [datos]
    geoms = []
    for g in geometrias:
        try:
            geos = GEOSGeometry(json.dumps(g), srid=4326)
        except (GEOSException, ValueError, GDALException):
            raise ValidationError("El dibujo no es un GeoJSON válido.")
        geoms.append(geos)
    return _a_multipoligono(geoms)


def revisar_validez(geom):
    if not geom.valid:
        raise ValidationError(f"La geometría no es válida ({geom.valid_reason}). Corrija el polígono "
                              "(por ejemplo, lados que se cruzan) y vuelva a cargarlo.")
    if geom.empty:
        raise ValidationError("El polígono está vacío.")


def superficie_ha(geom):
    utm = geom.transform(SRID_TRABAJO, clone=True)
    return Decimal(utm.area / 10000).quantize(Decimal("0.0001"))


def ubicacion_en_municipio(geom, municipio):
    """('dentro'|'parcial'|'fuera', aviso)."""
    mun = municipio.geom
    if mun.contains(geom):
        return "dentro", ""
    if not mun.intersects(geom):
        return "fuera", f"El polígono está fuera del municipio de {municipio.nombre}. Revise el archivo o el municipio del predio."
    fuera = geom.difference(mun)
    pct = 100 * superficie_ha(fuera) / max(superficie_ha(geom), Decimal("0.0001")) if not fuera.empty else 0
    if pct < Decimal("0.5"):
        # Diferencias por la simplificación del límite municipal (tolerancia de ~40 m).
        return "dentro", ""
    return "parcial", f"El {pct:.1f} % del polígono queda fuera del municipio de {municipio.nombre}."


def traslape_pct(nuevo, anterior):
    """Porcentaje del polígono anterior que cubre el nuevo (en UTM)."""
    a = anterior.transform(SRID_TRABAJO, clone=True)
    n = nuevo.transform(SRID_TRABAJO, clone=True)
    if a.area == 0:
        return Decimal("0")
    inter = a.intersection(n).area
    union = a.union(n).area
    return Decimal(100 * inter / union).quantize(Decimal("0.01"))
