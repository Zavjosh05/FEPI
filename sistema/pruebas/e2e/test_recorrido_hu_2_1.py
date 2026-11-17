"""HU-2.1 · Recorrido del dictamen técnico con capturas."""
from playwright.sync_api import expect

from dictamen import juridico, tecnico
from nucleo.models import Ejercicio, Usuario
from pruebas.fixtures_m2 import peg, registrar_peg, registrar_validada  # noqa: F401


def test_hu_2_1_recorrido_dictamen_tecnico(datos_e2e, peg, page, live_server, entrar, captura):  # noqa: F811
    u = {x.username: x for x in Usuario.objects.all()}
    cc = Ejercicio.objects.get(programa__clave="CC", anio=2026)
    exp = registrar_validada(u, cc, municipio="Juchitepec", nombre="Los Encinos del Monte", ha=9,
                             solicitante="Ernestina Flores Medina")
    registrar_validada(u, cc, municipio="Juchitepec", nombre="La Joya Alta", ha=5, desplazamiento=(180, 120),
                       solicitante="Pablo Juárez Santana")
    otro = registrar_validada(u, cc, municipio="Tlalmanalco", nombre="El Mirador", ha=12, solicitante="Ana Reyes Gil")
    tecnico.dictaminar(u["dir_drff"], otro, "no_factible", "Cobertura de bosque natural mayor al 30 % (fr. XIII).")
    juridico.dictaminar(u["juridica"], otro, "procedente", "Documentación vigente.")

    entrar("dir_drff")
    expect(page.locator("#tabla-bandeja")).to_contain_text(exp.folio)
    captura("hu_2_1_01_bandeja_direccion_en_dictamen")
    page.goto(f"{live_server.url}/dictamen/tecnico/{exp.folio}/")
    page.wait_for_selector("#mapa[data-listo='1']")
    expect(page.locator("[data-prueba=traslapes]")).to_contain_text("La Joya Alta")
    captura("hu_2_1_02_analisis_cartografico_y_lista_de_verificacion")
    page.check("#id_resultado_0")
    page.fill("#id_motivo", "Intento sin revisar la lista de verificación.")
    page.click("button:has-text('Registrar dictamen técnico')")
    expect(page.locator(".alert-danger, .alert")).to_contain_text("Falta marcar")
    for criterio in page.locator("#tabla-verificacion tr[data-criterio]").all():
        si = criterio.locator("label[for$='-si']")
        if si.count():
            si.click()
    page.check("#id_resultado_0")
    page.fill("#id_motivo", "Reforestación de 6 años con densidad de 72 %; el traslape con La Joya Alta se aclara en campo.")
    page.click("button:has-text('Registrar dictamen técnico')")
    page.wait_for_url("**pestana=dictamenes")
    expect(page.locator("[data-prueba=resumen-tecnico]")).to_contain_text("Factible")
    captura("hu_2_1_03_dictamen_tecnico_registrado")
    page.goto(f"{live_server.url}/dictamen/listado/")
    expect(page.locator("#tabla-listado")).to_contain_text("No factible")
    captura("hu_2_1_04_listado_preliminar")

    guardabosque = registrar_peg(u, peg, nombre="Ejido San Juan (Guardabosques)", solicitante="Ejido San Juan")
    entrar("dir_dpf")
    page.goto(f"{live_server.url}/recepcion/expediente/{guardabosque.folio}/?pestana=dictamenes")
    expect(page.locator("[data-prueba=plazo-dictamen]")).to_contain_text("45 días hábiles")
    captura("hu_2_1_05_plazo_de_45_dias_habiles_peg")
