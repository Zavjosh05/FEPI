"""Recorrido de los tropiezos de interfaz del sprint 1 ya corregidos (S2-02f, P-13 a P-18), con Playwright.
Los datos se preparan con los servicios; lo que se comprueba es lo que ve y hace cada unidad en pantalla."""
from decimal import Decimal

import pytest
from playwright.sync_api import expect

from nucleo.demo import completar_requisitos
from nucleo.models import Ejercicio, Estado, Expediente, Municipio, Usuario
from recepcion import servicios

pytestmark = pytest.mark.navegador


def _solicitud(nombre="Predio Tropiezos"):
    cc = Ejercicio.objects.get(programa__clave="CC", anio=2026)
    datos = servicios.DatosSolicitud(
        ejercicio=cc, municipio=Municipio.objects.get(nombre="Amecameca"), nombre_predio=nombre,
        tipo_persona=cc.tipos_persona.get(clave="fisica"), modalidad=cc.modalidades.get(clave="reforestacion"),
        solicitante_nombre="Persona de Prueba", solicitante_tipo="fisica", superficie_solicitada_ha=Decimal("6"))
    return servicios.registrar_solicitud(Usuario.objects.get(username="del_amecameca"), datos)


def test_recorrido_s2_02_tropiezos_p13_a_p18(datos_e2e, page, live_server, entrar, captura):
    base = live_server.url
    deleg = Usuario.objects.get(username="del_amecameca")
    exp = _solicitud()
    completar_requisitos(deleg, exp)

    # P-13 y P-14: botón del siguiente paso y aviso de polígono pendiente en el panel de envío.
    entrar("del_amecameca")
    page.goto(f"{base}/recepcion/expediente/{exp.folio}/?pestana=requisitos")
    expect(page.locator("[data-prueba=siguiente-paso] a")).to_have_text("Levantar polígono")
    expect(page.locator("[data-prueba=aviso-poligono]")).to_be_visible()
    captura("s2_02_p13_p14_siguiente_paso_y_aviso_de_poligono")

    # P-18: el acuse se descarga (no solo se abre).
    page.goto(f"{base}/recepcion/expediente/{exp.folio}/?pestana=documentos")
    with page.expect_download() as descarga:
        page.locator("[data-prueba=descargar-acuse]").first.click()
    archivo = descarga.value
    assert archivo.suggested_filename.startswith("AC-") and archivo.suggested_filename.endswith(".pdf")
    with open(archivo.path(), "rb") as f:
        assert f.read(4) == b"%PDF"
    captura("s2_02_p18_descarga_de_acuses")

    # P-15: el aviso de faltantes lleva a la fila del requisito.
    servicios.enviar_a_direccion(deleg, exp)
    plano = exp.revisiones.get(requisito__clave="CC-REQ-13")
    servicios.validar_expediente(Usuario.objects.get(username="dir_drff"), exp, [plano.pk])
    page.goto(f"{base}/recepcion/expediente/{exp.folio}/?pestana=validacion")
    page.click("[data-prueba=faltantes-aviso] a[data-requisito='CC-REQ-13']")
    page.wait_for_url(f"**pestana=requisitos#req-{plano.pk}")
    expect(page.locator(f"#req-{plano.pk}")).to_be_in_viewport()
    captura("s2_02_p15_enlace_del_aviso_al_requisito")

    # P-17: «Todos los míos» visible, con conteo y aviso cuando no hay nada por atender.
    Expediente.objects.filter(pk=exp.pk).update(estado=Estado.objects.get(clave="no_factible"))
    page.goto(f"{base}/bandeja/")
    expect(page.locator("[data-prueba=bandeja-vacia]")).to_contain_text("Todos los míos")
    page.click("label[for=alcance-todos]")
    expect(page.locator("#tabla-bandeja")).to_contain_text(exp.folio)
    expect(page.locator("#alcance-todos")).to_be_checked()
    page.mouse.move(0, 0)  # sin el cursor encima, para que la captura muestre el botón elegido
    page.wait_for_timeout(400)  # transición de color del botón
    captura("s2_02_p17_todos_los_mios")

    # P-16: la Secretaría Técnica lleva lo dictaminado a la sesión de aprobación desde su bandeja.
    otro = _solicitud("Predio Dictaminado")
    Expediente.objects.filter(pk=otro.pk).update(estado=Estado.objects.get(clave="dictaminada"))
    entrar("comite")
    expect(page.locator("[data-prueba=por-sesionar]")).to_contain_text("1")
    captura("s2_02_p16_bandeja_de_la_secretaria")
    page.click("[data-prueba=llevar-a-sesion]")
    page.wait_for_url("**/dictamen/sesiones/nueva/**")
    expect(page.locator("#id_ejercicio")).to_have_value(str(otro.ejercicio_id))
