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
    registrar_validada(u, cc, nombre="Predio Las Palmas", solicitante="Irma Soto Vega")

    entrar("juridica")
    expect(page.locator("#tabla-bandeja")).to_contain_text(exp.folio)
    captura("hu_2_2_01_bandeja_unidad_juridica")
    page.goto(f"{live_server.url}/dictamen/incumplidas/")
    captura("hu_2_2_02_listado_de_incumplidas")
    page.goto(f"{live_server.url}/dictamen/juridico/{exp.folio}/")
    expect(page.locator("[data-prueba=cotejo]")).to_contain_text("no puede ser procedente")
    captura("hu_2_2_03_cotejo_automatico")
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
