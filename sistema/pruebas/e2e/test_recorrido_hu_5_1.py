"""HU-5.1 · Recorrido de la solicitud de pago: oficio y comprobante en la Delegación, envío con sus soportes desde el área
responsable (y su rechazo si falta uno) y la solicitud en la bandeja de Administración y Finanzas."""
from playwright.sync_api import expect

from nucleo.demo import _pdf_demo
from pagos import solicitudes
from pruebas.fixtures_m3 import aprobadas, contratadas, delegado_de, en_delegacion, modelo_validado, notificadas  # noqa: F401


def test_hu_5_1_recorrido_oficio_comprobante_y_envio_de_la_solicitud(  # noqa: F811
        datos_e2e, contratadas, usuarios, page, live_server, entrar, captura, tmp_path):
    _, (completa, incompleta) = contratadas("CC", cuantas=2)
    solicitudes.emitir_oficio(delegado_de(usuarios, incompleta), incompleta)  # a esta le falta el comprobante
    cuenta = tmp_path / "estado_de_cuenta.pdf"
    cuenta.write_bytes(_pdf_demo("Estado de cuenta"))
    pestana = f"{live_server.url}/recepcion/expediente/{completa.folio}/?pestana=pagos"

    # La Delegación ve el contrato firmado por emitir su oficio y lo emite.
    entrar(delegado_de(usuarios, completa).username)
    expect(page.locator("[data-prueba=panel-oficios-por-emitir]")).to_contain_text(completa.folio)
    captura("hu_5_1_01_bandeja_de_la_delegacion_oficios_por_emitir")
    page.goto(pestana)
    expect(page.locator("[data-prueba=oficio-pago]")).to_contain_text("Emitir el oficio de solicitud de pago")
    page.click("[data-prueba=oficio-pago] button:has-text('Emitir el oficio')")
    expect(page.locator("[data-prueba=oficio-pago]")).to_contain_text("OFP-CC-2026-")
    captura("hu_5_1_02_oficio_de_la_delegacion_emitido_con_su_acuse")

    # Guarda el comprobante de la cuenta bancaria que pide CC para la primera ministración.
    page.set_input_files("#form-comprobante input[type=file]", str(cuenta))
    page.click("#form-comprobante button[type=submit]")
    expect(page.locator("[data-prueba=comprobante-cuenta]")).to_contain_text("Recibido el")
    captura("hu_5_1_03_comprobante_de_la_cuenta_bancaria_guardado")

    # El área responsable intenta enviar la solicitud a la que le falta el comprobante: el sistema no la envía y dice cuál falta.
    entrar("dir_drff")
    expect(page.locator("[data-prueba=panel-por-solicitar]")).to_contain_text(incompleta.folio)
    captura("hu_5_1_04_bandeja_del_area_responsable_ministraciones_por_solicitar")
    page.goto(f"{live_server.url}/recepcion/expediente/{incompleta.folio}/?pestana=pagos")
    expect(page.locator("[data-prueba=faltan-soportes-m1]")).to_contain_text("comprobante de la cuenta bancaria")
    page.click("[data-prueba=form-envio-m1] button")
    expect(page.locator(".alert-danger")).to_contain_text("No se puede enviar la solicitud: falta Comprobante de la cuenta bancaria")
    captura("hu_5_1_05_solicitud_incompleta_no_se_envia_y_dice_que_falta")

    # La solicitud con todos sus soportes se envía: fecha, hora y acuse.
    page.goto(pestana)
    expect(page.locator("[data-prueba=soportes-m1] .badge.text-bg-danger")).to_have_count(0)
    captura("hu_5_1_06_solicitud_con_todos_sus_soportes")
    page.click("[data-prueba=form-envio-m1] button")
    expect(page.locator("[data-prueba=envio-solicitud]")).to_contain_text("Enviada a Administración y Finanzas el")
    expect(page.locator("[data-prueba=estado-solicitud]").first).to_contain_text("Enviada")
    captura("hu_5_1_07_solicitud_enviada_con_fecha_hora_y_acuse")

    # Administración y Finanzas la recibe en su bandeja.
    entrar("finanzas")
    expect(page.locator("#tabla-bandeja")).to_contain_text(completa.folio)
    captura("hu_5_1_08_bandeja_de_administracion_y_finanzas_con_la_solicitud")
