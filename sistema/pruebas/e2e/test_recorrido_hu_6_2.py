"""HU-6.2 · Recorrido de incumplimientos y reintegros: el área responsable avisa las omisiones con su plazo; al vencer, el sistema
lo señala y el área confirma la propuesta de cancelación; el Comité la acuerda y la Unidad Jurídica la cumple (Listado de
Incumplidas y requerimiento preparado); Administración y Finanzas registra la cuenta, la Unidad Jurídica emite el requerimiento
con monto y cuenta y Administración y Finanzas comprueba el depósito."""
from datetime import timedelta

from django.utils import timezone
from playwright.sync_api import expect

from nucleo.demo import _pdf_demo
from pruebas.e2e.test_recorrido_hu_6_1 import _cumplir_en_bandeja, _sesion
from pruebas.fixtures_m3 import *  # noqa: F401,F403
from pruebas.fixtures_m4 import *  # noqa: F401,F403
from pruebas.fixtures_m5 import *  # noqa: F401,F403
from seguimiento import incumplimientos


def test_hu_6_2_recorrido_omision_cancelacion_requerimiento_y_reintegro(  # noqa: F811
        datos_e2e, pagada, usuarios, page, live_server, entrar, captura, tmp_path):
    exp = pagada("CC")                                                     # 6 ha: $8,400 ministrados
    _sesion(usuarios, exp.ejercicio)
    pestana = f"{live_server.url}/recepcion/expediente/{exp.folio}/?pestana=seguimiento"
    comprobante = tmp_path / "comprobante_deposito.pdf"
    comprobante.write_bytes(_pdf_demo("Comprobante de deposito"))

    # El área responsable avisa las omisiones con la fecha límite que fija (las reglas no dan días).
    entrar("dir_drff")
    page.goto(pestana)
    page.click("[data-prueba=avisar-omision] summary")
    page.fill("#form-omision #id_omisiones", "Entregar la evidencia fotográfica de los trabajos de reforestación.")
    page.fill("#form-omision #id_vence", (timezone.localdate() + timedelta(days=14)).isoformat())
    captura("hu_6_2_01_aviso_de_omisiones_con_su_plazo")
    page.click("#form-omision button[type=submit]")
    expect(page.locator(".alert-success")).to_contain_text("Aviso de omisiones enviado a la Delegación")
    expect(page.locator("[data-prueba=avisos-omision] [data-prueba=vence-omision]")).to_contain_text(
        f"{timezone.localdate() + timedelta(days=14):%d/%m/%Y}")
    captura("hu_6_2_02_omisiones_por_subsanar_con_fecha_limite")

    # Vence sin subsanar: la revisión diaria lo señala (no cambia nada) y el área confirma la propuesta con un clic.
    aviso = exp.avisos_omision.get()
    type(aviso).objects.filter(pk=aviso.pk).update(vence=timezone.localdate() - timedelta(days=1))
    assert incumplimientos.revisar(timezone.localdate()) == 1
    page.goto(f"{live_server.url}/")
    expect(page.locator("[data-prueba=panel-senalamientos]")).to_contain_text(exp.folio)
    page.goto(pestana)
    alerta = page.locator("[data-prueba=senalamiento][data-tipo=omision_vencida]")
    expect(alerta).to_contain_text("nada se ejecuta hasta que una persona lo confirma")
    captura("hu_6_2_03_omision_vencida_senalada_por_el_sistema")
    alerta.locator("button:has-text('Proponer la cancelación al Comité')").click()
    expect(page.locator("[data-prueba=propuestas-expediente] tr[data-tipo=cancelacion]")).to_be_visible()

    # El Comité acuerda la cancelación y la Unidad Jurídica la cumple.
    entrar("comite")
    page.goto(f"{live_server.url}/seguimiento/")
    page.locator("[data-prueba=propuestas-por-llevar] button:has-text('Registrar el acuerdo del Comité')").first.click()
    expect(page.locator(".alert-success")).to_contain_text("Unidad Jurídica")
    entrar("juridica")
    _cumplir_en_bandeja(page, live_server)
    page.goto(pestana)
    expect(page.locator("[data-prueba=inscripcion-listado]")).to_contain_text("Listado de Personas Beneficiarias Incumplidas")
    expect(page.locator("[data-prueba=requerimiento][data-estado=por_emitir]")).to_contain_text("$8,400.00")
    captura("hu_6_2_04_cancelada_inscrita_en_el_listado_y_requerimiento_por_emitir")

    # Administración y Finanzas registra la cuenta para reintegros del programa.
    entrar("finanzas")
    page.goto(f"{live_server.url}/seguimiento/incumplimientos/")
    page.select_option("#form-cuenta #id_programa", label=exp.programa.nombre)
    page.fill("#form-cuenta #id_titular", "PROBOSQUE")
    page.fill("#form-cuenta #id_banco", "Banco de prueba")
    page.fill("#form-cuenta #id_cuenta", "CUENTA-PRUEBA-0001")
    page.click("#form-cuenta button[type=submit]")
    expect(page.locator(f"[data-prueba=cuentas] tr[data-programa={exp.programa.clave}]")).to_contain_text("CUENTA-PRUEBA-0001")
    captura("hu_6_2_05_cuenta_para_reintegros_registrada")

    # La Unidad Jurídica emite el requerimiento con el monto y la cuenta.
    entrar("juridica")
    page.goto(pestana)
    page.click("#form-requerimiento button[type=submit]")
    tarjeta = page.locator("[data-prueba=requerimiento][data-estado=emitido]")
    expect(tarjeta.locator("[data-prueba=monto-requerido]")).to_contain_text("Monto por devolver: $8,400.00")
    expect(tarjeta.locator("[data-prueba=cuenta-requerimiento]")).to_contain_text("CUENTA-PRUEBA-0001")
    captura("hu_6_2_06_requerimiento_de_devolucion_con_monto_y_cuenta")

    # Administración y Finanzas comprueba el depósito: reintegrada.
    entrar("finanzas")
    page.goto(pestana)
    page.fill("#form-deposito #id_fecha", timezone.localdate().isoformat())
    page.fill("#form-deposito #id_importe", "8400.00")
    page.fill("#form-deposito #id_referencia", "DEP-0001")
    page.set_input_files("#form-deposito #id_archivo", str(comprobante))
    page.click("#form-deposito button[type=submit]")
    expect(page.locator(".alert-success")).to_contain_text("reintegrado")
    expect(page.locator("[data-prueba=requerimiento][data-estado=depositado]")).to_contain_text("DEP-0001")
    captura("hu_6_2_07_deposito_comprobado_expediente_reintegrado")
