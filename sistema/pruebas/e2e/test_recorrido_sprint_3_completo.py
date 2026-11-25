"""Recorrido completo por la interfaz (Playwright): ejecución, seguimiento y cierre, con un cambio de usuario en cada relevo.

* **Capturando Carbono, del contrato en la Delegación al padrón público:** la Delegación registra la firma (con ella se crea la
  cuenta del portal de la persona beneficiaria), emite el oficio y guarda el comprobante; la Dirección solicita la primera
  ministración y Administración y Finanzas la paga; la persona entra al portal con su CURP y el código del acuse y envía su aviso
  de término y su Informe Final; la Delegación revisa lo recibido y registra la verificación en campo; la Dirección solicita la
  segunda ministración y Finanzas la paga; la Dirección cierra el expediente, publica el padrón y envía el informe anual; la
  Secretaría Técnica registra su recepción; cualquier persona consulta el padrón sin sesión y la persona consulta su expediente
  con el folio y el código. La bitácora cuenta toda la historia.
* **Guardabosques, el ciclo de reportes:** el aviso «Por vencer» del reporte mensual en la bandeja de la Delegación, el reporte
  enviado por el portal, la revisión de la Delegación, la evaluación y el envío al CASPEG de la Dirección de Protección Forestal,
  la validación del CASPEG con su acuerdo, la solicitud y el pago de la ministración y el historial por periodo.

El tramo de partida (la solicitud aprobada y el contrato enviado a la Delegación, o firmado en PEG) se arma con los servicios: los
recorridos de los sprints 1 y 2 ya lo cubren por la interfaz. Cada paso ocurre en su fecha con el reloj simulado
(``nucleo.reloj``), así que los plazos y las fechas de las pantallas son los del calendario del programa. Sin rodeos: si algo no
deja avanzar por la interfaz, se corrige en el código.
"""
from playwright.sync_api import expect

from nucleo import reloj
from nucleo.demo import _pdf_demo
from nucleo.models import Expediente
from pruebas.e2e.conftest import ir_a
from pruebas.e2e.test_recorrido_hu_2_4 import _sesion
from pruebas.e2e.test_recorrido_sprint_2_completo import Recorrido, comprobar_bitacora
from pruebas.fixtures_m3 import *  # noqa: F401,F403
from pruebas.fixtures_m3 import delegado_de
from pruebas.fixtures_m4 import CONTRASENA_PORTAL, _codigos
from pruebas.fixtures_m5 import *  # noqa: F401,F403

CURP_CC = "LAPB800101MMCRNT05"


def _portal_primer_acceso(page, base, curp, codigo):
    """La persona entra al portal por primera vez con su CURP y el código de un solo uso del acuse y define su contraseña."""
    page.goto(f"{base}/portal/entrar/")
    page.click("a:has-text('Primer acceso')")
    page.fill("#curp", curp)
    page.fill("#codigo", codigo)
    page.fill("#contrasena", CONTRASENA_PORTAL)
    page.fill("#confirmacion", CONTRASENA_PORTAL)
    page.click("button[type=submit]")
    expect(page.locator("[data-prueba=mis-expedientes]")).to_be_visible()


def _salir_del_portal(page):
    page.click("button:has-text('Salir')")
    expect(page.locator("#curp")).to_be_visible()


def _pagar(r, page, folio, n, referencia, fecha):
    """Administración y Finanzas acepta la solicitud de la ministración ``n`` y registra su pago."""
    r.relevo("finanzas")
    expect(page.locator("[data-prueba=panel-por-revisar]")).to_contain_text(folio)
    r.abrir(folio, "Ministración solicitada")
    r.siguiente_paso(f"Revisar la solicitud de pago de la ministración {n}")
    page.click(f"[data-prueba=form-revision-m{n}] button:has-text('Aceptar')")
    pago = page.locator(f"[data-prueba=form-pago-m{n}]")
    expect(pago).to_be_visible()
    pago.locator("input[name=referencia]").fill(referencia)
    pago.locator("input[name=fecha_pago]").fill(fecha)
    pago.locator("button:has-text('Registrar el pago')").click()
    expect(page.locator(f"[data-prueba=pago-m{n}]")).to_contain_text("Pagada")


def test_sprint_3_cc_del_contrato_al_padron_publico_por_la_interfaz(  # noqa: F811
        datos_e2e, en_delegacion, usuarios, page, live_server, entrar, captura, tmp_path):
    with reloj.en("2026-08-03 10:00") as rel:
        _, (exp,) = en_delegacion("CC", cuantas=1)
        persona = exp.beneficiaria
        persona.curp = CURP_CC                             # con CURP válida, la firma crea la cuenta del portal
        persona.save(update_fields=["curp"])
        folio, base = exp.folio, live_server.url
        r = Recorrido(page, live_server, entrar, captura, tmp_path)
        delegacion = delegado_de(usuarios, exp).username
        assert delegacion == "del_amecameca"

        # ---- 1. Delegación: firma del contrato (crea la cuenta del portal), oficio y comprobante ------------------------
        rel.ir_a("2026-08-04 10:00")
        r.relevo(delegacion)
        r.abrir(folio, "Contrato en la Delegación")
        r.siguiente_paso("Registrar la firma del contrato")
        page.fill("#id_firmante_nombre", persona.nombre)
        for caja in page.locator("#form-firma input[type=checkbox][id^=id_v_]").all():
            caja.check()
        page.set_input_files("#id_archivo", r.pdf("contrato_firmado.pdf"))
        page.click("button:has-text('Registrar la firma')")
        expect(page.locator("[data-prueba=firma-contrato]")).to_contain_text("Contrato firmado")
        r.pestana("documentos")
        expect(page.locator("body")).to_contain_text("Acceso al portal de personas beneficiarias")
        captura("s3_11_01_firma_registrada_y_acuse_de_acceso_al_portal")
        r.bandeja()
        page.click(f"[data-prueba=panel-oficios-por-emitir] a:has-text('{folio}')")
        page.click("[data-prueba=oficio-pago] button:has-text('Emitir el oficio')")
        expect(page.locator("[data-prueba=oficio-pago]")).to_contain_text("OFP-CC-2026-")
        page.set_input_files("#form-comprobante input[type=file]", r.pdf("estado_de_cuenta.pdf"))
        page.click("#form-comprobante button[type=submit]")
        expect(page.locator("[data-prueba=comprobante-cuenta]")).to_contain_text("Recibido el")
        codigo_acceso, codigo_consulta = _codigos(Expediente.objects.get(folio=folio).acuses.get(tipo="alta_portal"))

        # ---- 2. Dirección: solicita la primera ministración; 3. Finanzas la paga ----------------------------------------
        rel.ir_a("2026-08-05 10:00")
        r.relevo("dir_drff")
        expect(page.locator("[data-prueba=panel-por-solicitar]")).to_contain_text(folio)
        r.abrir(folio, "Contrato firmado")
        r.siguiente_paso("Solicitar la ministración 1")
        page.click("[data-prueba=form-envio-m1] button")
        expect(page.locator("[data-prueba=envio-solicitud]")).to_contain_text("Enviada a Administración y Finanzas el")
        rel.ir_a("2026-08-06 10:00")
        _pagar(r, page, folio, 1, "SPEI-2026-0001", "2026-08-06")

        # ---- 4. La persona beneficiaria, en el portal: primer acceso, aviso de término e Informe Final ------------------
        rel.ir_a("2026-11-12 10:00")
        page.click("button:has-text('Salir')")
        _portal_primer_acceso(page, base, CURP_CC, codigo_acceso)
        expect(page.locator("[data-prueba=mis-expedientes]")).to_contain_text(folio)
        page.click(f"a:has-text('{folio}')")
        page.select_option("#form-envio-portal #id_tipo", "aviso_termino")
        page.fill("#form-envio-portal #id_fecha_hecho", "2026-11-11")
        page.fill("#form-envio-portal #id_descripcion", "Concluimos la reforestación del predio.")
        page.click("#form-envio-portal button[type=submit]")
        expect(page.locator(".alert-success")).to_contain_text("Envío registrado: Aviso de término de actividades")
        page.select_option("#form-envio-portal #id_tipo", "informe_final")
        page.set_input_files("#form-envio-portal input[type=file]", r.pdf("informe_final.pdf"))
        page.click("#form-envio-portal button[type=submit]")
        expect(page.locator("[data-prueba=lista-envios] li")).to_have_count(2)
        expect(page.locator("[data-prueba=estado-portal]")).to_contain_text("Comprobación enviada")
        captura("s3_11_02_portal_la_persona_envia_su_aviso_y_su_informe_final")
        _salir_del_portal(page)

        # ---- 5. Delegación: revisa lo recibido por el portal y registra la verificación en campo ------------------------
        rel.ir_a("2026-11-13 10:00")
        r.relevo(delegacion)
        expect(page.locator("[data-prueba=panel-comprobaciones-por-revisar]")).to_contain_text(folio)
        r.abrir(folio, "Comprobación enviada")
        r.pestana("ejecucion")
        expect(page.locator("[data-prueba=comprobaciones] tr[data-medio=portal]")).to_have_count(2)
        for _ in range(2):
            page.locator("[data-prueba=comprobaciones] button:has-text('Marcar como revisado')").first.click()
            expect(page.locator(".alert-success")).to_contain_text("revisado")
        page.select_option("#form-verificacion #id_tipo_documento", "informe_final_firmado")
        page.set_input_files("#form-verificacion #id_archivo", r.pdf("informe_final_firmado.pdf"))
        page.fill("#form-verificacion #id_fecha_visita", "2026-11-12")
        page.fill("#form-verificacion #id_superficie_verificada", "6")
        page.click("#form-verificacion button[type=submit]")
        expect(page.locator(".alert-success")).to_contain_text("Verificación registrada")
        expect(page.locator("[data-prueba=verificacion] [data-prueba=superficie-verificada]")).to_contain_text("6 ha de 6")
        captura("s3_11_03_pestana_ejecucion_envios_revisados_y_verificacion")

        # ---- 6. Dirección: segunda ministración; 7. Finanzas la paga --------------------------------------------------
        rel.ir_a("2026-11-16 10:00")
        r.relevo("dir_drff")
        r.abrir(folio, "Verificada")
        r.siguiente_paso("Solicitar la ministración 2")
        expect(page.locator("[data-soporte=verificacion_campo]")).to_contain_text("Completo")
        page.click("[data-prueba=form-envio-m2] button")
        expect(page.locator("[data-prueba=solicitud-m2] [data-prueba=estado-solicitud]")).to_contain_text("Enviada")
        rel.ir_a("2026-11-17 10:00")
        _pagar(r, page, folio, 2, "SPEI-2026-0002", "2026-11-17")
        captura("s3_11_04_segunda_ministracion_pagada")

        # ---- 8. Dirección: cierra el expediente (pestaña Seguimiento), publica el padrón y envía el informe anual -------
        rel.ir_a("2026-11-25 10:00")
        r.relevo("dir_drff")
        r.abrir(folio, "Ministración pagada")
        r.pestana("seguimiento")
        expect(page.locator("[data-prueba=resultados-expediente]")).to_be_visible()
        captura("s3_11_05_pestana_seguimiento_resultados_finales_antes_del_cierre")
        page.click("[data-prueba=cerrar-expediente]")
        expect(page.locator("[data-prueba=expediente-cerrado]")).to_contain_text("25/11/2026")
        r.estado("Ejercicio cerrado")
        rel.ir_a("2026-11-26 10:00")
        ir_a(page, "Cierre del ejercicio")
        page.click("[data-programa=CC] a.btn")
        expect(page.locator(f"tr[data-folio='{folio}']")).to_contain_text("Cerrado con resultados finales")
        page.click("[data-prueba=publicar-padron]")
        expect(page.locator("[data-prueba=padron-publicado]")).to_contain_text("Publicado el 26/11/2026")
        rel.ir_a("2026-11-27 10:00")
        page.reload()
        page.click("[data-prueba=enviar-informe]")
        expect(page.locator("[data-prueba=informe-enviado]")).to_contain_text("27/11/2026 a las 10:00 h")
        captura("s3_11_06_cierre_del_ejercicio_padron_publicado_e_informe_enviado")
        _sesion(usuarios, exp.ejercicio)                    # sesión de seguimiento convocada para presentarlo

        # ---- 9. Secretaría Técnica: registra la recepción del informe en la sesión del Comité ----------------------------
        rel.ir_a("2026-11-30 10:00")
        r.relevo("comite")
        expect(page.locator("[data-prueba=panel-informes-por-recibir]")).to_contain_text("Capturando Carbono")
        page.click("[data-prueba=panel-informes-por-recibir] a >> nth=0")
        page.select_option("[data-prueba=form-recepcion] #id_sesion", index=1)
        page.fill("[data-prueba=form-recepcion] #id_observaciones", "Se presenta en la sesión de seguimiento.")
        page.click("[data-prueba=form-recepcion] button[type=submit]")
        expect(page.locator("[data-prueba=informe-recepcion]")).to_contain_text("Recibido por la Secretaría Técnica")
        expect(page.locator("[data-prueba=estado-cierre]")).to_contain_text("Ejercicio cerrado")
        captura("s3_11_07_recepcion_del_informe_y_ejercicio_cerrado")

        # ---- 10. Cualquier persona: el padrón sin iniciar sesión; la persona: consulta con folio y código ---------------
        page.click("button:has-text('Salir')")
        page.goto(f"{base}/padron/")
        page.click("text=Ver el padrón")
        filas = page.locator("[data-prueba=padron-filas]")
        expect(filas.locator(f"tr[data-folio='{folio}']")).to_contain_text(persona.nombre)
        expect(filas.locator(f"tr[data-folio='{folio}']")).to_contain_text("Vigente")
        expect(filas).not_to_contain_text(CURP_CC)
        captura("s3_11_08_padron_publico_sin_iniciar_sesion")
        page.goto(f"{base}/portal/consulta/")
        page.fill("#folio", folio)
        page.fill("#codigo", codigo_consulta)
        page.click("button[type=submit]")
        expect(page.locator("[data-prueba=estado-portal]")).to_contain_text("Ejercicio cerrado")
        expect(page.locator("[data-prueba=lista-envios] li")).to_have_count(2)
        captura("s3_11_09_consulta_con_folio_y_codigo_expediente_cerrado")
        page.click("button:has-text('Terminar la consulta')")

        # ---- 11. La bitácora cuenta toda la historia, con cada unidad --------------------------------------------------
        r.relevo("dir_drff")
        page.goto(f"{base}/recepcion/expediente/{folio}/")
        filas = r.bitacora()
        comprobar_bitacora(filas, ["Contrato firmado", "Ministración solicitada", "Ministración pagada", "Actividades en ejecución",
                                   "Comprobación enviada", "Verificada", "Ministración solicitada", "Ministración pagada",
                                   "Actividades concluidas", "Ejercicio cerrado"],
                           [r.unidades[u] for u in (delegacion, "dir_drff", "finanzas")])
        # P-36: a 1366 px caben todas las pestañas del expediente (12, con «Trazabilidad»), en una fila y sin cortes.
        medida = page.locator("[data-prueba=pestanas-expediente]").evaluate(
            "ul => ({ancho: window.innerWidth, desborda: ul.scrollWidth > ul.clientWidth, "
            "pestanas: [...ul.querySelectorAll('a')].map(a => {const r = a.getBoundingClientRect(); "
            "return {texto: a.innerText.trim(), derecha: r.right, arriba: r.top};})})")
        assert medida["ancho"] == 1366 and not medida["desborda"] and len(medida["pestanas"]) == 12
        assert all(p["derecha"] <= medida["ancho"] for p in medida["pestanas"]), medida
        assert len({round(p["arriba"]) for p in medida["pestanas"]}) == 1, medida
        assert {"Bitácora", "Trazabilidad"} <= {p["texto"] for p in medida["pestanas"][-2:]}
        captura("s3_11_10_bitacora_de_la_firma_al_cierre")
    assert Expediente.objects.get(folio=folio).estado.clave == "ejercicio_cerrado"


def test_sprint_3_peg_ciclo_de_reportes_por_la_interfaz(  # noqa: F811
        datos_e2e, contratadas, usuarios, page, live_server, entrar, captura, tmp_path):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from dictamen import sesiones
    from dictamen.models import TipoSesion
    from pagos import solicitudes
    from pruebas.fixtures_m2 import documento_sesion, fecha_sesion

    with reloj.en("2026-06-16 10:00") as rel:
        _, (exp,) = contratadas("PEG", cuantas=1)          # firma del Guardabosque: se crea su cuenta del portal
        folio, base, deleg = exp.folio, live_server.url, delegado_de(usuarios, exp)
        solicitudes.adjuntar_comprobante(deleg, exp, SimpleUploadedFile("cuenta.pdf", _pdf_demo("Cuenta"), "application/pdf"))
        codigo_acceso, _ = _codigos(exp.acuses.get(tipo="alta_portal"))
        curp = exp.beneficiaria.curp
        r = Recorrido(page, live_server, entrar, captura, tmp_path)

        # ---- 1. Delegación: el aviso «Por vencer» del reporte de junio en su bandeja -------------------------------------
        rel.ir_a("2026-06-25 10:00")
        # (la Secretaría Técnica convoca con anticipación la sesión del CASPEG que validará la evaluación de junio)
        s = sesiones.crear_sesion(usuarios["comite"], exp.ejercicio, TipoSesion.SEGUIMIENTO, fecha_sesion(8), "Sala",
                                  "Quórum\nValidación de la evaluación de reportes")
        sesiones.agregar_documento(usuarios["comite"], s, documento_sesion(), "Evaluación de junio")
        sesiones.enviar_convocatoria(usuarios["comite"], s)
        r.relevo(deleg.username)
        panel = page.locator("[data-prueba=panel-por-vencer]")
        expect(panel).to_contain_text(folio)
        expect(panel).to_contain_text("30/06/2026")
        captura("s3_11_11_bandeja_de_la_delegacion_con_el_aviso_por_vencer")

        # ---- 2. El Guardabosque envía su reporte de junio por el portal -------------------------------------------------
        rel.ir_a("2026-07-02 10:00")
        page.click("button:has-text('Salir')")
        _portal_primer_acceso(page, base, curp, codigo_acceso)
        page.click(f"a:has-text('{folio}')")
        page.select_option("#form-envio-portal #id_tipo", "reporte_mensual")
        page.select_option("#form-envio-portal #id_periodo", "2026-06")
        page.set_input_files("#form-envio-portal input[type=file]", r.pdf("reporte_junio.pdf"))
        page.click("#form-envio-portal button[type=submit]")
        expect(page.locator(".alert-success")).to_contain_text("Envío registrado")
        expect(page.locator("[data-prueba=lista-envios]")).to_contain_text("portal de personas beneficiarias")
        captura("s3_11_12_el_guardabosque_envia_su_reporte_por_el_portal")
        _salir_del_portal(page)

        # ---- 3. Delegación: revisa el reporte ---------------------------------------------------------------------------
        rel.ir_a("2026-07-03 10:00")
        r.relevo(deleg.username)
        expect(page.locator("[data-prueba=panel-reportes-por-revisar]")).to_contain_text(folio)
        page.locator("[data-prueba=panel-reportes-por-revisar] a").first.click()
        page.wait_for_url("**/ejecucion/reportes/**")
        page.locator("[data-prueba=form-revision] select").select_option("revisado")
        page.locator("[data-prueba=form-revision] button").click()
        expect(page.locator(".alert-success")).to_contain_text("revisado")

        # ---- 4. Dirección de Protección Forestal: evalúa el periodo y lo envía al CASPEG --------------------------------
        rel.ir_a("2026-07-06 11:00")
        r.relevo("dir_dpf")
        page.locator("[data-prueba=panel-evaluaciones-por-hacer] a", has_text="Junio").first.click()
        page.wait_for_url("**periodo=2026-06**")
        fila = page.locator(f"tr[data-prueba=fila-guardabosque][data-folio='{folio}']")
        expect(fila).to_have_attribute("data-estado", "por_evaluar")
        fila.locator("select").select_option("cumple")
        fila.locator("button:has-text('Guardar la evaluación')").click()
        expect(page.locator(".alert-success")).to_contain_text("cumple")
        page.locator("[data-prueba=enviar-al-caspeg] button").click()
        expect(page.locator("[data-prueba=enviados-al-caspeg]")).to_contain_text("1 cumplen, 0 no cumplen, 0 no entregaron")
        captura("s3_11_13_evaluacion_del_periodo_enviada_al_caspeg")

        # ---- 5. CASPEG (Secretaría Técnica): valida la evaluación con su acuerdo ----------------------------------------
        rel.ir_a("2026-07-07 11:00")
        r.relevo("comite")
        page.goto(f"{base}/dictamen/sesiones/{s.pk}/")
        page.select_option("#id_tipo", "validacion_reportes")
        page.fill("#id_descripcion", "Se valida la evaluación de los reportes de junio.")
        page.select_option("#id_expedientes", [str(exp.pk)])
        page.fill("#id_periodo", "2026-06")
        page.click("button:has-text('Registrar acuerdo')")
        expect(page.locator("#tabla-acuerdos")).to_contain_text("2026-06")

        # ---- 6. Dirección: solicita la ministración 1; 7. Finanzas la paga por depósito ---------------------------------
        rel.ir_a("2026-07-08 10:00")
        r.relevo("dir_dpf")
        r.abrir(folio, "Contrato firmado")
        r.siguiente_paso("Solicitar la ministración 1")
        expect(page.locator("[data-prueba=solicitud-m1] [data-soporte=evaluacion_reportes]")).to_contain_text("Completo")
        page.click("[data-prueba=form-envio-m1] button")
        expect(page.locator("[data-prueba=envio-solicitud]")).to_contain_text("Enviada a Administración y Finanzas el")
        rel.ir_a("2026-07-09 10:00")
        _pagar(r, page, folio, 1, "DEP-2026-0001", "2026-07-09")

        # ---- 8. El expediente muestra el historial por periodo -----------------------------------------------------------
        r.relevo("dir_dpf")
        page.goto(f"{base}/recepcion/expediente/{folio}/?pestana=ejecucion")
        expect(page.locator("[data-prueba=historial-reportes] tr[data-periodo='2026-06']")).to_contain_text("Validada")
        captura("s3_11_14_historial_de_reportes_validado_y_ministracion_pagada")
    assert Expediente.objects.get(folio=folio).estado.clave == "pagada"
