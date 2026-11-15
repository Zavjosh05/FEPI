"""HU-3.2 · Recorrido de los modelos de contrato, la elaboración y el envío a la Delegación con capturas."""
from playwright.sync_api import expect

from contrato import contratos
from contrato.models import Contrato
from pruebas.fixtures_m3 import aprobadas, notificadas  # noqa: F401


def test_hu_3_2_recorrido_modelo_validado_elaboracion_y_envio(datos_e2e, notificadas, page, live_server, entrar, captura):  # noqa: F811
    sesion, (exp,) = notificadas("PS")

    # El área responsable ve qué sigue, intenta elaborar y descubre que no hay modelo validado.
    entrar("dir_drff")
    page.goto(f"{live_server.url}/recepcion/expediente/{exp.folio}/")
    expect(page.locator("a:has-text('Elaborar el contrato')").first).to_be_visible()
    captura("hu_3_2_01_siguiente_paso_elaborar_el_contrato")
    page.goto(f"{live_server.url}/contrato/contratos/{exp.folio}/elaborar/")
    expect(page.locator("[data-prueba=sin-modelo-validado]")).to_be_visible()
    captura("hu_3_2_02_sin_modelo_validado")

    # Registra la plantilla base (borrador) y le quita la marca: versión nueva por validar.
    page.goto(f"{live_server.url}/contrato/modelos/")
    page.select_option("#base_ejercicio", label="Plantaciones Sustentables 2026")
    page.click("button:has-text('Crear plantilla base')")
    expect(page.locator("[data-prueba=estado-version]")).to_contain_text("Por validar")
    expect(page.locator(".badge:has-text('BORRADOR – modelo por validar')").first).to_be_visible()
    captura("hu_3_2_03_plantilla_base_borrador_por_validar")
    texto = contratos.PLANTILLAS_BASE["contrato_adhesion"].replace(contratos.MARCA_BORRADOR, "").strip()
    page.fill("#id_texto", texto)
    page.click("button:has-text('Guardar versión nueva')")
    expect(page.locator("[data-prueba=versiones] tbody tr")).to_have_count(2)
    captura("hu_3_2_04_version_nueva_por_validar")

    # La Unidad Jurídica ve el modelo pendiente, lo revisa y lo valida.
    entrar("juridica")
    expect(page.locator("[data-prueba=panel-modelos-por-validar]")).to_be_visible()
    captura("hu_3_2_05_bandeja_unidad_juridica")
    page.click("[data-prueba=panel-modelos-por-validar] a")
    page.check("#id_decision_0")
    page.fill("#id_observaciones", "Cláusulas conformes con las Reglas de Operación.")
    captura("hu_3_2_06_revision_de_la_unidad_juridica")
    page.click("button:has-text('Registrar la revisión')")
    expect(page.locator("[data-prueba=estado-version]")).to_contain_text("Validada")
    captura("hu_3_2_07_modelo_validado_con_fecha_hora_y_observaciones")

    # El área responsable elabora el contrato sobre el modelo validado y lo envía.
    entrar("dir_drff")
    page.goto(f"{live_server.url}/contrato/contratos/{exp.folio}/elaborar/")
    expect(page.locator("#form-elaborar")).to_be_visible()
    captura("hu_3_2_08_elaborar_sobre_modelo_validado")
    page.click("button:has-text('Elaborar el contrato')")
    expect(page.locator("[data-prueba=estado-contrato]")).to_contain_text("Elaborado")
    captura("hu_3_2_09_contrato_elaborado")
    page.click("button:has-text('Enviar a la Delegación')")
    expect(page.locator("[data-prueba=envio-contrato]")).to_contain_text("AC-")
    assert Contrato.objects.get().enviado_en is not None
    captura("hu_3_2_10_contrato_enviado_con_fecha_hora_y_acuse")

    # La Delegación lo recibe en su bandeja para la firma.
    entrar("del_amecameca")
    expect(page.locator("#tabla-bandeja")).to_contain_text(exp.folio)
    captura("hu_3_2_11_bandeja_de_la_delegacion")
    page.goto(f"{live_server.url}/recepcion/expediente/{exp.folio}/?pestana=contrato")
    expect(page.locator("a:has-text('Ver el PDF')")).to_be_visible()
    captura("hu_3_2_12_pestana_contrato_en_la_delegacion")
