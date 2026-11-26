"""HU-1.3 · Ubicación del predio."""
import io
import json
import zipfile
from datetime import date

import pytest
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from nucleo.demo import cuadro_en_municipio
from nucleo.models import Ejercicio, Municipio
from recepcion import geometria, servicios

from .conftest import historia

pytestmark = pytest.mark.django_db


def _registrar(usuarios, exp, geom, **extra):
    datos = dict(origen="dibujo", levantado_por="delegacion", responsable="Brigada de campo",
                 fecha_levantamiento=date(2026, 3, 10))
    datos.update(extra)
    return servicios.registrar_poligono(usuarios["del_amecameca"], exp, geom, **datos)


def test_hu_1_3_criterios_del_modelo(modelo):
    criterios = historia(modelo, "HU-1.3")["criterios"]
    assert len(criterios) == 3 and "trazabilidad" in criterios[2]


def test_hu_1_3_existe_poligono_asociado_al_expediente(nueva_solicitud, usuarios):
    """Criterio 1: existe un polígono asociado al expediente del predio, con superficie en hectáreas."""
    exp = nueva_solicitud()
    pol = _registrar(usuarios, exp, cuadro_en_municipio(exp.predio.municipio, 10))
    assert servicios.poligono_vigente(exp) == pol
    assert abs(float(pol.superficie_ha) - 10) < 0.05  # EPSG:32614
    assert pol.ubicacion_municipio == "dentro" and pol.aviso == ""
    assert exp.eventos.filter(tipo="poligono").exists()


def test_hu_1_3_si_el_poligono_cambia_de_lugar_existen_el_anterior_y_el_nuevo(nueva_solicitud, usuarios):
    """Criterio 2: si el polígono cambia de lugar, existen el anterior y el nuevo."""
    exp = nueva_solicitud()
    mun = exp.predio.municipio
    primero = _registrar(usuarios, exp, cuadro_en_municipio(mun, 4))
    with pytest.raises(ValidationError, match="motivo"):
        _registrar(usuarios, exp, cuadro_en_municipio(mun, 4, (800, 0)))
    segundo = _registrar(usuarios, exp, cuadro_en_municipio(mun, 4, (800, 0)), motivo_cambio="Cambio de área")
    primero.refresh_from_db()
    assert exp.poligonos.count() == 2
    assert not primero.vigente and segundo.vigente and segundo.anterior == primero
    assert segundo.tipo_cambio == "cambio_lugar" and segundo.traslape_anterior_pct == 0


def test_hu_1_3_correccion_en_el_mismo_lugar_tambien_conserva_el_anterior(nueva_solicitud, usuarios):
    exp = nueva_solicitud()
    mun = exp.predio.municipio
    _registrar(usuarios, exp, cuadro_en_municipio(mun, 4))
    segundo = _registrar(usuarios, exp, cuadro_en_municipio(mun, 4.4, (10, 0)), motivo_cambio="Ajuste GPS")
    assert segundo.tipo_cambio == "correccion" and exp.poligonos.count() == 2


def test_hu_1_3_geometria_invalida_se_rechaza(nueva_solicitud, usuarios):
    exp = nueva_solicitud()
    c = cuadro_en_municipio(exp.predio.municipio, 4)[0].coords[0]
    moño = MultiPolygon(Polygon((c[0], c[2], c[1], c[3], c[0]), srid=4326), srid=4326)  # lados que se cruzan
    with pytest.raises(ValidationError, match="no es válida"):
        _registrar(usuarios, exp, moño)
    assert not exp.poligonos.exists()


def test_hu_1_3_poligono_fuera_del_municipio_avisa(nueva_solicitud, usuarios):
    exp = nueva_solicitud()
    fuera = cuadro_en_municipio(Municipio.objects.get(nombre="Toluca"), 4)
    pol = _registrar(usuarios, exp, fuera)
    assert pol.ubicacion_municipio == "fuera" and "fuera del municipio de Amecameca" in pol.aviso


def test_hu_1_3_lectura_de_geojson_kml_y_shapefile(catalogos, tmp_path):
    mun = Municipio.objects.get(nombre="Amecameca")
    geom = cuadro_en_municipio(mun, 6)
    gj = json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": json.loads(geom.geojson)}]})
    leido, origen = geometria.leer_archivo(SimpleUploadedFile("predio.geojson", gj.encode()))
    assert origen == "geojson" and abs(float(geometria.superficie_ha(leido)) - 6) < 0.05

    coords = " ".join(f"{x},{y},0" for x, y in geom[0].coords[0])
    kml = f"""<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>
      <Placemark><name>Predio</name><Polygon><outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates>
      </LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>"""
    leido, origen = geometria.leer_archivo(SimpleUploadedFile("predio.kml", kml.encode()))
    assert origen == "kml" and abs(float(geometria.superficie_ha(leido)) - 6) < 0.05


def test_hu_1_3_shapefile_en_zip(catalogos, tmp_path):
    mun = Municipio.objects.get(nombre="Amecameca")
    geom = cuadro_en_municipio(mun, 5).transform(32614, clone=True)
    contenido = _shapefile_zip(geom)
    leido, origen = geometria.leer_archivo(SimpleUploadedFile("predio.zip", contenido))
    assert origen == "shp" and abs(float(geometria.superficie_ha(leido)) - 5) < 0.05
    assert leido.srid == 4326 and mun.geom.contains(leido)


def test_hu_1_3_formato_no_admitido(catalogos):
    with pytest.raises(ValidationError, match="Formato no admitido"):
        geometria.leer_archivo(SimpleUploadedFile("predio.dwg", b"xx"))


def test_hu_1_3_programa_sin_poligono_no_lo_admite(nueva_solicitud, usuarios):
    """Guardabosques (PEG) no usa polígono: la regla viene del catálogo del programa."""
    exp = nueva_solicitud()
    peg = Ejercicio.objects.get(programa__clave="PEG", anio=2026)
    exp.ejercicio.programa.usa_poligono = False
    exp.ejercicio.programa.save()
    with pytest.raises(ValidationError, match="no usa polígono"):
        _registrar(usuarios, exp, cuadro_en_municipio(exp.predio.municipio, 2))
    assert not peg.programa.usa_poligono


def test_hu_1_3_pantalla_carga_archivo_y_dibujo(client, nueva_solicitud, contrasena):
    exp = nueva_solicitud()
    client.login(username="del_amecameca", password=contrasena)
    geom = cuadro_en_municipio(exp.predio.municipio, 3)
    r = client.post(f"/recepcion/expediente/{exp.folio}/poligono/", {
        "archivo": SimpleUploadedFile("p.geojson", geom.geojson.encode()), "levantado_por": "prestador",
        "responsable": "Prestador SC", "prestador_rfn": "RFN-MEX-123", "fecha_levantamiento": "2026-03-10"})
    assert r.status_code == 302
    pol = servicios.poligono_vigente(exp)
    assert pol.origen == "geojson" and pol.prestador.rfn == "RFN-MEX-123" and pol.archivo
    dibujo = cuadro_en_municipio(exp.predio.municipio, 3, (2000, 0)).geojson
    r = client.post(f"/recepcion/expediente/{exp.folio}/poligono/", {
        "dibujo": dibujo, "levantado_por": "delegacion", "responsable": "Brigada",
        "fecha_levantamiento": "2026-03-11", "motivo_cambio": "Se cambió el área"})
    assert exp.poligonos.count() == 2 and servicios.poligono_vigente(exp).origen == "dibujo"
    datos = client.get(f"/recepcion/expediente/{exp.folio}/poligonos.json").json()
    assert len(datos["poligonos"]["features"]) == 2
    assert client.get(f"/recepcion/expediente/{exp.folio}/?pestana=ubicacion").status_code == 200


def test_hu_1_3_vista_previa_del_archivo_sin_registrar(client, nueva_solicitud, usuarios, contrasena):
    """Al elegir el archivo, la pantalla lo muestra en el mapa con su superficie y ubicación; no se guarda nada."""
    exp = nueva_solicitud()
    mun = exp.predio.municipio
    url = f"/recepcion/expediente/{exp.folio}/poligono/vista-previa/"
    client.login(username="del_amecameca", password=contrasena)
    r = client.post(url, {"archivo": SimpleUploadedFile("p.geojson", cuadro_en_municipio(mun, 5).geojson.encode())})
    datos = r.json()
    assert r.status_code == 200 and datos["geometria"]["type"] == "MultiPolygon"
    assert abs(datos["superficie_ha"] - 5) < 0.05 and datos["ubicacion"] == "dentro" and not datos["pide_motivo"]
    assert not exp.poligonos.exists()
    _registrar(usuarios, exp, cuadro_en_municipio(mun, 4))
    otro = cuadro_en_municipio(Municipio.objects.get(nombre="Toluca"), 4).geojson.encode()
    datos = client.post(url, {"archivo": SimpleUploadedFile("p.geojson", otro)}).json()
    assert datos["pide_motivo"] and datos["tipo_cambio"] == "Cambio de lugar" and datos["traslape_pct"] == 0
    assert datos["ubicacion"] == "fuera" and "fuera del municipio de Amecameca" in datos["aviso"]
    assert exp.poligonos.count() == 1
    r = client.post(url, {"archivo": SimpleUploadedFile("p.txt", b"hola")})
    assert r.status_code == 400 and "Formato no admitido" in r.json()["error"]
    assert client.get(url).status_code == 405
    client.login(username="dir_drff", password=contrasena)            # solo la Delegación registra polígonos
    r = client.post(url, {"archivo": SimpleUploadedFile("p.geojson", cuadro_en_municipio(mun, 5).geojson.encode())})
    assert r.status_code in (400, 403, 404)


def _shapefile_zip(geom_utm):
    """Arma a mano un shapefile de un polígono (shp, shx, dbf, prj) y lo comprime en zip."""
    import struct

    from django.contrib.gis.gdal import SpatialReference

    anillo = list(geom_utm[0].coords[0])
    if Polygon(anillo).area and _area_con_signo(anillo) > 0:   # el shapefile pide el exterior en sentido horario
        anillo = anillo[::-1]
    xs, ys = [p[0] for p in anillo], [p[1] for p in anillo]
    caja = struct.pack("<4d", min(xs), min(ys), max(xs), max(ys))
    contenido = struct.pack("<i", 5) + caja + struct.pack("<2i", 1, len(anillo)) + struct.pack("<i", 0)
    contenido += b"".join(struct.pack("<2d", x, y) for x, y in anillo)
    palabras = len(contenido) // 2

    def encabezado(longitud_palabras):
        return (struct.pack(">7i", 9994, 0, 0, 0, 0, 0, longitud_palabras) + struct.pack("<2i", 1000, 5) + caja
                + struct.pack("<4d", 0, 0, 0, 0))

    shp = encabezado(50 + 4 + palabras) + struct.pack(">2i", 1, palabras) + contenido
    shx = encabezado(50 + 4) + struct.pack(">2i", 50, palabras)
    dbf = struct.pack("<4BIHH20x", 3, 126, 1, 1, 1, 32 + 32 + 1, 1 + 4)
    dbf += b"ID".ljust(11, bytes(1)) + b"N" + bytes(4) + bytes([4, 0]) + bytes(14) + bytes([0x0D])
    dbf += b"    1" + bytes([0x1A])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("predio.shp", shp)
        z.writestr("predio.shx", shx)
        z.writestr("predio.dbf", dbf)
        z.writestr("predio.prj", SpatialReference(32614).wkt)
    return buffer.getvalue()


def _area_con_signo(anillo):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(anillo, anillo[1:])) / 2


def test_hu_1_3_trazabilidad(nueva_solicitud, usuarios):
    """Criterio 3: el alta del polígono y el paso del anterior a «no vigente» quedan en el historial con su usuario."""
    exp = nueva_solicitud()
    mun = exp.predio.municipio
    primero = _registrar(usuarios, exp, cuadro_en_municipio(mun, 4))
    _registrar(usuarios, exp, cuadro_en_municipio(mun, 4, (800, 0)), motivo_cambio="Cambio de área")
    cambios = list(primero.history.order_by("history_date", "history_id").values_list("vigente", "history_user__username"))
    assert cambios == [(True, "del_amecameca"), (False, "del_amecameca")]
