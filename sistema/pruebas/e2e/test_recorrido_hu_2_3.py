"""HU-2.3 · Recorrido de la sesión de aprobación con capturas."""
from datetime import timedelta

from django.utils import timezone
from playwright.sync_api import expect

from dictamen import juridico, tecnico
from dictamen.models import SesionComite
from nucleo.demo import _pdf_demo
from nucleo.models import Ejercicio, Usuario
from pruebas.fixtures_m2 import propiedad_en_regla, fecha_sesion, registrar_validada


def test_hu_2_3_recorrido_sesion_de_aprobacion(datos_e2e, page, live_server, entrar, captura, tmp_path):
    u = {x.username: x for x in Usuario.objects.all()}
    cc = Ejercicio.objects.get(programa__clave="CC", anio=2026)
    casos = [("Amecameca", "Los Ocotes", "reforestacion", "factible"),
             ("Tlalmanalco", "El Mirador", "plantacion_maderable", "factible"),
             ("Ozumba", "El Tecolote", "reforestacion", "factible"),
             ("Ayapango", "Cerro Gordo", "reforestacion", "no_factible")]
    for municipio, nombre, modalidad, resultado in casos:
        exp = registrar_validada(u, cc, municipio=municipio, nombre=nombre, modalidad=modalidad, ha=5,
                                 solicitante=f"Titular de {nombre}")
        tecnico.dictaminar(u["dir_drff"], exp, resultado,
                           "Cumple los criterios técnicos" if resultado == "factible" else "Densidad menor a la mínima")
        juridico.dictaminar(u["juridica"], exp, "procedente", "Documentación vigente", propiedad=propiedad_en_regla(exp))

    entrar("comite")
    expect(page.locator("#tabla-bandeja")).to_contain_text("Los Ocotes")
    captura("hu_2_3_01_bandeja_secretaria_tecnica")
    page.goto(f"{live_server.url}/dictamen/sesiones/nueva/?tipo=aprobacion")
    page.fill("#id_fecha_hora", timezone.localtime(fecha_sesion(6)).strftime("%Y-%m-%dT%H:%M"))
    page.fill("#id_lugar", "Sala de juntas de PROBOSQUE, Metepec")
    page.fill("#id_orden_del_dia", "Lista de asistencia y quórum\nPresentación del listado preliminar\n"
                                   "Aprobación de listados\nAutorización de publicación")
    captura("hu_2_3_02_nueva_sesion")
    page.click("button:has-text('Crear sesión')")
    archivo = tmp_path / "listado_preliminar.pdf"
    archivo.write_bytes(_pdf_demo("Listado preliminar"))
    page.fill("input[name=nombre]", "Listado preliminar de solicitudes")
    page.set_input_files("input[name=archivo]", str(archivo))
    page.click("button:has-text('Agregar documento')")
    page.click("button:has-text('Enviar convocatoria')")
    expect(page.locator("[data-prueba=convocatoria]")).to_contain_text("Enviada el")
    captura("hu_2_3_03_convocatoria_enviada_con_acuse")
    page.fill("#id_presupuesto", "20500")
    page.click("button:has-text('Generar propuesta')")
    expect(page.locator("[data-listado=lista_espera]")).to_contain_text("El Mirador")
    captura("hu_2_3_04_listados_propuestos")
    fila = page.locator("[data-listado=lista_espera] tr[data-folio]").first
    fila.locator("select[name=resultado]").select_option("beneficiaria")
    fila.locator("input[name=orden]").fill("1")
    fila.locator("input[name=motivo]").fill("Predio en Área Natural Protegida (8.1.2 fr. V)")
    fila.locator("button:has-text('Ajustar')").click()
    expect(page.locator("[data-listado=beneficiaria]")).to_contain_text("Constancia")
    captura("hu_2_3_05_ajuste_del_comite_con_constancia")
    page.check("#id_autoriza_publicacion")
    page.click("button:has-text('Registrar acta')")
    expect(page.locator(".alert-danger")).to_contain_text("antes de la sesión")   # la sesión aún no llega
    SesionComite.objects.update(fecha_hora=timezone.now() - timedelta(hours=3))   # ya se celebró
    page.reload()
    page.check("#id_autoriza_publicacion")
    page.click("button:has-text('Registrar acta')")
    expect(page.locator("[data-prueba=acta]")).to_contain_text("Acta registrada")
    captura("hu_2_3_06_acta_y_autorizacion_de_publicacion")
