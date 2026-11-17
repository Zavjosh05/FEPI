"""HU-4.2 · Recorrido de la verificación en campo: la Delegación ve la comprobación por verificar, registra el resultado con la
superficie verificada (90 %) y una incidencia con su documento; el área responsable ve el resultado y la segunda ministración
ajustada a lo verificado y la solicita a Administración y Finanzas."""
from datetime import timedelta

from django.utils import timezone
from playwright.sync_api import expect

from ejecucion import comprobaciones
from nucleo.demo import _pdf_demo
from pruebas.fixtures_m3 import *  # noqa: F401,F403
from pruebas.fixtures_m3 import delegado_de
from pruebas.fixtures_m4 import *  # noqa: F401,F403
from pruebas.fixtures_m5 import *  # noqa: F401,F403


def test_hu_4_2_recorrido_verificacion_con_incidencia_y_segunda_ministracion_ajustada(  # noqa: F811
        datos_e2e, pagada, usuarios, page, live_server, entrar, captura, tmp_path):
    exp = pagada("CC")                                           # 6 ha: 70 % pagado ($8,400), 30 % por verificar
    deleg = delegado_de(usuarios, exp)
    comprobaciones.registrar_envio(deleg, exp, "aviso_termino", fecha_hecho=timezone.localdate() - timedelta(days=2))
    formato, acta = tmp_path / "informe_final_firmado.pdf", tmp_path / "acta_de_helada.pdf"
    formato.write_bytes(_pdf_demo("Informe Final firmado"))
    acta.write_bytes(_pdf_demo("Acta de la helada"))
    pestana = f"{live_server.url}/recepcion/expediente/{exp.folio}/?pestana=ejecucion"

    # La Delegación tiene la comprobación por verificar: el siguiente paso y el plazo de entrega del documento.
    entrar(deleg.username)
    page.goto(pestana)
    expect(page.locator("a.btn:has-text('Registrar el resultado de la verificación en campo')")).to_be_visible()
    expect(page.locator("[data-prueba=plazo-entrega-verificacion]")).to_contain_text("15 días hábiles")
    captura("hu_4_2_01_comprobacion_por_verificar_en_la_delegacion")

    # Registra el resultado: Informe Final firmado, 5.4 de 6 ha y una helada como caso fortuito con su acta.
    page.select_option("#form-verificacion #id_tipo_documento", "informe_final_firmado")
    page.set_input_files("#form-verificacion #id_archivo", str(formato))
    page.fill("#form-verificacion #id_fecha_visita", (timezone.localdate() - timedelta(days=1)).isoformat())
    page.fill("#form-verificacion #id_superficie_verificada", "5.4")
    page.select_option("#form-verificacion #id_incidencia_1_tipo", "caso_fortuito")
    page.fill("#form-verificacion #id_incidencia_1_descripcion", "Helada en 0.6 ha del rodal norte.")
    page.set_input_files("#form-verificacion #id_incidencia_1_archivo", str(acta))
    captura("hu_4_2_02_formulario_del_resultado_con_superficie_e_incidencia")
    page.click("#form-verificacion button[type=submit]")
    expect(page.locator(".alert-success")).to_contain_text("Verificación registrada (cumple con ajuste de superficie")
    tarjeta = page.locator("[data-prueba=verificacion]")
    expect(tarjeta.locator("[data-prueba=superficie-verificada]")).to_contain_text("5.4 ha de 6 aprobadas: ajuste del 90 %")
    expect(tarjeta.locator("[data-prueba=importe-ajustado]")).to_contain_text("$2,400.00")
    expect(tarjeta.locator("[data-incidencia=caso_fortuito]")).to_contain_text("acta_de_helada")
    captura("hu_4_2_03_resultado_con_ajuste_incidencia_y_acuse")

    # El área responsable recibe el expediente verificado y solicita la segunda ministración por lo verificado.
    entrar("dir_drff")
    expect(page.locator("#tabla-bandeja")).to_contain_text(exp.folio)
    page.goto(f"{live_server.url}/recepcion/expediente/{exp.folio}/?pestana=pagos")
    expect(page.locator("[data-soporte=verificacion_campo]")).to_contain_text("Completo")
    expect(page.locator("[data-prueba=solicitud-m2]")).to_contain_text("$2,400.00")
    captura("hu_4_2_04_segunda_ministracion_ajustada_con_el_soporte_de_la_verificacion")
    page.click("[data-prueba=form-envio-m2] button")
    expect(page.locator("[data-prueba=solicitud-m2] [data-prueba=estado-solicitud]")).to_contain_text("Enviada")
    captura("hu_4_2_05_segunda_ministracion_enviada_a_administracion_y_finanzas")
