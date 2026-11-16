"""HU-5.3 · Recorrido de la entrega de cheques de PSAHEM: la Fiduciaria emite y envía el cheque, la Delegación lo entrega a la
persona y se ve el vencimiento del cobro en 3 meses."""
from datetime import date

from playwright.sync_api import expect

from pruebas.fixtures_m2 import psa, peg, validada  # noqa: F401
from pruebas.fixtures_m3 import aprobadas, contratadas, delegado_de, en_delegacion, modelo_validado, notificadas  # noqa: F401
from pruebas.fixtures_m5 import aceptada, con_soportes, remitida, solicitada  # noqa: F401


def test_hu_5_3_recorrido_emision_envio_y_entrega_del_cheque(  # noqa: F811
        datos_e2e, remitida, usuarios, page, live_server, entrar, captura):
    exp, sol = remitida()
    pestana = f"{live_server.url}/recepcion/expediente/{exp.folio}/?pestana=pagos"

    # La Fiduciaria ve el pago remitido y emite el cheque de la ministración.
    entrar("fiduciaria")
    expect(page.locator("[data-prueba=panel-cheques-por-emitir]")).to_contain_text(exp.folio)
    captura("hu_5_3_01_bandeja_de_la_fiduciaria_pagos_por_emitir")
    page.goto(pestana)
    page.fill("#id_numero", "CHQ-FIPASAHEM-0001")
    page.fill("#id_fecha_emision", date.today().isoformat())
    page.click("[data-prueba=form-emision-m1] button:has-text('Emitir el cheque')")
    expect(page.locator("[data-prueba=cheque-m1]")).to_contain_text("CHQ-FIPASAHEM-0001")
    captura("hu_5_3_02_cheque_emitido_a_nombre_de_la_persona_y_de_su_ministracion")

    # Lo envía a la Delegación: fecha, hora y acuse.
    page.click("button:has-text('Enviar el cheque a la Delegación')")
    expect(page.locator("[data-prueba=envio-cheque]")).to_contain_text("Enviado a")
    captura("hu_5_3_03_cheque_enviado_a_la_delegacion_con_fecha_y_hora")

    # La Delegación lo tiene por entregar y por notificar a la persona.
    entrar(delegado_de(usuarios, exp).username)
    expect(page.locator("[data-prueba=panel-cheques-por-entregar]")).to_contain_text(exp.folio)
    expect(page.locator("[data-prueba=panel-notificaciones]")).to_contain_text("Aviso de pago")
    captura("hu_5_3_04_bandeja_de_la_delegacion_cheque_por_entregar")
    page.goto(pestana)
    page.fill("#id_recibe_nombre", exp.solicitante.nombre)
    page.click("[data-prueba=form-entrega-m1] button:has-text('Registrar la entrega')")
    expect(page.locator("[data-prueba=entrega-cheque]")).to_contain_text("Entregado el")
    expect(page.locator("[data-prueba=cobro-cheque]")).to_contain_text("Debe cobrarlo a más tardar")
    captura("hu_5_3_05_cheque_entregado_con_fecha_hora_y_vencimiento_del_cobro")

    # Lista de cheques con el vencimiento del cobro.
    page.goto(f"{live_server.url}/pagos/cheques/")
    expect(page.locator("[data-prueba=cheques-por-cobrar]")).to_contain_text("CHQ-FIPASAHEM-0001")
    captura("hu_5_3_06_cheques_entregados_por_cobrar_con_su_vencimiento")
