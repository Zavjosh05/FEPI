"""HU-4.1 · Recorridos del envío de comprobaciones: la persona beneficiaria entra al portal con su CURP y el código del acuse,
define su contraseña, envía un aviso y un informe y ve sus acuses (y no ve lo ajeno); la Delegación ve lo recibido en su
bandeja y lo revisa. En el otro, la Delegación registra una entrega en ventanilla y la persona la consulta con folio y código."""
import re
from datetime import timedelta

from django.utils import timezone
from playwright.sync_api import expect

from nucleo.demo import _pdf_demo
from pruebas.fixtures_m3 import *  # noqa: F401,F403
from pruebas.fixtures_m3 import delegado_de
from pruebas.fixtures_m4 import *  # noqa: F401,F403
from pruebas.fixtures_m4 import CONTRASENA_PORTAL
from pruebas.fixtures_m5 import *  # noqa: F401,F403


def test_hu_4_1_recorrido_la_persona_entra_al_portal_envia_un_aviso_y_un_informe_y_ve_sus_acuses(  # noqa: F811
        datos_e2e, pagada, cuenta_portal, usuarios, page, live_server, entrar, captura, tmp_path):
    exp, otro = pagada("CC", cuantas=2)
    persona, codigo, _ = cuenta_portal(exp, con_codigos=True)
    cuenta_portal(otro, curp="ROSR700101HMCRLM05")
    informe = tmp_path / "informe_final.pdf"
    informe.write_bytes(_pdf_demo("Informe Final de Actividades"))
    ayer = (timezone.localdate() - timedelta(days=1)).isoformat()

    # Primer acceso: CURP y código de un solo uso del acuse; la persona define su contraseña.
    page.goto(f"{live_server.url}/portal/entrar/")
    page.click("a:has-text('Primer acceso')")
    page.fill("#curp", persona.username)
    page.fill("#codigo", codigo)
    page.fill("#contrasena", CONTRASENA_PORTAL)
    page.fill("#confirmacion", CONTRASENA_PORTAL)
    captura("hu_4_1_01_primer_acceso_con_curp_y_codigo_del_acuse")
    page.click("button[type=submit]")
    expect(page.locator("[data-prueba=mis-expedientes]")).to_contain_text(exp.folio)
    expect(page.locator("[data-prueba=mis-expedientes]")).not_to_contain_text(otro.folio)
    captura("hu_4_1_02_mis_expedientes_solo_los_suyos")

    # Envía el aviso de término de actividades.
    page.click(f"a:has-text('{exp.folio}')")
    expect(page.locator("[data-prueba=mis-envios]")).to_contain_text("Todavía no hay envíos")
    page.select_option("#form-envio-portal #id_tipo", "aviso_termino")
    page.fill("#form-envio-portal #id_fecha_hecho", ayer)
    page.fill("#form-envio-portal #id_descripcion", "Concluimos la reforestación del predio.")
    page.click("#form-envio-portal button[type=submit]")
    expect(page.locator(".alert-success")).to_contain_text("Envío registrado: Aviso de término de actividades")
    expect(page.locator("[data-prueba=estado-portal]")).to_contain_text("Comprobación enviada")
    captura("hu_4_1_03_aviso_de_termino_enviado_con_su_acuse")

    # Envía el Informe Final de Actividades con su documento.
    page.select_option("#form-envio-portal #id_tipo", "informe_final")
    page.set_input_files("#form-envio-portal input[type=file]", str(informe))
    page.click("#form-envio-portal button[type=submit]")
    expect(page.locator(".alert-success")).to_contain_text("Informe Final de Actividades")
    envios = page.locator("[data-prueba=lista-envios] li")
    expect(envios).to_have_count(2)
    expect(page.locator("[data-prueba=lista-envios]")).to_contain_text("portal de personas beneficiarias")
    captura("hu_4_1_04_informe_final_enviado_y_la_lista_de_envios")

    # Sus acuses, con la fecha y la hora, se abren desde el portal.
    acuses = page.locator("[data-prueba=acuses-portal] a")
    expect(acuses.first).to_be_visible()
    folio_acuse = page.locator("[data-prueba=lista-envios] li a").first.inner_text()
    assert re.match(r"AC-\d{4}-\d{6}", folio_acuse)
    respuesta = page.request.get(f"{live_server.url}/portal/expediente/{exp.folio}/acuse/{folio_acuse}/")
    assert respuesta.status == 200 and respuesta.body()[:4] == b"%PDF"
    page.locator("[data-prueba=acuses-portal]").scroll_into_view_if_needed()
    captura("hu_4_1_05_acuses_de_sus_envios_en_el_portal")

    # Lo ajeno no existe para ella, ni las pantallas del personal.
    assert page.goto(f"{live_server.url}/portal/expediente/{otro.folio}/").status == 404
    page.goto(f"{live_server.url}/recepcion/expediente/{exp.folio}/")
    expect(page.locator("[data-prueba=mis-expedientes]")).to_be_visible()

    # La Delegación ve lo recibido por el portal en su bandeja y lo revisa.
    entrar(delegado_de(usuarios, exp).username)
    expect(page.locator("[data-prueba=panel-comprobaciones-por-revisar]")).to_contain_text(exp.folio)
    captura("hu_4_1_06_bandeja_de_la_delegacion_con_lo_recibido_por_el_portal")
    page.goto(f"{live_server.url}/recepcion/expediente/{exp.folio}/?pestana=ejecucion")
    expect(page.locator("[data-prueba=comprobaciones] tr[data-medio=portal]")).to_have_count(2)
    page.locator("[data-prueba=comprobaciones] button:has-text('Marcar como revisado')").first.click()
    expect(page.locator(".alert-success")).to_contain_text("revisado")
    expect(page.locator("[data-prueba=comprobaciones]")).to_contain_text("revisado por la Delegación")
    captura("hu_4_1_07_pestana_ejecucion_de_la_delegacion_con_los_envios")


def test_hu_4_1_recorrido_entrega_en_ventanilla_y_consulta_con_folio_y_codigo(  # noqa: F811
        datos_e2e, pagada, usuarios, page, live_server, entrar, captura, tmp_path):
    exp = pagada("CC")
    codigo = re.findall(r"[A-Z2-9]{4}-[A-Z2-9]{4}", str(exp.acuses.get(tipo="alta_portal").contenido))[-1]
    informe = tmp_path / "informe_final_firmado.pdf"
    informe.write_bytes(_pdf_demo("Informe Final de Actividades firmado"))

    # La Delegación registra el Informe Final recibido en persona: el mismo registro que un envío por el portal.
    entrar(delegado_de(usuarios, exp).username)
    page.goto(f"{live_server.url}/recepcion/expediente/{exp.folio}/?pestana=ejecucion")
    expect(page.locator("[data-prueba=sin-comprobaciones]")).to_be_visible()
    page.select_option("#form-entrega #id_tipo", "informe_final")
    page.set_input_files("#form-entrega input[type=file]", str(informe))
    page.fill("#form-entrega #id_persona_entrega", "Beatriz Lara Pineda")
    captura("hu_4_1_08_la_delegacion_registra_la_entrega_en_ventanilla")
    page.click("#form-entrega button[type=submit]")
    expect(page.locator(".alert-success")).to_contain_text("entrega registrada con el acuse")
    fila = page.locator("[data-prueba=comprobaciones] tr[data-medio=ventanilla]")
    expect(fila).to_contain_text("Entrega Beatriz Lara Pineda; recibe")
    expect(fila.locator("[data-prueba=fecha-envio]")).to_have_text(re.compile(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2} h"))
    captura("hu_4_1_09_entrega_en_ventanilla_con_fecha_hora_y_acuse")

    # La persona consulta sin cuenta con el folio y el código del acuse: ve el envío y su acuse, pero no envía.
    page.context.clear_cookies()
    page.goto(f"{live_server.url}/portal/consulta/")
    page.fill("#folio", exp.folio)
    page.fill("#codigo", codigo)
    page.click("button[type=submit]")
    expect(page.locator("[data-prueba=lista-envios]")).to_contain_text("Informe Final de Actividades")
    expect(page.locator("[data-prueba=lista-envios]")).to_contain_text("en persona, en la delegación")
    expect(page.locator("[data-prueba=consulta-sin-envio]")).to_be_visible()
    expect(page.locator("#form-envio-portal")).to_have_count(0)
    captura("hu_4_1_10_consulta_con_folio_y_codigo_ve_la_entrega_y_su_acuse")
