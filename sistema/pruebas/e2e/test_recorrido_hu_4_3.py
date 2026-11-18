"""HU-4.3 · Recorrido de la evaluación de reportes de los Guardabosques: la Delegación revisa el reporte de junio, la Dirección de
Protección Forestal evalúa, ve quién no entregó y envía la evaluación al CASPEG; el CASPEG la valida con su acuerdo de seguimiento
y el expediente muestra el historial por periodo."""
from nucleo import reloj
from playwright.sync_api import expect

from dictamen import seguimiento, sesiones
from dictamen.models import TipoSesion
from ejecucion import comprobaciones
from nucleo.demo import _pdf_demo
from pruebas.fixtures_m2 import documento_sesion, fecha_sesion
from pruebas.fixtures_m3 import *  # noqa: F401,F403
from pruebas.fixtures_m3 import delegado_de
from pruebas.fixtures_m4 import *  # noqa: F401,F403
from pruebas.fixtures_m5 import *  # noqa: F401,F403


def test_hu_4_3_recorrido_revision_evaluacion_no_entrego_envio_y_validacion(  # noqa: F811
        datos_e2e, contratadas, usuarios, page, live_server, entrar, captura, tmp_path):
    with reloj.en("2026-06-16 10:00"):
        _, (a, b) = contratadas("PEG", cuantas=2)
    reporte = tmp_path / "reporte_junio.pdf"
    reporte.write_bytes(_pdf_demo("Reporte mensual de junio"))
    with reloj.en("2026-07-02 10:00"):
        comprobaciones.registrar_envio(delegado_de(usuarios, a), a, "reporte_mensual", archivo=_Archivo(reporte), periodo="2026-06")
    url = f"{live_server.url}/ejecucion/reportes/?periodo=2026-06"

    # La Delegación de Amecameca revisa el reporte recibido.
    entrar(delegado_de(usuarios, a).username)
    expect(page.locator("[data-prueba=panel-reportes-por-revisar]")).to_contain_text(a.folio)
    page.goto(url)
    expect(page.locator("[data-prueba=supuestos]")).to_contain_text("Supuestos")
    captura("hu_4_3_01_la_delegacion_ve_el_reporte_por_revisar")
    page.locator("[data-prueba=form-revision] select").select_option("revisado")
    page.locator("[data-prueba=form-revision] button").click()
    expect(page.locator(".alert-success")).to_contain_text("revisado")
    expect(page.locator("[data-prueba=tabla-periodo] tr[data-prueba=fila-guardabosque]")).to_have_attribute("data-estado", "por_evaluar")
    captura("hu_4_3_02_reporte_revisado_por_la_delegacion")

    # La Dirección de Protección Forestal ve la tabla por periodo: quien no entregó queda identificado.
    page.context.clear_cookies()
    entrar("dir_dpf")
    page.goto(url)
    fila_a = page.locator(f"tr[data-prueba=fila-guardabosque][data-folio='{a.folio}']")
    fila_b = page.locator(f"tr[data-prueba=fila-guardabosque][data-folio='{b.folio}']")
    expect(fila_a).to_have_attribute("data-estado", "por_evaluar")
    expect(fila_b).to_have_attribute("data-estado", "no_entrego")
    expect(fila_b).to_contain_text("Señalado para el seguimiento")
    expect(page.locator("[data-prueba=enviar-al-caspeg] button")).to_be_disabled()
    captura("hu_4_3_03_tabla_por_periodo_con_quien_no_entrego")
    fila_a.locator("select").select_option("cumple")
    fila_a.locator("button:has-text('Guardar la evaluación')").click()
    expect(page.locator(".alert-success")).to_contain_text("cumple")
    expect(page.locator(f"tr[data-folio='{a.folio}'][data-prueba=fila-guardabosque] [data-prueba=estado-periodo]")).to_have_text("Cumple")
    expect(page.locator("[data-prueba=enviar-al-caspeg] button")).to_be_enabled()
    captura("hu_4_3_04_evaluacion_del_guardabosque_que_cumple")
    page.locator("[data-prueba=enviar-al-caspeg] button").click()
    expect(page.locator(".alert-success")).to_contain_text("enviada al CASPEG")
    expect(page.locator("[data-prueba=enviados-al-caspeg]")).to_contain_text("1 cumplen, 0 no cumplen, 1 no entregaron")
    captura("hu_4_3_05_evaluacion_enviada_al_caspeg_con_su_acuse")

    # El CASPEG la valida con un acuerdo de su sesión de seguimiento (HU-2.4).
    s = sesiones.crear_sesion(usuarios["comite"], a.ejercicio, TipoSesion.SEGUIMIENTO, fecha_sesion(8), "Sala", "Quórum\nValidación")
    sesiones.agregar_documento(usuarios["comite"], s, documento_sesion(), "Evaluación")
    sesiones.enviar_convocatoria(usuarios["comite"], s)
    seguimiento.registrar_acuerdo(usuarios["comite"], s, "validacion_reportes", "Se valida la evaluación de junio", [a, b],
                                  periodo="2026-06")
    page.context.clear_cookies()
    entrar("comite")
    page.goto(f"{live_server.url}/ejecucion/reportes/")
    expect(page.locator("[data-prueba=enviados-al-caspeg]")).to_contain_text("Validada")
    captura("hu_4_3_06_el_caspeg_ve_la_evaluacion_validada")

    # El expediente de cada Guardabosque muestra su historial por periodo.
    page.context.clear_cookies()
    entrar("dir_dpf")
    page.goto(f"{live_server.url}/recepcion/expediente/{a.folio}/?pestana=ejecucion")
    expect(page.locator("[data-prueba=historial-reportes] tr[data-periodo='2026-06']")).to_contain_text("Validada")
    captura("hu_4_3_07_historial_por_periodo_del_guardabosque_que_cumplio")
    page.goto(f"{live_server.url}/recepcion/expediente/{b.folio}/?pestana=ejecucion")
    expect(page.locator("[data-prueba=senalado-reportes]")).to_contain_text("No entregó".lower())
    captura("hu_4_3_08_guardabosque_que_no_entrego_queda_senalado")


class _Archivo:
    """Archivo subido mínimo para el servicio (nombre y contenido)."""

    def __init__(self, ruta):
        self.name, self._datos = ruta.name, ruta.read_bytes()

    def seek(self, _):
        pass

    def read(self):
        return self._datos
