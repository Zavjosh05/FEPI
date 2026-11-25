"""Recorrido completo del sprint 1 con UNA solicitud, todo por la interfaz (Playwright).

Repite con clics el guion de pruebas/test_sprint_1_recorrido_completo.py (que lo hace con servicios): registro en la
ventanilla, revisión de requisitos, polígono, envío, aviso de faltantes y reenvío, validación, dictámenes técnico y
jurídico, sesión de aprobación y acta. En cada relevo se cierra la sesión y entra la unidad siguiente, y se comprueba
en pantalla el estado del expediente y su presencia (o ausencia) en las bandejas.

Única excepción a «todo por la interfaz»: la hora de la sesión se mueve al pasado por ORM justo antes de registrar el
acta (no se puede registrar antes de la sesión y la convocatoria exige 3 días hábiles de anticipación).
"""
import json
import re
from datetime import timedelta

import pytest
from django.utils import timezone
from playwright.sync_api import expect

from dictamen.models import SesionComite
from nucleo.demo import _pdf_demo, cuadro_en_municipio
from nucleo.models import Expediente, Municipio
from pruebas.e2e.test_recorridos import _elegir
from pruebas.fixtures_m2 import fecha_sesion

pytestmark = pytest.mark.navegador


def test_sprint_1_una_solicitud_recorre_todo_por_la_interfaz(datos_e2e, page, live_server, entrar, captura, tmp_path):
    base = live_server.url
    unidades = {}                      # usuario -> nombre de la unidad que se ve en la barra superior

    def pdf(nombre):
        ruta = tmp_path / nombre
        ruta.write_bytes(_pdf_demo(nombre))
        return str(ruta)

    def relevo(usuario):
        """Cierra la sesión con «Salir» (si hay una abierta) y entra con el siguiente usuario."""
        if page.locator("button:has-text('Salir')").count():
            page.click("button:has-text('Salir')")
            expect(page.locator("#id_username")).to_be_visible()
        entrar(usuario)
        unidades[usuario] = page.locator("[data-prueba=unidad]").inner_text().strip()

    def ir_a_bandeja():
        page.click(".navbar a:has-text('Bandeja')")
        page.wait_for_url("**/bandeja/**")

    def en_bandeja(folio, estado):
        fila = page.locator("#tabla-bandeja tr", has_text=folio)
        expect(fila).to_have_count(1)
        expect(fila).to_contain_text(estado)

    def fuera_de_bandeja(folio):
        ir_a_bandeja()
        expect(page.locator("#tabla-bandeja")).to_be_visible()
        expect(page.locator("#tabla-bandeja")).not_to_contain_text(folio)

    def abrir_expediente(folio):
        page.click(f"#tabla-bandeja a:has-text('{folio}')")
        page.wait_for_url(f"**/recepcion/expediente/{folio}/**")

    def pestana(clave):
        page.click(f"a[data-pestana={clave}]")
        page.wait_for_url(f"**pestana={clave}")

    def estado_exp(texto):
        expect(page.locator("[data-prueba=estado]")).to_contain_text(texto)

    def revisar_requisitos(faltar=()):
        """Revisa cada requisito con su formulario: archivo donde se pide, «no aplica» en los condicionales."""
        filas = page.eval_on_selector_all("tbody.req-fila", "els => els.map(e => ({id: e.id, clave: e.dataset.clave}))")
        assert len(filas) >= 10
        for f in filas:
            fila = page.locator(f"#{f['id']}")
            fila.locator("button:has-text('Revisar')").click()
            form = fila.locator("form")
            expect(form).to_be_visible()
            opciones = form.locator("select[name=estado] option").evaluate_all("os => os.map(o => o.value)")
            lleva_archivo = form.locator("input[name=archivo]").count() > 0
            if f["clave"] in faltar:
                form.locator("select[name=estado]").select_option("faltante")
                form.locator("input[name=observaciones]").fill("No lo presentó")
                esperado = r"Faltante|No cumple"
            elif "no_aplica" in opciones:
                form.locator("select[name=estado]").select_option("no_aplica")
                esperado = r"No aplica"
            else:
                form.locator("select[name=estado]").select_option("entregado")
                if lleva_archivo:
                    form.locator("input[name=archivo]").set_input_files(pdf(f"{f['clave']}.pdf"))
                esperado = r"Entregado|Cumple"
            form.locator("button:has-text('Guardar')").click()
            expect(page.locator(f"#{f['id']} [data-prueba=estado-req]")).to_have_text(re.compile(esperado))
        return [f["clave"] for f in filas]

    def entregar_plano():
        plano = page.locator("tbody.req-fila[data-clave=CC-REQ-13]")
        plano.locator("button:has-text('Revisar')").click()
        form = plano.locator("form")
        form.locator("select[name=estado]").select_option("entregado")
        form.locator("input[name=archivo]").set_input_files(pdf("plano_corregido.pdf"))
        form.locator("button:has-text('Guardar')").click()
        expect(plano.locator("[data-prueba=estado-req]")).to_have_text("Entregado")

    # ---- 1. Delegación: registro de la solicitud en la ventanilla (HU-1.1) -----------------------
    relevo("del_amecameca")
    page.click(".navbar a:has-text('Registrar solicitud')")
    page.wait_for_url("**/recepcion/registrar/")
    expect(page.locator("#id_ejercicio option:checked")).to_contain_text("Capturando Carbono")
    _elegir(page, "#id_tipo_persona", "Persona física")
    _elegir(page, "#id_modalidad", "Reforestación")
    page.fill("#id_nombre_predio", "Predio del recorrido")
    page.fill("#id_superficie_solicitada_ha", "6")
    page.fill("#id_solicitante_nombre", "Persona del Recorrido")
    _elegir(page, "#id_municipio", "^Amecameca")
    expect(page.locator("#delegacion-municipio")).to_contain_text("lo atiende esta Delegación")
    page.click("button:has-text('Registrar y generar acuse')")
    page.wait_for_url("**/recepcion/expediente/**")
    folio = re.search(r"/expediente/([^/?]+)/", page.url).group(1)
    expect(page.locator(".alert-success")).to_contain_text("Acuse de recepción")
    expect(page.locator("[data-prueba=acuse-recepcion]")).to_be_visible()
    estado_exp("Solicitud recibida")
    captura("recorrido_sprint_1_01_registro")
    ir_a_bandeja()
    en_bandeja(folio, "Solicitud recibida")

    # Intento indebido: otra Delegación no puede abrir el expediente por su URL.
    relevo("del_toluca")
    ir_a_bandeja()
    expect(page.locator("#tabla-bandeja")).not_to_contain_text(folio)
    respuesta = page.goto(f"{base}/recepcion/expediente/{folio}/")
    assert respuesta.status in (403, 404), f"del_toluca abrió el expediente ajeno (HTTP {respuesta.status})"
    expect(page.locator("[data-prueba=estado]")).to_have_count(0)

    # ---- 2. Delegación: requisitos (uno queda faltante), polígono y envío a la Dirección (HU-1.2, 1.3) ----
    relevo("del_amecameca")
    ir_a_bandeja()
    abrir_expediente(folio)
    pestana("requisitos")
    expect(page.locator("[data-prueba=boton-enviar]")).to_be_disabled()          # nada revisado todavía
    revisar_requisitos(faltar=("CC-REQ-13",))
    expect(page.locator("[data-prueba=panel-envio]")).to_contain_text("1 faltantes")
    expect(page.locator("[data-prueba=panel-envio]")).to_contain_text("CC-REQ-13")
    expect(page.locator("[data-prueba=boton-enviar]")).to_be_disabled()          # con un faltante no se puede enviar
    captura("recorrido_sprint_1_02_requisitos_con_un_faltante")
    entregar_plano()
    expect(page.locator("[data-prueba=boton-enviar]")).to_be_enabled()

    pestana("ubicacion")
    page.wait_for_selector("#mapa[data-listo='1']")
    ruta = tmp_path / "poligono_campo.geojson"
    muni = Municipio.objects.get(nombre="Amecameca")    # solo prepara el archivo que se sube por la pantalla
    ruta.write_text(json.dumps({"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"nombre": "Predio del recorrido"},
        "geometry": json.loads(cuadro_en_municipio(muni, 6).geojson)}]}))
    page.set_input_files("#id_archivo", str(ruta))
    page.fill("#id_responsable", "Brigada de la Delegación")
    page.click("button:has-text('Registrar polígono')")
    page.wait_for_selector("#mapa[data-listo='1']")
    expect(page.locator("[data-prueba=poligono-vigente]")).to_contain_text("ha")
    captura("recorrido_sprint_1_03_poligono_cargado")

    pestana("requisitos")
    page.click("[data-prueba=boton-enviar]")
    page.wait_for_url("**pestana=documentos")
    expect(page.locator("#tabla-acuses")).to_contain_text("envío del expediente digital")
    estado_exp("En revisión de la Dirección")
    fuera_de_bandeja(folio)

    # ---- 3. Dirección: lo ve en su bandeja y emite el aviso de faltantes (HU-1.4) ---------------------
    relevo("dir_drff")
    en_bandeja(folio, "En revisión de la Dirección")
    abrir_expediente(folio)
    page.click("a:has-text('Validar expediente')")
    page.wait_for_url("**/validar/")
    page.check("input[aria-label='Faltante CC-REQ-13']")
    page.fill("input[aria-label='Observación CC-REQ-13']", "El plano no trae coordenadas")
    page.fill("#observaciones", "Un requisito por corregir")
    page.click("button:has-text('Emitir aviso de faltantes')")
    page.wait_for_url("**pestana=validacion")
    expect(page.locator("[data-prueba=fecha-limite]")).to_be_visible()
    estado_exp("Aviso de faltantes")
    captura("recorrido_sprint_1_04_direccion_aviso_de_faltantes")
    fuera_de_bandeja(folio)

    # ---- 4. Delegación: ve el aviso, registra la notificación, sube de nuevo el documento y reenvía -----
    relevo("del_amecameca")
    en_bandeja(folio, "Aviso de faltantes")
    abrir_expediente(folio)
    pestana("validacion")
    expect(page.locator("[data-prueba=aviso-faltantes]")).to_contain_text("Pendiente de notificar")
    page.click("button:has-text('Registrar notificación')")
    expect(page.locator("[data-prueba=aviso-faltantes]")).to_contain_text("Notificado a la persona solicitante")
    pestana("requisitos")
    expect(page.locator("[data-prueba=boton-enviar]")).to_have_text(re.compile("Reenviar a la Dirección"))
    entregar_plano()
    expect(page.locator("[data-prueba=boton-enviar]")).to_be_enabled()
    captura("recorrido_sprint_1_05_delegacion_notifica_y_reenvia")
    page.click("[data-prueba=boton-enviar]")
    page.wait_for_url("**pestana=documentos")
    estado_exp("En revisión de la Dirección")
    fuera_de_bandeja(folio)

    # ---- 5. Dirección: valida y registra el dictamen técnico (HU-1.4, HU-2.1) ------------------------
    relevo("dir_drff")
    en_bandeja(folio, "En revisión de la Dirección")
    abrir_expediente(folio)
    page.click("a:has-text('Validar expediente')")
    page.wait_for_url("**/validar/")
    page.click("button:has-text('Validar expediente')")
    page.wait_for_url("**pestana=validacion")
    estado_exp("Validado · en dictamen")
    ir_a_bandeja()
    en_bandeja(folio, "Validado · en dictamen")
    abrir_expediente(folio)
    pestana("dictamenes")
    page.click("a:has-text('Elaborar dictamen técnico')")
    page.wait_for_url("**/dictamen/tecnico/**")
    page.wait_for_selector("#mapa[data-listo='1']")
    expect(page.locator("[data-prueba=traslapes]")).to_contain_text("Ninguno")
    for criterio in page.locator("#tabla-verificacion tr[data-criterio]").all():
        si = criterio.locator("label[for$='-si']")
        if si.count():
            si.click()
    page.check("#id_resultado_0")
    page.fill("#id_motivo", "Reforestación con densidad suficiente")
    captura("recorrido_sprint_1_06_dictamen_tecnico_lista_de_verificacion")
    page.click("button:has-text('Registrar dictamen técnico')")
    page.wait_for_url("**pestana=dictamenes")
    expect(page.locator("[data-prueba=resumen-tecnico]")).to_contain_text("Factible")
    estado_exp("Validado · en dictamen")                    # falta el dictamen jurídico
    fuera_de_bandeja(folio)                                  # la Dirección ya dictaminó

    # ---- 6. Unidad Jurídica: lo ve en su bandeja y registra el dictamen jurídico (HU-2.2) --------------
    relevo("juridica")
    en_bandeja(folio, "Validado · en dictamen")
    abrir_expediente(folio)
    pestana("dictamenes")
    expect(page.locator("[data-prueba=resumen-tecnico]")).to_contain_text("Factible")
    page.click("a:has-text('Elaborar dictamen jurídico')")
    page.wait_for_url("**/dictamen/juridico/**")
    expect(page.locator("[data-prueba=cotejo]")).to_contain_text("Sin coincidencias")
    for radio in page.locator("input[type=radio][name^=doc_][value=si]").all():
        radio.check(force=True)
    page.select_option("#id_tipo_documento", "escritura")
    page.fill("#id_numero_documento", "Escritura 4521")
    page.fill("#id_superficie_documento_ha", "8")
    page.check("#id_titular_coincide_0")
    page.check("#id_sin_conflicto_0")
    page.check("#id_resultado_0")
    page.fill("#id_motivo", "Documentación legal vigente")
    page.click("button:has-text('Registrar dictamen jurídico')")
    page.wait_for_url("**pestana=dictamenes")
    expect(page.locator("[data-prueba=resumen-juridico]")).to_contain_text("Procedente")
    expect(page.locator("[data-prueba=resumen-propiedad]")).to_contain_text("acreditada")
    expect(page.locator("[data-prueba=documento-juridico]")).to_be_visible()
    estado_exp("Dictaminada")
    captura("recorrido_sprint_1_07_dictamen_juridico")
    fuera_de_bandeja(folio)

    # ---- 7. Secretaría Técnica del Comité: sesión de aprobación, convocatoria, listados y acta (HU-2.3) --
    relevo("comite")
    en_bandeja(folio, "Dictaminada")
    page.click(".navbar a:has-text('Sesiones del Comité')")
    page.wait_for_url("**/dictamen/sesiones/")
    page.click("a:has-text('Nueva sesión de aprobación')")
    page.wait_for_url("**/sesiones/nueva/**")
    page.fill("#id_fecha_hora", timezone.localtime(fecha_sesion(6)).strftime("%Y-%m-%dT%H:%M"))
    page.fill("#id_lugar", "Sala de juntas de PROBOSQUE, Metepec")
    page.fill("#id_orden_del_dia", "Quórum\nListado preliminar\nAprobación de listados\nAutorización de publicación")
    page.click("button:has-text('Crear sesión')")
    expect(page.locator("[data-prueba=estado-sesion]")).to_be_visible()
    page.fill("input[name=nombre]", "Listado preliminar")
    page.set_input_files("input[name=archivo]", pdf("listado.pdf"))
    page.click("button:has-text('Agregar documento')")
    expect(page.locator("[data-prueba=convocatoria]")).to_contain_text("Listado preliminar")
    page.click("button:has-text('Enviar convocatoria')")
    expect(page.locator("[data-prueba=convocatoria]")).to_contain_text("Enviada el")
    page.fill("#id_presupuesto", "500000")
    page.click("button:has-text('Generar propuesta')")
    expect(page.locator("[data-listado=beneficiaria]")).to_contain_text(folio)
    captura("recorrido_sprint_1_08_sesion_convocada_y_listados")

    page.check("#id_autoriza_publicacion")
    page.click("button:has-text('Registrar acta')")
    expect(page.locator(".alert-danger")).to_contain_text("antes de la sesión")      # el acta anticipada se rechaza
    # ÚNICO paso que no es de interfaz: la sesión «ya se celebró» (se mueve su hora al pasado).
    SesionComite.objects.update(fecha_hora=timezone.now() - timedelta(hours=3))
    page.reload()
    page.check("#id_autoriza_publicacion")
    page.click("button:has-text('Registrar acta')")
    expect(page.locator("[data-prueba=acta]")).to_contain_text("Acta registrada")
    expect(page.locator("[data-prueba=acta]")).to_contain_text("Autorización de publicación: Sí")
    captura("recorrido_sprint_1_09_acta_y_autorizacion")
    page.click(f"[data-listado=beneficiaria] a:has-text('{folio}')")
    page.wait_for_url("**pestana=dictamenes")
    estado_exp("Aprobada")
    fuera_de_bandeja(folio)                                  # espera al módulo M3 (sprint 2)

    # ---- 8. Comprobación final como Delegación: estado, bitácora completa y acuse en PDF ------------------
    relevo("del_amecameca")
    expect(page.locator("#tabla-bandeja")).not_to_contain_text(folio)               # ya no está «por atender»
    page.click("label[for=alcance-todos]")
    en_bandeja(folio, "Aprobada")
    abrir_expediente(folio)
    estado_exp("Aprobada")
    pestana("bitacora")
    bitacora = page.locator("#tabla-bitacora")
    for transicion in ("Solicitud recibida", "En revisión de la Dirección", "Aviso de faltantes",
                       "Validado · en dictamen", "Dictaminada", "Aprobada"):
        expect(bitacora).to_contain_text(transicion)
    for usuario in ("del_amecameca", "dir_drff", "juridica", "comite"):
        expect(bitacora).to_contain_text(unidades[usuario])
    captura("recorrido_sprint_1_10_bitacora_y_estado_final")
    pestana("documentos")
    acuses = page.locator("#tabla-acuses a")
    assert acuses.count() >= 5
    respuesta = page.context.request.get(base + acuses.first.get_attribute("href"))
    assert respuesta.status == 200 and respuesta.body()[:4] == b"%PDF"
    expect(page.locator("[data-prueba=documento-dictamen]")).to_have_count(2)       # dictámenes técnico y jurídico
    captura("recorrido_sprint_1_11_acuses")
    pestana("trazabilidad")
    page.select_option("select[name=registro]", "Expediente")      # el historial del expediente: un renglón por relevo
    page.wait_for_url("**registro=Expediente**")
    for usuario in ("del_amecameca", "dir_drff", "juridica", "comite"):
        expect(page.locator("#tabla-trazabilidad")).to_contain_text(unidades[usuario])
    captura("recorrido_sprint_1_12_trazabilidad")

    exp = Expediente.objects.get(folio=folio)
    assert exp.estado.clave == "aprobada"
