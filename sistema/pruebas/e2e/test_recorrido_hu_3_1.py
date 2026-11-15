"""HU-3.1 · Recorrido de la publicación y las notificaciones con capturas (PS: trae también la cita a firma)."""
from playwright.sync_api import expect

from contrato.models import Publicacion
from pruebas.fixtures_m3 import aprobadas  # noqa: F401


def test_hu_3_1_recorrido_publicacion_y_notificaciones(datos_e2e, aprobadas, page, live_server, entrar, captura):  # noqa: F811
    sesion, exps = aprobadas("PS")
    primera = next(e for e in exps if e.predio.municipio.nombre == "Tlalmanalco")   # Delegación Amecameca

    # El área responsable ve en su bandeja el listado autorizado por publicar y lo publica.
    entrar("dir_drff")
    expect(page.locator("[data-prueba=panel-por-publicar]")).to_contain_text(sesion.numero)
    captura("hu_3_1_01_bandeja_area_responsable")
    page.goto(f"{live_server.url}/contrato/publicacion/")
    expect(page.locator("[data-prueba=por-publicar]")).to_contain_text(sesion.numero)
    captura("hu_3_1_02_listados_autorizados_por_publicar")
    page.click("a:has-text('Revisar y publicar')")
    expect(page.locator("[data-prueba=fecha-convocatoria]")).to_contain_text("Sin fecha en las reglas")
    captura("hu_3_1_03_publicar_sin_fecha_en_las_reglas")
    page.click("button:has-text('Publicar los listados')")
    expect(page.locator("[data-prueba=publicada]")).to_contain_text("AC-")
    expect(page.locator("[data-prueba=avisos-enviados]")).to_contain_text("Cita a firma del contrato")
    assert Publicacion.objects.get().renglones.count() == 2
    captura("hu_3_1_04_publicada_con_acuse_y_avisos_enviados")

    # La Delegación ve lo que le toca notificar y registra la entrega.
    entrar("del_amecameca")
    expect(page.locator("[data-prueba=panel-notificaciones]")).to_contain_text("Notificaciones por entregar")
    captura("hu_3_1_05_bandeja_delegacion")
    page.goto(f"{live_server.url}/contrato/notificaciones/")
    expect(page.locator("tr[data-tipo=cita_firma]")).to_contain_text("5 días hábiles")
    captura("hu_3_1_06_notificaciones_por_entregar_con_plazo_de_la_cita")
    fila = page.locator("tr[data-tipo=resultados]")
    fila.locator("summary").click()
    fila.locator("select").select_option("personal")
    fila.locator("textarea").fill("Se entregó en la ventanilla de la Delegación.")
    captura("hu_3_1_07_registrar_la_entrega")
    fila.locator("button:has-text('Registrar notificación')").click()
    expect(page.locator("#mensajes .alert-success")).to_contain_text("Notificación registrada")
    page.goto(f"{live_server.url}/contrato/notificaciones/?ver=entregadas")
    expect(page.locator("[data-prueba=notificada]")).to_have_count(1)
    captura("hu_3_1_08_entrega_con_fecha_hora_medio_y_acuse")

    # La pestaña «Contrato» del expediente junta lo publicado y lo notificado.
    page.goto(f"{live_server.url}/recepcion/expediente/{primera.folio}/?pestana=contrato")
    expect(page.locator("[data-prueba=resultado-publicado]")).to_contain_text("Lista de Personas Beneficiarias")
    expect(page.locator("[data-prueba=notificaciones-exp] tr")).to_have_count(3)
    captura("hu_3_1_09_pestana_contrato_del_expediente")

    # La persona consulta sin iniciar sesión.
    page.context.clear_cookies()
    page.goto(f"{live_server.url}/entrar/")
    expect(page.locator("[data-prueba=enlace-resultados]")).to_be_visible()
    captura("hu_3_1_10_inicio_de_sesion_con_enlace_a_resultados")
    page.click("a:has-text('Consulte los resultados publicados')")
    expect(page.locator("[data-prueba=indice-publico]")).to_contain_text("Plantaciones Sustentables")
    captura("hu_3_1_11_pagina_publica_indice")
    page.click("a:has-text('Ver listados')")
    expect(page.locator("[data-listado=beneficiaria]")).to_contain_text(primera.solicitante.nombre)
    captura("hu_3_1_12_pagina_publica_listados")
    page.fill("#folio", primera.folio)
    page.click("button:has-text('Buscar')")
    expect(page.locator("tr[data-folio]")).to_have_count(1)
    captura("hu_3_1_13_pagina_publica_busqueda_por_folio")
