"""Núcleo y M1/M2 · tropiezos de interfaz del sprint 1 (S2-02f, P-13 a P-18)."""
from decimal import Decimal

import pytest

from dictamen import juridico, tecnico
from nucleo.demo import completar_requisitos, cuadro_en_municipio
from nucleo.pasos import siguiente_paso
from recepcion import servicios

pytestmark = pytest.mark.django_db


def _paso(usuario, exp):
    exp.refresh_from_db()
    p = siguiente_paso(usuario, exp)
    return p["texto"] if p else None


def _poligono(usuarios, exp):
    from django.utils import timezone

    servicios.registrar_poligono(usuarios["del_amecameca"], exp, cuadro_en_municipio(exp.predio.municipio, 6),
                                 "dibujo", "delegacion", "Brigada", timezone.localdate())


def test_nucleo_p13_siguiente_paso_en_cada_relevo(nueva_solicitud, usuarios):
    deleg, dirc, jur, comite = (usuarios[u] for u in ("del_amecameca", "dir_drff", "juridica", "comite"))
    exp = nueva_solicitud(superficie_solicitada_ha=Decimal("6"))
    assert _paso(deleg, exp) == "Revisar requisitos"
    assert _paso(dirc, exp) is None and _paso(usuarios["del_toluca"], exp) is None
    completar_requisitos(deleg, exp)
    assert _paso(deleg, exp) == "Levantar polígono"
    _poligono(usuarios, exp)
    assert _paso(deleg, exp) == "Enviar a la Dirección"
    servicios.enviar_a_direccion(deleg, exp)
    assert _paso(dirc, exp) == "Validar expediente" and _paso(deleg, exp) is None
    plano = exp.revisiones.get(requisito__clave="CC-REQ-13")
    aviso = servicios.validar_expediente(dirc, exp, [plano.pk])
    assert _paso(deleg, exp) == "Registrar la notificación del aviso de faltantes"
    servicios.registrar_notificacion(deleg, aviso)
    assert _paso(deleg, exp) == "Revisar requisitos"
    completar_requisitos(deleg, exp)
    assert _paso(deleg, exp) == "Reenviar a la Dirección"
    servicios.enviar_a_direccion(deleg, exp)
    servicios.validar_expediente(dirc, exp)
    assert _paso(dirc, exp) == "Elaborar el dictamen técnico" and _paso(jur, exp) == "Elaborar el dictamen jurídico"
    tecnico.dictaminar(dirc, exp, "factible", "Bien")
    assert _paso(dirc, exp) is None
    juridico.dictaminar(jur, exp, "procedente", "Bien")
    p = siguiente_paso(comite, exp)
    assert p["texto"] == "Llevar a sesión de aprobación" and f"ejercicio={exp.ejercicio_id}" in p["url"]


def test_nucleo_p13_boton_en_el_encabezado_del_expediente(client, nueva_solicitud, contrasena):
    exp = nueva_solicitud()
    client.login(username="del_amecameca", password=contrasena)
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=documentos").content.decode()
    assert 'data-prueba="siguiente-paso"' in html and "Revisar requisitos" in html


def test_nucleo_p14_aviso_de_poligono_pendiente_al_enviar(client, nueva_solicitud, usuarios, contrasena):
    exp = nueva_solicitud()
    completar_requisitos(usuarios["del_amecameca"], exp)
    client.login(username="del_amecameca", password=contrasena)
    url = f"/recepcion/expediente/{exp.folio}/?pestana=requisitos"
    assert 'data-prueba="aviso-poligono"' in client.get(url).content.decode()
    _poligono(usuarios, exp)
    assert 'data-prueba="aviso-poligono"' not in client.get(url).content.decode()


def test_nucleo_p15_aviso_de_faltantes_enlaza_al_requisito(client, nueva_solicitud, usuarios, contrasena):
    exp = nueva_solicitud()
    completar_requisitos(usuarios["del_amecameca"], exp)
    servicios.enviar_a_direccion(usuarios["del_amecameca"], exp)
    plano = exp.revisiones.get(requisito__clave="CC-REQ-13")
    servicios.validar_expediente(usuarios["dir_drff"], exp, [plano.pk])
    client.login(username="del_amecameca", password=contrasena)
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=validacion").content.decode()
    assert f'?pestana=requisitos#req-{plano.pk}"' in html
    assert f'id="req-{plano.pk}"' in client.get(f"/recepcion/expediente/{exp.folio}/?pestana=requisitos").content.decode()


def test_nucleo_p16_llevar_a_sesion_desde_la_bandeja_de_la_secretaria(client, nueva_solicitud, usuarios, contrasena):
    from dictamen import sesiones
    from dictamen.models import TipoSesion
    from nucleo.models import Estado, Expediente

    from .fixtures_m2 import fecha_sesion

    exp = nueva_solicitud()
    Expediente.objects.filter(pk=exp.pk).update(estado=Estado.objects.get(clave="dictaminada"))
    client.login(username="comite", password=contrasena)
    html = client.get("/bandeja/").content.decode()
    assert 'data-prueba="por-sesionar"' in html and f"sesiones/nueva/?tipo=aprobacion&amp;ejercicio={exp.ejercicio_id}" in html
    nueva = client.get(f"/dictamen/sesiones/nueva/?tipo=aprobacion&ejercicio={exp.ejercicio_id}").content.decode()
    assert f'value="{exp.ejercicio_id}" selected' in nueva
    sesion = sesiones.crear_sesion(usuarios["comite"], exp.ejercicio, TipoSesion.APROBACION, fecha_sesion(6), "Sala",
                                   "Listados")
    assert f"/dictamen/sesiones/{sesion.pk}/" in client.get("/bandeja/").content.decode()  # la abierta, no una nueva


def test_nucleo_p17_todos_los_mios_visible_con_conteos(client, nueva_solicitud, usuarios, contrasena):
    from nucleo.models import Estado, Expediente

    exp = nueva_solicitud()
    Expediente.objects.filter(pk=exp.pk).update(estado=Estado.objects.get(clave="no_factible"))
    client.login(username="del_amecameca", password=contrasena)
    r = client.get("/bandeja/")
    html = r.content.decode()
    assert r.context["total_por_atender"] == 0 and r.context["total_todos"] == 1
    assert 'id="cuenta-todos">1<' in html and 'data-prueba="bandeja-vacia"' in html and "«Todos los míos»" in html
    parcial = client.get("/bandeja/?alcance=todos", HTTP_HX_REQUEST="true", HTTP_HX_TARGET="tabla-bandeja").content.decode()
    assert exp.folio in parcial and 'hx-swap-oob="true"' in parcial


def test_nucleo_p18_acuses_y_documentos_se_ven_o_se_descargan(client, nueva_solicitud, usuarios, contrasena):
    exp = nueva_solicitud()
    completar_requisitos(usuarios["del_amecameca"], exp)
    acuse, doc = exp.acuses.first(), exp.documentos.first()
    client.login(username="del_amecameca", password=contrasena)
    ver = client.get(f"/acuses/{acuse.folio}/")
    bajar = client.get(f"/acuses/{acuse.folio}/?descargar=1")
    assert ver["Content-Disposition"].startswith("inline") and bajar["Content-Disposition"].startswith("attachment")
    assert f'{acuse.folio}.pdf' in bajar["Content-Disposition"] and b"".join(bajar.streaming_content)[:4] == b"%PDF"
    assert client.get(f"/documentos/{doc.pk}/?descargar=1")["Content-Disposition"].startswith("attachment")
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=documentos").content.decode()
    assert f'/acuses/{acuse.folio}/?descargar=1' in html and 'data-prueba="descargar-acuse"' in html
    client.login(username="del_toluca", password=contrasena)
    assert client.get(f"/acuses/{acuse.folio}/?descargar=1").status_code == 404
