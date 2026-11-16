"""HU-5.2 · Recorrido del pago de la ministración: Administración y Finanzas devuelve y acepta la solicitud, registra el pago
con su fecha y la persona recibe el aviso por la Delegación; en PSAHEM la Secretaría Técnica solicita el pago a la Fiduciaria."""
from datetime import date

from playwright.sync_api import expect

from pruebas.fixtures_m2 import psa, peg, validada  # noqa: F401
from pruebas.fixtures_m3 import aprobadas, contratadas, delegado_de, en_delegacion, modelo_validado, notificadas  # noqa: F401
from pruebas.fixtures_m5 import aceptada, con_soportes, solicitada  # noqa: F401


def test_hu_5_2_recorrido_revision_pago_aviso_y_remision_a_la_fiduciaria(  # noqa: F811
        datos_e2e, solicitada, aceptada, usuarios, page, live_server, entrar, captura):
    cc = solicitada("CC")
    psahem, solicitud_psa = aceptada("PSA")
    pestana_cc = f"{live_server.url}/recepcion/expediente/{cc.folio}/?pestana=pagos"

    # Administración y Finanzas recibe la solicitud y la devuelve con observaciones al área responsable.
    entrar("finanzas")
    expect(page.locator("[data-prueba=panel-por-revisar]")).to_contain_text(cc.folio)
    captura("hu_5_2_01_bandeja_de_administracion_y_finanzas_solicitudes_por_revisar")
    page.goto(pestana_cc)
    page.fill("[data-prueba=form-revision-m1] textarea", "El comprobante de la cuenta no es legible.")
    page.click("[data-prueba=form-revision-m1] button:has-text('Devolver')")
    expect(page.locator("[data-prueba=revision-m1]")).to_contain_text("Devuelta con observaciones")
    captura("hu_5_2_02_solicitud_devuelta_con_observaciones")

    # El área responsable la ve devuelta, la corrige y la reenvía.
    entrar("dir_drff")
    expect(page.locator("[data-prueba=panel-por-solicitar]")).to_contain_text("devuelta")
    page.goto(pestana_cc)
    expect(page.locator("[data-prueba=solicitud-devuelta]")).to_be_visible()
    captura("hu_5_2_03_el_area_responsable_ve_la_solicitud_devuelta")
    page.click("[data-prueba=form-envio-m1] button")
    expect(page.locator("[data-prueba=estado-solicitud]").first).to_contain_text("Enviada")

    # Administración y Finanzas la acepta y registra el pago: referencia, fecha e importe igual al solicitado.
    entrar("finanzas")
    page.goto(pestana_cc)
    page.click("[data-prueba=form-revision-m1] button:has-text('Aceptar')")
    expect(page.locator("[data-prueba=form-pago-m1]")).to_be_visible()
    captura("hu_5_2_04_solicitud_aceptada_lista_para_registrar_el_pago")
    page.fill("#id_referencia", "SPEI-2026-0001")
    page.fill("#id_fecha_pago", date.today().isoformat())
    page.click("[data-prueba=form-pago-m1] button:has-text('Registrar el pago')")
    expect(page.locator("[data-prueba=pago-m1]")).to_contain_text("Pagada")
    expect(page.locator("[data-prueba=fecha-pago]")).to_be_visible()
    captura("hu_5_2_05_pago_registrado_asociado_a_su_solicitud_con_fecha_y_acuse")

    # La persona recibe el aviso de pago por conducto de la Delegación.
    entrar(delegado_de(usuarios, cc).username)
    expect(page.locator("[data-prueba=panel-notificaciones]")).to_contain_text("Aviso de pago")
    captura("hu_5_2_06_la_delegacion_tiene_el_aviso_de_pago_por_notificar")

    # PSAHEM: la Secretaría Técnica solicita el pago a la Fiduciaria dentro de sus 5 días hábiles.
    entrar("comite")
    expect(page.locator("[data-prueba=panel-por-remitir]")).to_contain_text(psahem.folio)
    captura("hu_5_2_07_bandeja_de_la_secretaria_tecnica_pagos_por_solicitar_a_la_fiduciaria")
    page.goto(f"{live_server.url}/recepcion/expediente/{psahem.folio}/?pestana=pagos")
    expect(page.locator("[data-prueba=plazo-remision]")).to_contain_text("5 días hábiles")
    page.fill("#id_oficio", "ST-FIPASAHEM/001/2026")
    page.click("[data-prueba=form-remision-m1] button:has-text('Solicitar el pago')")
    expect(page.locator("[data-prueba=remision-m1]")).to_contain_text("en plazo")
    captura("hu_5_2_08_remision_a_la_fiduciaria_con_fecha_hora_y_acuse")

    # La Fiduciaria lo recibe en su bandeja.
    entrar("fiduciaria")
    expect(page.locator("#tabla-bandeja")).to_contain_text(psahem.folio)
    captura("hu_5_2_09_bandeja_de_la_fiduciaria_con_el_pago_remitido")
