"""Núcleo · prueba de volumen (G-02): con unos cientos de solicitudes generadas, las bandejas, el listado preliminar, la página pública
y las tablas largas responden con un número de consultas que no crece con el número de renglones, y sus tablas están limitadas.

Se excluye de las rápidas con ``-m "not volumen"`` (genera ~250 solicitudes: ~1 min 30 s)."""
import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from nucleo import generador
from nucleo.models import Expediente

pytestmark = [pytest.mark.django_db, pytest.mark.volumen]

PAGINAS = [
    ("dir_drff", "/bandeja/"), ("dir_drff", "/bandeja/?alcance=todos"), ("dir_drff", "/dictamen/listado/"),
    ("dir_drff", "/dictamen/sesiones/"), ("dir_drff", "/contrato/publicacion/"), ("dir_drff", "/contrato/contratos/"),
    ("dir_drff", "/contrato/firmas/"), ("dir_drff", "/contrato/vales/"), ("dir_drff", "/pagos/solicitudes/"),
    ("del_amecameca", "/bandeja/"), ("del_amecameca", "/bandeja/?alcance=todos"), ("del_amecameca", "/contrato/notificaciones/"),
    ("del_amecameca", "/contrato/firmas/"), ("del_amecameca", "/pagos/solicitudes/"), ("comite", "/bandeja/"),
    ("comite", "/dictamen/sesiones/"), ("comite", "/pagos/revision/"), ("juridica", "/bandeja/"), ("juridica", "/dictamen/incumplidas/"),
    ("finanzas", "/bandeja/"), ("finanzas", "/pagos/revision/"), ("fiduciaria", "/pagos/cheques/"), ("vivero", "/contrato/vivero/"),
    (None, "/contrato/resultados/"), (None, "/contrato/resultados/CC/2026/"), (None, "/contrato/resultados/PS/2026/"),
]
MAXIMO_CONSULTAS = 45
MAXIMO_RENGLONES = 320          # las tablas largas se limitan (la bandeja a 300 renglones; las demás, a menos)


def _medir(client, contrasena):
    medidas = {}
    for usuario, url in PAGINAS:
        client.logout()
        if usuario:
            client.login(username=usuario, password=contrasena)
        with CaptureQueriesContext(connection) as q:
            r = client.get(url)
        assert r.status_code == 200, (usuario, url, r.status_code)
        medidas[(usuario, url)] = (len(q), len(re.findall(rb"<tr[ >]", r.content)), len(r.content))
    return medidas


def test_nucleo_volumen_las_consultas_no_crecen_con_el_numero_de_solicitudes(catalogos, client, contrasena, capsys):
    generador.generar("CC", 24, 1)
    generador.generar("PS", 12, 1)
    chicas = _medir(client, contrasena)
    generador.generar("CC", 200, 2)
    generador.generar("PS", 40, 2)
    assert Expediente.objects.count() >= 270
    grandes = _medir(client, contrasena)
    with capsys.disabled():
        print("\nconsultas con ~36 solicitudes -> con ~276 (renglones de tabla, bytes):")
        for clave in PAGINAS:
            a, b = chicas[clave], grandes[clave]
            print(f"  {clave[0] or 'público':14} {clave[1]:42} {a[0]:3d} -> {b[0]:3d} consultas; {a[1]:4d} -> {b[1]:4d} renglones; {b[2]:7d} bytes")
    for clave in PAGINAS:
        (c_ant, _, _), (c_nuevo, renglones, tamano) = chicas[clave], grandes[clave]
        assert c_nuevo <= MAXIMO_CONSULTAS, f"{clave}: {c_nuevo} consultas"
        assert c_nuevo <= c_ant + 3, f"{clave}: {c_ant} consultas con pocas solicitudes y {c_nuevo} con muchas (una por renglón)"
        assert renglones <= MAXIMO_RENGLONES, f"{clave}: {renglones} renglones sin límite"


def test_nucleo_volumen_las_tablas_largas_se_limitan_y_lo_dicen(catalogos, client, contrasena, monkeypatch):
    from contrato.vistas import publicacion as vista_publica
    from dictamen.vistas import tecnico as vista_tecnico

    generador.generar("CC", 40, 3)
    monkeypatch.setattr(vista_tecnico, "LIMITE_LISTADO", 5)
    monkeypatch.setattr(vista_publica, "LIMITE_PUBLICO", 4)
    client.login(username="dir_drff", password=contrasena)
    html = client.get("/dictamen/listado/").content.decode()
    assert 'data-prueba="listado-recortado"' in html and html.count("<tr>") <= 5 + 2
    assert client.get("/dictamen/listado/?formato=csv").content.count(b"\n") >= 15      # el CSV trae todo
    client.logout()
    publica = client.get("/contrato/resultados/CC/2026/").content.decode()
    assert 'data-prueba="listado-recortado"' in publica and publica.count("<tr data-folio") <= 12
