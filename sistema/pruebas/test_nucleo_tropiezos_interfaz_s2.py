"""Núcleo, M3 y M5 · tropiezos de interfaz del recorrido del sprint 2 (cierre del sprint 2, P-23 a P-31)."""
import re

import pytest
from django.core.exceptions import ValidationError

from contrato import publicacion
from nucleo.models import Evento, bandeja
from pagos import pagos, solicitudes

from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de
from .fixtures_m5 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def test_nucleo_p23_bitacora_cronologica_con_desempate_por_registro(client, nueva_solicitud, usuarios, contrasena):
    from django.utils import timezone

    exp = nueva_solicitud()
    ahora = timezone.now().replace(microsecond=0)
    for i in range(3):          # tres renglones del mismo instante, registrados en este orden
        Evento.registrar(exp, usuarios["del_amecameca"], "prueba", f"Renglón {i}", fecha_hora=ahora)
    client.login(username="del_amecameca", password=contrasena)
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=bitacora").content.decode()
    assert 'data-prueba="orden-bitacora"' in html
    assert html.index("Renglón 0") < html.index("Renglón 1") < html.index("Renglón 2")
    fechas = re.findall(r"<td class=\"text-nowrap\">(\d\d/\d\d/\d{4} \d\d:\d\d:\d\d)</td>", html)
    from datetime import datetime
    ordenadas = [datetime.strptime(f, "%d/%m/%Y %H:%M:%S") for f in fechas]
    assert ordenadas == sorted(ordenadas)


def test_nucleo_p24_todas_las_paginas_publicas_enlazan_a_iniciar_sesion(client, aprobadas, usuarios):
    sesion, (exp,) = aprobadas("PS", cuantas=1)
    publicacion.publicar(usuarios["dir_drff"], sesion)
    for url in ("/contrato/resultados/", f"/contrato/resultados/PS/{exp.ejercicio.anio}/"):
        html = client.get(url).content.decode()
        assert html.count('data-prueba="enlace-entrar"') == 1 and "/entrar/" in html
    assert 'data-prueba="enlace-entrar"' not in client.get("/entrar/").content.decode()


def test_nucleo_p25_el_folio_del_panel_abre_el_aviso_por_registrar(client, aprobadas, usuarios, contrasena):
    sesion, (exp,) = aprobadas("PS", cuantas=1)
    publicacion.publicar(usuarios["dir_drff"], sesion)
    aviso = exp.notificaciones.filter(tipo="resultados").get()
    client.login(username=delegado_de(usuarios, exp).username, password=contrasena)
    panel = client.get("/bandeja/").content.decode()
    assert f"/contrato/notificaciones/?ver=pendientes&aviso={aviso.pk}#notificacion-{aviso.pk}" in panel
    pagina = client.get(f"/contrato/notificaciones/?ver=pendientes&aviso={aviso.pk}").content.decode()
    fila = pagina[pagina.index(f'id="notificacion-{aviso.pk}"'):]
    assert "<details open>" in fila[:fila.index("</tr>")]


def test_nucleo_p26_psahem_por_atender_de_la_secretaria_incluye_lo_que_debe_remitir(aceptada, usuarios):
    exp, sol = aceptada("PSA")
    assert exp in bandeja(usuarios["comite"]) and exp not in bandeja(usuarios["finanzas"])
    pagos.remitir_a_fiduciaria(usuarios["comite"], sol)
    assert exp not in bandeja(usuarios["comite"])


def test_nucleo_p26_otros_programas_no_cambian_la_bandeja_de_la_secretaria(aceptada, usuarios):
    exp, _ = aceptada("CC")
    assert exp not in bandeja(usuarios["comite"]) and exp in bandeja(usuarios["finanzas"])


def test_nucleo_p27_el_plazo_de_remision_dice_cumplido_despues_de_remitir(client, remitida, usuarios, contrasena):
    exp, sol = remitida()
    client.login(username="comite", password=contrasena)
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=pagos").content.decode()
    zona = html[html.index('data-prueba="plazo-remision"'):]
    assert "cumplido en plazo" in zona[:900] and "por vencer" not in zona[:900]


def test_nucleo_p28_el_vale_tiene_un_solo_nombre_y_al_surtirse_se_avisa_el_estado(client, contratadas, catalogo_planta,
                                                                                    usuarios, contrasena):
    from contrato import planta

    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("PS")
    vale = planta.emitir_vale(delegado_de(usuarios, exp), exp, vivero, [(esp["Pino patula"], 4400)])
    client.login(username="vivero", password=contrasena)
    detalle = client.get(f"/contrato/vales/{vale.folio}/").content.decode()
    assert "Vale de Salida de Planta" in detalle
    r = client.post(f"/contrato/vales/{vale.folio}/salida/", {"especie": esp["Pino patula"].pk, "cantidad": 4400},
                    follow=True)
    cuerpo = r.content.decode()
    assert "pasó a «Planta entregada»" in cuerpo


def test_nucleo_p29_la_pagina_publica_muestra_las_fechas_no_la_clave_de_la_sesion(client, aprobadas, usuarios):
    sesion, (exp,) = aprobadas("PS", cuantas=1)
    publicacion.publicar(usuarios["dir_drff"], sesion)
    html = client.get(f"/contrato/resultados/PS/{exp.ejercicio.anio}/").content.decode()
    from django.utils import timezone
    assert sesion.numero not in html
    assert f"sesión del {timezone.localtime(sesion.fecha_hora):%d/%m/%Y}" in html and "Publicados el" in html


def test_nucleo_p30_el_soporte_faltante_se_dice_una_vez_y_con_la_unidad(client, con_soportes, usuarios, contrasena):
    exp = con_soportes("CC", comprobante=False)
    client.login(username="dir_drff", password=contrasena)
    r = client.post(f"/pagos/solicitud/{exp.folio}/1/enviar/", follow=True)
    cuerpo = r.content.decode()
    assert cuerpo.count("No se puede enviar la solicitud") == 1 and "lo resuelve la Delegación" in cuerpo
    assert 'data-prueba="faltan-soportes-m1"' not in cuerpo
    with pytest.raises(ValidationError, match="lo resuelve la Delegación"):
        solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 1)


def test_nucleo_p31_registrar_cobro_con_rotulo_y_ayuda_solo_para_quien_puede(client, entregado, usuarios, contrasena):
    exp, cheque = entregado()
    url = f"/recepcion/expediente/{exp.folio}/?pestana=pagos"
    client.login(username="fiduciaria", password=contrasena)
    html = client.get(url).content.decode()
    assert "Registrar que fue cobrado" in html and "Cobro del cheque" in html and "Fecha del cobro" in html
    assert "ya lo cobró" in html
    client.login(username="dir_drff", password=contrasena)
    assert "Registrar que fue cobrado" not in client.get(url).content.decode()
