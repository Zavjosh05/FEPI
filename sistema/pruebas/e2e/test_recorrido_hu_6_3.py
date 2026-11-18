"""HU-6.3 · Recorrido del cierre del ejercicio: el área responsable ve los resultados finales (aprobado, verificado, pagado y
reintegrado coinciden), cierra el expediente, publica el padrón (que cualquier persona consulta sin cuenta) y envía el informe
anual al Comité con la fecha y la hora; la Secretaría Técnica registra su recepción en la sesión del Comité."""
from playwright.sync_api import expect

from pruebas.e2e.conftest import ir_a
from pruebas.e2e.test_recorrido_hu_6_1 import _sesion
from pruebas.fixtures_m3 import *  # noqa: F401,F403
from pruebas.fixtures_m4 import *  # noqa: F401,F403
from pruebas.fixtures_m5 import *  # noqa: F401,F403
from pruebas.test_hu_6_3 import _concluida


def test_hu_6_3_recorrido_resultados_finales_cierre_padron_e_informe_al_comite(  # noqa: F811
        datos_e2e, pagada, usuarios, page, live_server, entrar, captura):
    exp = _concluida(pagada, usuarios)                                      # CC 4 ha: pago único verificado y concluido
    ej = exp.ejercicio
    _sesion(usuarios, ej)

    # El área responsable abre el cierre del ejercicio desde el menú y ve los resultados finales.
    entrar("dir_drff")
    ir_a(page, "Cierre del ejercicio")
    expect(page.locator("[data-prueba=ejercicios-cierre]")).to_contain_text(f"{ej.programa.nombre} {ej.anio}")
    captura("hu_6_3_01_cierre_del_ejercicio_por_programa")
    page.click(f"[data-programa={ej.programa.clave}] a.btn")
    fila = page.locator(f"[data-prueba=resultados-finales] tr[data-folio='{exp.folio}']")
    expect(fila).to_contain_text("Lista para cerrar")
    assert fila.get_attribute("data-diferencias") == "0"
    expect(page.locator("[data-total=aprobado]")).to_have_text(page.locator("[data-total=pagado]").inner_text())
    captura("hu_6_3_02_resultados_finales_coinciden_con_verificaciones_y_pagos")

    # Cierra el expediente con sus resultados finales.
    page.click("[data-prueba=cerrar-listos]")
    expect(page.locator(".alert-success")).to_contain_text("cerrado(s)")
    expect(page.locator(f"tr[data-folio='{exp.folio}']")).to_contain_text("Cerrado con resultados finales")
    captura("hu_6_3_03_expediente_cerrado")

    # Publica el padrón y envía el informe anual al Comité con su fecha y su hora.
    page.click("[data-prueba=publicar-padron]")
    expect(page.locator("[data-prueba=padron-publicado]")).to_contain_text("Publicado el")
    page.click("[data-prueba=enviar-informe]")
    expect(page.locator("[data-prueba=informe-enviado]")).to_contain_text("a las")
    expect(page.locator("[data-prueba=informe-recepcion]")).to_contain_text("Todavía no se registra su recepción")
    captura("hu_6_3_04_padron_publicado_e_informe_enviado_al_comite")

    # Cualquier persona consulta el padrón sin iniciar sesión.
    page.context.clear_cookies()
    page.goto(f"{live_server.url}/padron/")
    expect(page.locator("[data-prueba=indice-padron]")).to_contain_text(ej.programa.nombre)
    page.click(f"text=Ver el padrón")
    expect(page.locator("[data-prueba=padron-filas]")).to_contain_text(exp.folio)
    expect(page.locator("[data-prueba=padron-filas]")).to_contain_text(exp.beneficiaria.nombre)
    expect(page.locator("[data-prueba=padron-filas]")).not_to_contain_text("CURP")
    captura("hu_6_3_05_padron_publico_sin_iniciar_sesion")

    # La Secretaría Técnica registra la recepción del informe en la sesión del Comité.
    entrar("comite")
    expect(page.locator("[data-prueba=panel-informes-por-recibir]")).to_contain_text(ej.programa.nombre)
    ir_a(page, "Cierre del ejercicio")
    page.click(f"[data-programa={ej.programa.clave}] a.btn")
    page.select_option("[data-prueba=form-recepcion] #id_sesion", index=1)
    page.fill("[data-prueba=form-recepcion] #id_observaciones", "Se presentará en la sesión de seguimiento.")
    page.click("[data-prueba=form-recepcion] button[type=submit]")
    expect(page.locator(".alert-success")).to_contain_text("Recepción del informe registrada")
    expect(page.locator("[data-prueba=informe-recepcion]")).to_contain_text("Recibido por la Secretaría Técnica")
    expect(page.locator("[data-paso=recepcion]")).to_have_attribute("data-listo", "si")
    expect(page.locator("[data-prueba=estado-cierre]")).to_contain_text("Ejercicio cerrado")
    captura("hu_6_3_06_recepcion_del_informe_y_ejercicio_cerrado")
