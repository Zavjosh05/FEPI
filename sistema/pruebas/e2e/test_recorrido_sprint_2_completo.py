"""Recorrido completo del sprint 2, todo por la interfaz (Playwright), en dos tramos.

* **Plantaciones Sustentables, de «aprobada» al pago:** publicar los listados, consultar la página pública, notificar
  en la Delegación, validar el modelo de contrato, elaborarlo y enviarlo, registrar la firma, emitir el Vale de Planta,
  salidas parcial y final del vivero, oficio, comprobante, solicitud de pago, aceptación y pago en Administración y
  Finanzas, y el expediente pagado con su bitácora.
* **PSAHEM, de «contratada» al cheque entregado:** oficio, instrucción de pago del Comité, solicitud, aceptación,
  remisión de la Secretaría Técnica, cheque de la Fiduciaria, entrega de la Delegación y vencimiento del cobro.

Cada relevo cierra la sesión (Salir) y entra la unidad siguiente. El tramo de partida (la solicitud aprobada, o con el
contrato firmado) se arma con los servicios: el recorrido del sprint 1 ya cubre la interfaz hasta la aprobación.
Los rodeos y los hallazgos de interfaz están marcados con «RODEO» y «HALLAZGO» en los comentarios.
"""
import re
from datetime import timedelta

import pytest
from django.utils import timezone
from playwright.sync_api import expect

from dictamen.models import SesionComite
from nucleo.demo import _pdf_demo
from nucleo.models import Expediente
from pruebas.e2e.conftest import ir_a
from pruebas.e2e.test_recorridos import _elegir
from pruebas.fixtures_m2 import fecha_sesion
from pruebas.fixtures_m3 import (aprobadas, catalogo_planta, contratadas, delegado_de, en_delegacion,  # noqa: F401
                                 modelo_validado, notificadas)

pytestmark = pytest.mark.navegador


class Recorrido:
    """Ayudantes de navegación comunes a los dos tramos (relevo, bandeja, expediente, pestañas)."""

    def __init__(self, page, live_server, entrar, captura, tmp_path):
        self.page, self.base, self._entrar, self.captura, self.tmp = page, live_server.url, entrar, captura, tmp_path
        self.unidades = {}

    def pdf(self, nombre):
        ruta = self.tmp / nombre
        ruta.write_bytes(_pdf_demo(nombre))
        return str(ruta)

    def relevo(self, usuario):
        """Cierra la sesión con «Salir» (si hay una abierta) y entra con el siguiente usuario."""
        if self.page.locator("button:has-text('Salir')").count():
            self.page.click("button:has-text('Salir')")
            expect(self.page.locator("#id_username")).to_be_visible()
        self._entrar(usuario)
        self.unidades[usuario] = self.page.locator("[data-prueba=unidad]").inner_text().strip()

    def bandeja(self):
        self.page.click(".navbar a:has-text('Bandeja')")
        self.page.wait_for_url("**/bandeja/**")

    def en_bandeja(self, folio, estado):
        """El expediente está «por atender» en la bandeja de quien entró, con el estado dicho."""
        self.bandeja()
        fila = self.page.locator("#tabla-bandeja tr", has_text=folio)
        expect(fila).to_have_count(1)
        expect(fila).to_contain_text(re.compile(estado))

    def fuera_de_bandeja(self, folio):
        self.bandeja()
        expect(self.page.locator("#tabla-bandeja")).to_be_visible()
        expect(self.page.locator("#tabla-bandeja")).not_to_contain_text(folio)

    def abrir(self, folio, estado=None):
        """Abre el expediente desde la bandeja (el enlace del folio)."""
        if estado:
            self.en_bandeja(folio, estado)
        else:
            self.bandeja()
        self.page.click(f"#tabla-bandeja a:has-text('{folio}')")
        self.page.wait_for_url(f"**/recepcion/expediente/{folio}/**")

    def estado(self, texto):
        expect(self.page.locator("[data-prueba=estado]")).to_contain_text(re.compile(texto))

    def pestana(self, clave):
        self.page.click(f"a[data-pestana={clave}]")
        self.page.wait_for_url(f"**pestana={clave}")

    def siguiente_paso(self, texto):
        """Hace clic en el botón «siguiente paso» del encabezado del expediente."""
        boton = self.page.locator("[data-prueba=siguiente-paso] a")
        expect(boton).to_contain_text(texto)
        boton.click()

    def bitacora(self):
        """Pestaña «Bitácora»: filas (fecha y hora, quién, estado) en orden cronológico."""
        self.pestana("bitacora")
        filas = self.page.locator("#tabla-bitacora tbody tr").evaluate_all(
            "trs => trs.map(t => [...t.querySelectorAll('td')].map(c => c.innerText.trim()))")
        filas = [f for f in filas if len(f) >= 4]
        from datetime import datetime
        fecha = lambda f: datetime.strptime(f[0], "%d/%m/%Y %H:%M:%S")  # noqa: E731
        if fecha(filas[0]) > fecha(filas[-1]):      # la tabla va de lo más nuevo a lo más viejo
            filas = filas[::-1]                      # (así los renglones del mismo segundo conservan su orden)
        return sorted(filas, key=fecha)


def comprobar_bitacora(filas, transiciones, unidades):
    """Los estados llegan en el orden dicho (subsucesión de la columna «Estado») y la bitácora nombra a cada unidad."""
    estados = [f[3] for f in filas]
    i = 0
    for t in transiciones:
        while i < len(estados) and not re.search(t, estados[i]):
            i += 1
        assert i < len(estados), f"la bitácora no trae «{t}» en orden: {estados}"
        i += 1
    texto = " ".join(" ".join(f) for f in filas)
    for u in unidades:
        assert u in texto, f"la bitácora no nombra a la unidad {u}"


def test_sprint_2_ps_de_aprobada_al_pago_por_la_interfaz(  # noqa: F811
        datos_e2e, aprobadas, catalogo_planta, usuarios, page, live_server, entrar, captura, tmp_path):
    from contrato import contratos

    vivero, esp = catalogo_planta
    sesion, (exp,) = aprobadas("PS", cuantas=1)
    folio = exp.folio
    r = Recorrido(page, live_server, entrar, captura, tmp_path)
    delegacion = delegado_de(usuarios, exp).username
    assert delegacion == "del_amecameca"

    # ---- 1. Dirección: publica los listados autorizados (HU-3.1) -----------------------------------------------
    r.relevo("dir_drff")
    expect(page.locator("[data-prueba=panel-por-publicar]")).to_contain_text(sesion.numero)
    r.en_bandeja(folio, "Aprobada")
    page.click("[data-prueba=panel-por-publicar] a")
    page.wait_for_url("**/contrato/publicacion/**")
    expect(page.locator("[data-prueba=fecha-convocatoria]")).to_contain_text("Sin fecha en las reglas")
    page.click("button:has-text('Publicar los listados')")
    expect(page.locator("[data-prueba=publicada]")).to_contain_text("AC-")
    expect(page.locator("[data-prueba=avisos-enviados]")).to_contain_text("Cita a firma del contrato")
    captura("recorrido_sprint_2_ps_01_publicacion")
    r.fuera_de_bandeja(folio)                         # ahora lo atiende la Delegación (notifica)

    # ---- 2. Cualquier persona: página pública sin sesión y búsqueda por folio --------------------------------------
    page.click("button:has-text('Salir')")
    page.click("a:has-text('Consulte los resultados publicados')")
    expect(page.locator("[data-prueba=indice-publico]")).to_contain_text("Plantaciones Sustentables")
    page.click("a:has-text('Ver listados')")
    expect(page.locator("[data-listado=beneficiaria]")).to_contain_text(exp.solicitante.nombre)
    page.fill("#folio", folio)
    page.click("button:has-text('Buscar')")
    expect(page.locator("tr[data-folio]")).to_have_count(1)
    expect(page.locator("tr[data-folio]")).to_contain_text(folio)
    captura("recorrido_sprint_2_ps_02_pagina_publica_busqueda_por_folio")

    # ---- 3. Delegación: notifica a la persona (HU-3.1) -------------------------------------------------------------
    if page.locator("a:has-text('Iniciar sesión')").count():
        page.click("a:has-text('Iniciar sesión')")
    else:   # HALLAZGO: la página de listados no trae enlace para volver a iniciar sesión (solo el índice)
        page.goto(f"{live_server.url}/entrar/")
    r.relevo(delegacion)
    r.en_bandeja(folio, "Resultados publicados")
    page.click(f"#tabla-bandeja a:has-text('{folio}')")
    r.siguiente_paso("Notificar a la persona beneficiaria")
    page.wait_for_url("**/contrato/notificaciones/**")
    fila = page.locator("tr[data-tipo=resultados]")
    fila.locator("summary").click()
    fila.locator("select").select_option("personal")
    fila.locator("textarea").fill("Se entregó en la ventanilla de la Delegación.")
    fila.locator("button:has-text('Registrar notificación')").click()
    expect(page.locator("#mensajes .alert-success")).to_contain_text("Notificación registrada")
    captura("recorrido_sprint_2_ps_03_notificacion_en_la_delegacion")
    r.fuera_de_bandeja(folio)

    # ---- 4. Dirección: sin modelo validado no se elabora; registra el modelo (HU-3.2) -----------------------------
    r.relevo("dir_drff")
    r.abrir(folio, "Persona beneficiaria notificada")
    r.siguiente_paso("Elaborar el contrato")
    expect(page.locator("[data-prueba=sin-modelo-validado]")).to_be_visible()
    captura("recorrido_sprint_2_ps_04_sin_modelo_validado")
    page.click("[data-prueba=sin-modelo-validado] a:has-text('Modelos de contrato')")
    page.select_option("#base_ejercicio", label="Plantaciones Sustentables 2026")
    page.click("button:has-text('Crear plantilla base')")
    expect(page.locator("[data-prueba=estado-version]")).to_contain_text("Por validar")
    texto = contratos.PLANTILLAS_BASE["contrato_adhesion"].replace(contratos.MARCA_BORRADOR, "").strip()
    page.fill("#id_texto", texto)
    page.click("button:has-text('Guardar versión nueva')")
    expect(page.locator("[data-prueba=versiones] tbody tr")).to_have_count(2)

    # ---- 5. Unidad Jurídica: valida el modelo --------------------------------------------------------------------
    r.relevo("juridica")
    page.click("[data-prueba=panel-modelos-por-validar] a")
    page.check("#id_decision_0")
    page.fill("#id_observaciones", "Cláusulas conformes con las Reglas de Operación.")
    page.click("button:has-text('Registrar la revisión')")
    expect(page.locator("[data-prueba=estado-version]")).to_contain_text("Validada")
    captura("recorrido_sprint_2_ps_05_modelo_validado_por_juridica")

    # ---- 6. Dirección: elabora el contrato y lo envía a la Delegación ----------------------------------------------
    r.relevo("dir_drff")
    r.abrir(folio, "Persona beneficiaria notificada")
    r.siguiente_paso("Elaborar el contrato")
    expect(page.locator("#form-elaborar")).to_be_visible()
    page.click("button:has-text('Elaborar el contrato')")
    expect(page.locator("[data-prueba=estado-contrato]")).to_contain_text("Elaborado")
    page.click("button:has-text('Enviar a la Delegación')")
    expect(page.locator("[data-prueba=envio-contrato]")).to_contain_text("AC-")
    captura("recorrido_sprint_2_ps_06_contrato_elaborado_y_enviado")
    r.fuera_de_bandeja(folio)

    # ---- 7. Delegación: registra la firma (HU-3.3) ---------------------------------------------------------------
    r.relevo(delegacion)
    r.abrir(folio, "Contrato en la Delegación")
    r.siguiente_paso("Registrar la firma del contrato")
    expect(page.locator("#form-firma")).to_be_visible()
    expect(page.locator("[data-prueba=fechas-firma]")).to_contain_text("Vencimiento para liberar el recurso")
    page.fill("#id_firmante_nombre", exp.solicitante.nombre)
    page.set_input_files("#id_archivo", r.pdf("contrato_firmado.pdf"))
    page.click("button:has-text('Registrar la firma')")
    expect(page.locator("[data-prueba=verificacion]")).to_be_visible()          # no se recibe sin verificar
    for caja in page.locator("#form-firma input[type=checkbox][id^=id_v_]").all():
        caja.check()
    page.set_input_files("#id_archivo", r.pdf("contrato_firmado.pdf"))
    page.click("button:has-text('Registrar la firma')")
    expect(page.locator("[data-prueba=firma-contrato]")).to_contain_text("Contrato firmado")
    captura("recorrido_sprint_2_ps_07_firma_registrada")

    # ---- 8. Delegación: emite el Vale de Planta (HU-3.4) -----------------------------------------------------------
    r.bandeja()
    page.click(f"[data-prueba=panel-vales-por-entregar] a:has-text('{folio}')")   # el contrato firmado ya no está «por atender»
    expect(page.locator("[data-prueba=propuesta-planta]")).to_contain_text("4400")
    page.select_option("#id_vivero", label=vivero.nombre)
    page.fill(f"#id_esp_{esp['Pino patula'].pk}", "3000")
    page.fill(f"#id_esp_{esp['Oyamel'].pk}", "1400")
    page.click("button:has-text('Entregar el vale')")
    expect(page.locator("[data-prueba=vigencia]")).to_contain_text("hasta el")
    captura("recorrido_sprint_2_ps_08_vale_entregado")

    # ---- 9. Vivero: valida el vale y registra una salida parcial y la final ----------------------------------------
    r.relevo("vivero")
    expect(page.locator("[data-prueba=panel-vales-por-surtir]")).to_contain_text("VP-PS-2026-")
    r.en_bandeja(folio, "Vale de Planta entregado")
    page.click("[data-prueba=panel-vales-por-surtir] a:has-text('Abrir la salida de planta')")
    folio_vale = re.search(r"VP-PS-2026-\d+", page.locator("body").inner_text()).group(0)
    page.fill("#folio", folio_vale)
    page.click("button:has-text('Validar el vale')")
    expect(page.locator("#form-salida")).to_be_visible()
    page.select_option("#id_especie", label=str(esp["Pino patula"]))
    page.fill("#id_cantidad", "3000")
    page.click("button:has-text('Registrar la salida')")
    expect(page.locator("[data-prueba=salidas]")).to_contain_text("3000")
    page.select_option("#id_especie", label=str(esp["Oyamel"]))
    page.fill("#id_cantidad", "9999")
    page.click("button:has-text('Registrar la salida')")
    expect(page.locator(".alert-danger")).to_contain_text("no se entrega más de lo autorizado")
    captura("recorrido_sprint_2_ps_09_salida_parcial_y_exceso_rechazado")
    page.select_option("#id_especie", label=str(esp["Oyamel"]))
    page.fill("#id_cantidad", "1400")
    page.click("button:has-text('Registrar la salida')")
    expect(page.locator("[data-prueba=salidas]")).to_contain_text("1400")
    captura("recorrido_sprint_2_ps_10_salida_final")
    r.fuera_de_bandeja(folio)

    # ---- 10. Delegación: oficio de solicitud de pago y comprobante de la cuenta (HU-5.1) ------------------------
    r.relevo(delegacion)
    r.bandeja()
    page.click(f"[data-prueba=panel-oficios-por-emitir] a:has-text('{folio}')")
    page.click("[data-prueba=oficio-pago] button:has-text('Emitir el oficio')")
    expect(page.locator("[data-prueba=oficio-pago]")).to_contain_text("OFP-PS-2026-")
    page.set_input_files("#form-comprobante input[type=file]", r.pdf("estado_de_cuenta.pdf"))
    page.click("#form-comprobante button[type=submit]")
    expect(page.locator("[data-prueba=comprobante-cuenta]")).to_contain_text("Recibido el")
    captura("recorrido_sprint_2_ps_11_oficio_y_comprobante")

    # ---- 11. Dirección: solicita la primera ministración ------------------------------------------------------------
    r.relevo("dir_drff")
    expect(page.locator("[data-prueba=panel-por-solicitar]")).to_contain_text(folio)
    r.abrir(folio, "Planta entregada")
    r.siguiente_paso("Solicitar la ministración 1")
    expect(page.locator("[data-prueba=soportes-m1] .badge.text-bg-danger")).to_have_count(0)
    page.click("[data-prueba=form-envio-m1] button")
    expect(page.locator("[data-prueba=envio-solicitud]")).to_contain_text("Enviada a Administración y Finanzas el")
    captura("recorrido_sprint_2_ps_12_solicitud_enviada")

    # ---- 12. Administración y Finanzas: acepta y registra el pago (HU-5.2) -----------------------------------------
    r.relevo("finanzas")
    expect(page.locator("[data-prueba=panel-por-revisar]")).to_contain_text(folio)
    r.abrir(folio, "Ministración solicitada")
    r.siguiente_paso("Revisar la solicitud de pago de la ministración 1")
    page.click("[data-prueba=form-revision-m1] button:has-text('Aceptar')")
    expect(page.locator("[data-prueba=form-pago-m1]")).to_be_visible()
    page.fill("#id_referencia", "SPEI-2026-0001")
    page.fill("#id_fecha_pago", timezone.localdate().isoformat())
    page.click("[data-prueba=form-pago-m1] button:has-text('Registrar el pago')")
    expect(page.locator("[data-prueba=pago-m1]")).to_contain_text("Pagada")
    expect(page.locator("[data-prueba=fecha-pago]")).to_be_visible()
    captura("recorrido_sprint_2_ps_13_pago_registrado")

    # ---- 13. Delegación: notifica el pago; Dirección ve el expediente pagado con su bitácora ----------------------
    r.relevo(delegacion)
    expect(page.locator("[data-prueba=panel-notificaciones]")).to_contain_text("Aviso de pago")
    # HALLAZGO (menor): el folio del panel abre la pestaña «Contrato» del expediente, donde el aviso de pago no se puede
    # registrar; hay que usar el botón de abajo, «Abrir la bandeja de notificaciones».
    page.click("[data-prueba=panel-notificaciones] a:has-text('Abrir la bandeja de notificaciones')")
    fila = page.locator("tr[data-tipo=pago]")
    fila.locator("summary").click()
    fila.locator("select").select_option("telefono")
    fila.locator("button:has-text('Registrar notificación')").click()
    expect(page.locator("#mensajes .alert-success")).to_contain_text("Notificación registrada")
    r.relevo("dir_drff")
    r.abrir(folio, "Ministración pagada")
    r.estado("Ministración pagada")
    filas = r.bitacora()
    comprobar_bitacora(filas, ["Resultados publicados", "Persona beneficiaria notificada", "Contrato elaborado",
                               "Contrato en la Delegación", "Contrato firmado", "Vale de Planta entregado",
                               "Planta entregada", "Ministración solicitada", "Ministración pagada"],
                       [r.unidades[u] for u in ("dir_drff", delegacion, "vivero", "finanzas")])
    captura("recorrido_sprint_2_ps_14_expediente_pagado_y_bitacora")
    assert Expediente.objects.get(folio=folio).estado.clave == "pagada"


def test_sprint_2_psahem_de_contratada_al_cheque_entregado_por_la_interfaz(  # noqa: F811
        datos_e2e, contratadas, usuarios, page, live_server, entrar, captura, tmp_path):
    _, (exp,) = contratadas("PSA", cuantas=1)
    folio = exp.folio
    r = Recorrido(page, live_server, entrar, captura, tmp_path)
    delegacion = delegado_de(usuarios, exp).username
    assert delegacion == "del_toluca"

    # ---- 1. Delegación: oficio de solicitud de pago (PSAHEM no pide comprobante de cuenta: paga con cheque) -----
    r.relevo(delegacion)
    r.bandeja()
    page.click(f"[data-prueba=panel-oficios-por-emitir] a:has-text('{folio}')")
    page.click("[data-prueba=oficio-pago] button:has-text('Emitir el oficio')")
    expect(page.locator("[data-prueba=oficio-pago]")).to_contain_text("OFP-PSA-2026-")
    expect(page.locator("#form-comprobante")).to_have_count(0)
    captura("recorrido_sprint_2_psa_01_oficio_de_la_delegacion")

    # ---- 2. Dirección: intenta solicitar sin la instrucción del Comité y el sistema dice qué falta -------------------
    r.relevo("dir_drff")
    r.abrir(folio, "Contrato firmado")
    r.siguiente_paso("Solicitar la ministración 1")
    page.click("[data-prueba=form-envio-m1] button")
    expect(page.locator(".alert-danger")).to_contain_text("instruye el pago de la ministración 1")
    captura("recorrido_sprint_2_psa_02_falta_la_instruccion_de_pago_del_comite")

    # ---- 3. Secretaría Técnica: sesión de seguimiento con el acuerdo de instrucción de pago (HU-2.4) ---------------
    r.relevo("comite")
    ir_a(page, "Sesiones del Comité")
    page.click("a:has-text('Nueva sesión de seguimiento')")
    page.wait_for_url("**/sesiones/nueva/**")
    _elegir(page, "#id_ejercicio", "Servicios Ambientales")
    page.fill("#id_fecha_hora", timezone.localtime(fecha_sesion(6)).strftime("%Y-%m-%dT%H:%M"))
    page.fill("#id_lugar", "Sala de juntas del FIPASAHEM")
    page.fill("#id_orden_del_dia", "Quórum\nInstrucción de pago")
    page.click("button:has-text('Crear sesión')")
    expect(page.locator("[data-prueba=estado-sesion]")).to_be_visible()
    page.fill("input[name=nombre]", "Pagos")
    page.set_input_files("input[name=archivo]", r.pdf("pagos.pdf"))
    page.click("button:has-text('Agregar documento')")
    page.click("button:has-text('Enviar convocatoria')")
    expect(page.locator("[data-prueba=convocatoria]")).to_contain_text("Enviada el")
    _elegir(page, "#id_tipo", "Instrucción de pago")
    page.fill("#id_descripcion", "Instruir a la Fiduciaria el pago de la ministración 1 (70 %).")
    _elegir(page, "#id_expedientes", re.escape(folio))
    page.fill("#id_ministracion", "1")
    page.click("button:has-text('Registrar acuerdo')")
    expect(page.locator("#tabla-acuerdos")).to_contain_text("Ministración 1")
    captura("recorrido_sprint_2_psa_03_instruccion_de_pago_del_comite")

    # ---- 4. Dirección: solicita la ministración con todos sus soportes ------------------------------------------------
    r.relevo("dir_drff")
    r.abrir(folio, "Contrato firmado")
    r.siguiente_paso("Solicitar la ministración 1")
    expect(page.locator("[data-prueba=soportes-m1] .badge.text-bg-danger")).to_have_count(0)
    page.click("[data-prueba=form-envio-m1] button")
    expect(page.locator("[data-prueba=envio-solicitud]")).to_contain_text("Enviada a Administración y Finanzas el")
    captura("recorrido_sprint_2_psa_04_solicitud_enviada")

    # ---- 5. Administración y Finanzas: acepta; no la paga (PSAHEM paga con cheque por la Fiduciaria) ---------------
    r.relevo("finanzas")
    r.abrir(folio, "Ministración solicitada")
    r.siguiente_paso("Revisar la solicitud de pago de la ministración 1")
    page.click("[data-prueba=form-revision-m1] button:has-text('Aceptar')")
    expect(page.locator("[data-prueba=revision-m1]")).to_contain_text("Aceptada")
    expect(page.locator("[data-prueba=form-pago-m1]")).to_have_count(0)
    captura("recorrido_sprint_2_psa_05_solicitud_aceptada")
    r.fuera_de_bandeja(folio)                         # una solicitud aceptada de PSAHEM espera a la Secretaría Técnica

    # ---- 6. Secretaría Técnica: solicita el pago a la Fiduciaria dentro de sus 5 días hábiles ------------------------
    r.relevo("comite")
    expect(page.locator("[data-prueba=panel-por-remitir]")).to_contain_text(folio)
    # HALLAZGO (menor): la solicitud aceptada que la Secretaría Técnica debe remitir NO sale en la tabla «por atender» de su
    # bandeja (solo en el panel «Pagos por solicitar a la Fiduciaria» y en «Todos los míos»): se entra por el panel.
    page.click(f"[data-prueba=panel-por-remitir] a:has-text('{folio}')")
    r.siguiente_paso("Solicitar el pago a la Fiduciaria")
    expect(page.locator("[data-prueba=plazo-remision]")).to_contain_text("5 días hábiles")
    page.fill("#id_oficio", "ST-FIPASAHEM/001/2026")
    page.click("[data-prueba=form-remision-m1] button:has-text('Solicitar el pago')")
    expect(page.locator("[data-prueba=remision-m1]")).to_contain_text("en plazo")
    captura("recorrido_sprint_2_psa_06_remision_a_la_fiduciaria")

    # ---- 7. Fiduciaria: emite el cheque y lo envía a la Delegación (HU-5.3) --------------------------------------------
    r.relevo("fiduciaria")
    r.abrir(folio, "Remitida a la Fiduciaria")
    r.siguiente_paso("Emitir el cheque")
    page.fill("#id_numero", "CHQ-FIPASAHEM-0001")
    page.fill("#id_fecha_emision", timezone.localdate().isoformat())
    page.click("[data-prueba=form-emision-m1] button:has-text('Emitir el cheque')")
    expect(page.locator("[data-prueba=cheque-m1]")).to_contain_text("CHQ-FIPASAHEM-0001")
    captura("recorrido_sprint_2_psa_07_cheque_emitido")
    r.abrir(folio, "Cheque emitido")
    r.siguiente_paso("Enviar el cheque a la Delegación")
    page.click("button:has-text('Enviar el cheque a la Delegación')")
    expect(page.locator("[data-prueba=envio-cheque]")).to_contain_text("Enviado a")
    captura("recorrido_sprint_2_psa_08_cheque_enviado")

    # ---- 8. Delegación: entrega el cheque a la persona; se ve el vencimiento del cobro -----------------------------
    r.relevo(delegacion)
    expect(page.locator("[data-prueba=panel-cheques-por-entregar]")).to_contain_text(folio)
    r.abrir(folio, "Cheque en la Delegación")
    r.siguiente_paso("Registrar la entrega del cheque")
    page.fill("#id_recibe_nombre", exp.solicitante.nombre)
    page.click("[data-prueba=form-entrega-m1] button:has-text('Registrar la entrega')")
    expect(page.locator("[data-prueba=entrega-cheque]")).to_contain_text("Entregado el")
    expect(page.locator("[data-prueba=cobro-cheque]")).to_contain_text("Debe cobrarlo a más tardar")
    captura("recorrido_sprint_2_psa_09_cheque_entregado_y_vencimiento_del_cobro")
    ir_a(page, "Cheques")
    expect(page.locator("[data-prueba=cheques-por-cobrar]")).to_contain_text("CHQ-FIPASAHEM-0001")

    # ---- 9. Dirección: expediente con el cheque entregado y la bitácora completa ---------------------------------------
    r.relevo("dir_drff")
    r.abrir(folio, "Cheque entregado")
    filas = r.bitacora()
    comprobar_bitacora(filas, ["Persona beneficiaria|Contrato firmado", "Ministración solicitada", "Remitida a la Fiduciaria",
                               "Cheque emitido", "Cheque en la Delegación", "Cheque entregado"],
                       [r.unidades[u] for u in ("dir_drff", delegacion, "comite", "finanzas", "fiduciaria")])
    captura("recorrido_sprint_2_psa_10_expediente_con_cheque_entregado_y_bitacora")
    assert Expediente.objects.get(folio=folio).estado.clave == "cheque_entregado"
