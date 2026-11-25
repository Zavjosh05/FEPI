"""HU-2.2 · Recorrido del dictamen jurídico con capturas."""
from playwright.sync_api import expect

from dictamen import juridico
from nucleo.models import Ejercicio, Usuario
from pruebas.fixtures_m2 import registrar_validada


def test_hu_2_2_recorrido_dictamen_juridico(datos_e2e, page, live_server, entrar, captura):
    u = {x.username: x for x in Usuario.objects.all()}
    cc = Ejercicio.objects.get(programa__clave="CC", anio=2026)
    juridico.registrar_incumplida(u["juridica"], nombre="Rogelio Bautista Núñez", curp="BANR600101HMCTXG09",
                                  programa="Capturando Carbono 2024",
                                  motivo="No realizó las actividades comprometidas (8.1.8.1 fr. I).")
    exp = registrar_validada(u, cc, municipio="Villa de Allende", nombre="Cerro de la Cruz", usuario="del_valle",
                             curp="BANR600101HMCTXG09", solicitante="Rogelio Bautista Núñez")
    palmas = registrar_validada(u, cc, nombre="Predio Las Palmas", solicitante="Irma Soto Vega", ha=6)

    entrar("juridica")
    expect(page.locator("#tabla-bandeja")).to_contain_text(exp.folio)
    captura("hu_2_2_01_bandeja_unidad_juridica")
    page.goto(f"{live_server.url}/dictamen/incumplidas/")
    captura("hu_2_2_02_listado_de_incumplidas")
    page.goto(f"{live_server.url}/dictamen/juridico/{exp.folio}/")
    expect(page.locator("[data-prueba=cotejo]")).to_contain_text("no puede ser procedente")
    captura("hu_2_2_03_cotejo_automatico")
    _documentos_validos(page)
    _propiedad(page, "escritura", "Rogelio Bautista Núñez", "15")
    page.check("#id_resultado_0")
    page.fill("#id_motivo", "Documentación en orden.")
    page.click("button:has-text('Registrar dictamen jurídico')")
    expect(page.locator("#mensajes .alert-danger")).to_contain_text("No puede ser procedente")
    captura("hu_2_2_04_procedente_impedido")
    page.check("#id_resultado_1")
    page.fill("#id_motivo", "El titular está en el Listado de Personas Beneficiarias Incumplidas (8.1.1.1 inelegibles fr. II).")
    page.click("button:has-text('Registrar dictamen jurídico')")
    page.wait_for_url("**pestana=dictamenes")
    expect(page.locator("[data-prueba=resumen-juridico]")).to_contain_text("No procedente")
    captura("hu_2_2_05_dictamen_juridico_no_procedente")

    page.goto(f"{live_server.url}/recepcion/expediente/{exp.folio}/?pestana=documentos")
    expect(page.locator("[data-prueba=documento-dictamen]")).to_contain_text("Dictamen jurídico")
    captura("hu_2_2_06_documento_del_dictamen_adjunto")

    # Propiedad o legal posesión: la constancia de posesión venció y no ampara toda la superficie.
    page.goto(f"{live_server.url}/dictamen/juridico/{palmas.folio}/")
    _documentos_validos(page)
    _propiedad(page, "constancia_posesion", "Irma Soto Vega", "4", vigente_hasta="2026-01-31",
               numero="Constancia 12/2024 del Comisariado Ejidal")
    page.check("#id_resultado_0")
    page.fill("#id_motivo", "Documentación en orden.")
    captura("hu_2_2_07_revision_de_la_propiedad")
    page.click("button:has-text('Registrar dictamen jurídico')")
    expect(page.locator("#mensajes .alert-danger")).to_contain_text("no se acredita la propiedad")
    page.check("#id_resultado_1")
    page.fill("#id_motivo", "No se acredita la legal posesión: la constancia venció y ampara 4 de 6 ha.")
    page.click("button:has-text('Registrar dictamen jurídico')")
    page.wait_for_url("**pestana=dictamenes")
    expect(page.locator("[data-prueba=resumen-propiedad]")).to_contain_text("no acreditada")
    captura("hu_2_2_08_propiedad_no_acreditada")


def _documentos_validos(page):
    for radio in page.locator("input[type=radio][name^=doc_][value=si]").all():
        radio.check(force=True)


def _propiedad(page, tipo, titular, superficie, vigente_hasta="", numero="Escritura 4521"):
    page.select_option("#id_tipo_documento", tipo)
    page.fill("#id_numero_documento", numero)
    page.fill("#id_titular_documento", titular)
    page.check("#id_titular_coincide_0")
    page.fill("#id_superficie_documento_ha", superficie)
    if vigente_hasta:
        page.fill("#id_vigente_hasta", vigente_hasta)
    page.check("#id_sin_conflicto_0")
