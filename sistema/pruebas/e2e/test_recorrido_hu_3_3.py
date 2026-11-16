"""HU-3.3 · Recorrido de la firma del contrato en la Delegación, el señalamiento sin firma y la liberación del recurso."""
from datetime import timedelta

from django.core.management import call_command
from django.utils import timezone
from playwright.sync_api import expect

from nucleo.demo import _pdf_demo
from nucleo.models import Hito, Notificacion
from pruebas.fixtures_m3 import aprobadas, delegado_de, en_delegacion, modelo_validado, notificadas  # noqa: F401


def test_hu_3_3_recorrido_firma_en_la_delegacion_sin_firma_y_liberacion(  # noqa: F811
        datos_e2e, en_delegacion, usuarios, page, live_server, entrar, captura, tmp_path):
    sesion, (firmada, vencida) = en_delegacion("PS", cuantas=2)
    delegado = delegado_de(usuarios, firmada).username
    firmado = tmp_path / "contrato_firmado.pdf"
    firmado.write_bytes(_pdf_demo("Contrato firmado"))

    # La Delegación ve en su bandeja los contratos por firmar, con sus dos fechas y los días que faltan.
    entrar(delegado)
    expect(page.locator("[data-prueba=panel-por-firmar]")).to_be_visible()
    captura("hu_3_3_01_bandeja_de_la_delegacion_contratos_por_firmar")
    page.goto(f"{live_server.url}/contrato/firmas/")
    expect(page.locator("[data-prueba=por-firmar]")).to_contain_text(firmada.folio)
    expect(page.locator("[data-prueba=por-firmar]")).to_contain_text("Vence para liberar el recurso")
    captura("hu_3_3_02_contratos_por_firmar_con_las_dos_fechas")

    # Registra la firma: archivo, quién firma y verificación de firmas y sello.
    page.click(f"tr[data-folio='{firmada.folio}'] a:has-text('Registrar la firma')")
    expect(page.locator("#form-firma")).to_be_visible()
    page.fill("#id_firmante_nombre", "Abel Contreras Vega")
    page.set_input_files("#id_archivo", str(firmado))
    captura("hu_3_3_03_formulario_de_firma")
    page.click("button:has-text('Registrar la firma')")
    expect(page.locator("[data-prueba=verificacion]")).to_be_visible()  # no se recibe sin verificar
    captura("hu_3_3_04_sin_verificar_firmas_y_sello_no_se_recibe")
    page.check("#id_v_firma_persona")
    page.check("#id_v_firma_probosque")
    page.set_input_files("#id_archivo", str(firmado))
    page.click("button:has-text('Registrar la firma')")
    expect(page.locator("[data-prueba=firma-contrato]")).to_contain_text("Contrato firmado")
    expect(page.locator("[data-prueba=situacion-firma]")).to_contain_text("En la fecha programada")
    captura("hu_3_3_05_contrato_firmado_con_fecha_hora_y_acuse")

    # El otro contrato vence sin firma: lo señala la revisión de plazos.
    Hito.objects.filter(expediente=vencida, clave="publicacion_resultados").update(
        fecha_hora=timezone.now() - timedelta(days=40))
    Notificacion.objects.filter(expediente=vencida, tipo="resultados").update(
        notificada_en=timezone.now() - timedelta(days=40))
    call_command("revisar_plazos")

    # La Delegación ya no puede recibir esa firma.
    entrar(delegado_de(usuarios, vencida).username)
    page.goto(f"{live_server.url}/contrato/contratos/{vencida.folio}/firmar/")
    expect(page.locator("[data-prueba=sin-firma-no-se-recibe]")).to_contain_text("ya no se puede registrar")
    captura("hu_3_3_06_firma_rechazada_por_estar_senalado_sin_firma")

    # El área responsable ve el señalamiento y confirma la liberación del recurso con un motivo.
    entrar("dir_drff")
    expect(page.locator("[data-prueba=panel-sin-firma]")).to_contain_text(vencida.folio)
    captura("hu_3_3_07_bandeja_del_area_responsable_con_el_contrato_senalado")
    page.goto(f"{live_server.url}/recepcion/expediente/{vencida.folio}/?pestana=contrato")
    expect(page.locator("[data-prueba=sin-firma-exp]")).to_be_visible()
    captura("hu_3_3_08_pestana_contrato_sin_firma_en_plazo")
    page.fill("input[name=pestana-motivo]", "La persona no acudió a firmar en el plazo.")
    page.click("#form-liberar button")
    expect(page.locator("[data-prueba=liberacion]")).to_contain_text("Recurso liberado")
    captura("hu_3_3_09_recurso_liberado_con_motivo_y_acuse")
