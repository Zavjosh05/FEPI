"""HU-6.1 · Recorrido de la lista de espera y las sustituciones: la Delegación recibe el desistimiento por escrito con su acuse, el
área responsable lo propone al Comité, la Secretaría Técnica registra el acuerdo en la sesión de seguimiento y el área lo cumple
(se libera el recurso); luego el área propone la reasignación en el orden de la lista de espera, el Comité la acuerda y la
solicitud del primer lugar pasa a aprobada."""
from playwright.sync_api import expect

from dictamen import sesiones
from dictamen.models import TipoSesion
from nucleo.demo import _pdf_demo
from pruebas.fixtures_m2 import documento_sesion, fecha_sesion
from pruebas.fixtures_m3 import *  # noqa: F401,F403
from pruebas.fixtures_m3 import delegado_de


def _sesion(usuarios, ejercicio):
    s = sesiones.crear_sesion(usuarios["comite"], ejercicio, TipoSesion.SEGUIMIENTO, fecha_sesion(6), "Sala de juntas",
                              "Quórum\nSustituciones, desistimientos y reasignaciones")
    sesiones.agregar_documento(usuarios["comite"], s, documento_sesion(), "Propuestas")
    sesiones.enviar_convocatoria(usuarios["comite"], s)
    return s


def _cumplir_en_bandeja(page, live_server):
    page.goto(f"{live_server.url}/")
    panel = page.locator("[data-prueba=acuerdos-pendientes]")
    expect(panel).to_be_visible()
    panel.locator("button:has-text('Marcar cumplido')").first.click()
    expect(page.locator(".alert-success")).to_contain_text("marcado como cumplido")


def test_hu_6_1_recorrido_desistimiento_baja_y_reasignacion_a_la_lista_de_espera(  # noqa: F811
        datos_e2e, notificadas, usuarios, page, live_server, entrar, captura, tmp_path):
    _, (uno, dos, tres) = notificadas("CC", cuantas=3, presupuesto=12000)   # recurso para una; dos en lista de espera
    _sesion(usuarios, uno.ejercicio)
    escrito = tmp_path / "escrito_desistimiento.pdf"
    escrito.write_bytes(_pdf_demo("Escrito de desistimiento"))
    pestana = f"{live_server.url}/recepcion/expediente/{uno.folio}/?pestana=seguimiento"

    # La Delegación recibe el desistimiento por escrito, con la firma verificada: queda el acuse con la fecha y la hora.
    entrar(delegado_de(usuarios, uno).username)
    page.goto(pestana)
    page.select_option("#form-solicitud #id_tipo", "desistimiento")
    page.set_input_files("#form-solicitud #id_archivo", str(escrito))
    page.fill("#form-solicitud #id_motivo", "Cambio de residencia: no podrá atender las actividades del programa.")
    page.check("#form-solicitud input[name=firmas]")
    captura("hu_6_1_01_desistimiento_recibido_en_la_delegacion")
    page.click("#form-solicitud button[type=submit]")
    expect(page.locator(".alert-success")).to_contain_text("Registrado: desistimiento por escrito, con el acuse AC-")
    expect(page.locator("[data-solicitud=desistimiento] [data-prueba=fecha-solicitud]")).to_contain_text("h")
    captura("hu_6_1_02_acuse_del_desistimiento_con_fecha_y_hora")

    # El área responsable lo ve en su bandeja y lo propone al Comité: libera $12,000.
    entrar("dir_drff")
    expect(page.locator("[data-prueba=panel-solicitudes-por-proponer]")).to_contain_text(uno.folio)
    page.goto(pestana)
    expect(page.locator("a.btn:has-text('Proponer al Comité')")).to_be_visible()
    page.select_option("#form-propuesta #id_tipo", "desistimiento")
    page.click("#form-propuesta button[type=submit]")
    expect(page.locator("[data-prueba=propuestas-expediente]")).to_contain_text("$12,000.00")
    captura("hu_6_1_03_propuesta_de_baja_con_el_recurso_liberado")

    # La Secretaría Técnica la lleva a la sesión de seguimiento convocada.
    entrar("comite")
    expect(page.locator("[data-prueba=panel-propuestas-por-llevar]")).to_be_visible()
    page.goto(f"{live_server.url}/seguimiento/")
    bloque = page.locator("[data-prueba=propuestas-por-llevar]")
    captura("hu_6_1_04_propuesta_por_llevar_a_sesion")
    bloque.locator("button:has-text('Registrar el acuerdo del Comité')").first.click()
    expect(page.locator(".alert-success")).to_contain_text("queda pendiente en la bandeja de")

    # El área cumple el acuerdo: el recurso queda liberado y alcanza para el lugar 1 de la lista de espera.
    entrar("dir_drff")
    _cumplir_en_bandeja(page, live_server)
    page.goto(f"{live_server.url}/seguimiento/")
    lista = page.locator(f"[data-prueba=lista-espera][data-ejercicio='{uno.ejercicio.pk}']")
    expect(lista.locator("[data-prueba=total-liberado]")).to_have_text("$12,000.00")
    expect(lista.locator(f"tr[data-folio='{dos.folio}']")).to_have_attribute("data-alcanza", "si")
    expect(lista.locator(f"tr[data-folio='{tres.folio}']")).to_have_attribute("data-alcanza", "no")
    captura("hu_6_1_05_recurso_liberado_y_lista_de_espera_en_su_orden")
    lista.locator("[data-prueba=form-reasignacion] button").click()
    expect(page.locator(".alert-success")).to_contain_text("Propuesta de reasignación enviada")
    expect(page.locator("[data-prueba=propuestas] tr[data-tipo=reasignacion]")).to_contain_text("se reasignan $12,000.00")
    captura("hu_6_1_06_propuesta_de_reasignacion_enviada_al_comite")

    # El Comité la acuerda y el área la cumple: el lugar 1 pasa a aprobada; el lugar 2 sigue en lista de espera.
    entrar("comite")
    page.goto(f"{live_server.url}/seguimiento/")
    page.locator("[data-prueba=propuestas-por-llevar] button:has-text('Registrar el acuerdo del Comité')").first.click()
    expect(page.locator(".alert-success")).to_contain_text("queda pendiente")
    entrar("dir_drff")
    _cumplir_en_bandeja(page, live_server)
    page.goto(f"{live_server.url}/recepcion/expediente/{dos.folio}/")
    expect(page.locator("body")).to_contain_text("Aprobada")
    page.goto(f"{live_server.url}/seguimiento/")
    expect(page.locator("[data-prueba=propuestas] tr[data-tipo=reasignacion] [data-prueba=estado-propuesta]")).to_contain_text(
        "Acuerdo cumplido")
    captura("hu_6_1_07_reasignacion_cumplida_y_solicitud_aprobada")
