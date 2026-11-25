"""HU-2.4 · Recorrido de reasignaciones e incidentes (sesión de seguimiento) con capturas."""
from decimal import Decimal

from playwright.sync_api import expect

from dictamen import aprobacion, juridico, seguimiento, sesiones, tecnico
from dictamen.models import TipoSesion
from nucleo.models import Ejercicio, Usuario
from pruebas.fixtures_m2 import (  # noqa: F401
    despues_de, documento_sesion, fecha_sesion, propiedad_en_regla, psa, registrar_validada,
)


def _dictaminada(u, cc, **kw):
    exp = registrar_validada(u, cc, **kw)
    tecnico.dictaminar(u["dir_drff"], exp, "factible", "Cumple los criterios técnicos.")
    juridico.dictaminar(u["juridica"], exp, "procedente", "Documentación y propiedad en regla.", propiedad=propiedad_en_regla(exp))
    return exp


def _acta(u, cc):
    """Acta con dos personas beneficiarias ($10,000 c/u) y dos solicitudes en lista de espera."""
    b1 = _dictaminada(u, cc, nombre="La Joya Alta", ha=5, solicitante="Pablo Juárez Santana")
    b2 = _dictaminada(u, cc, nombre="Los Encinos", municipio="Tlalmanalco", ha=5, solicitante="Ernestina Flores Medina")
    e1 = _dictaminada(u, cc, nombre="Las Trojes", municipio="Ozumba", ha=4.5, solicitante="Martina Colín Reyes")
    e2 = _dictaminada(u, cc, nombre="Potrero Viejo", municipio="Ayapango", ha=6, solicitante="Sergio Ayala Pineda")
    s = sesiones.crear_sesion(u["comite"], cc, TipoSesion.APROBACION, fecha_sesion(6), "Sala de juntas", "Quórum\nListados")
    sesiones.agregar_documento(u["comite"], s, documento_sesion(), "Listado preliminar")
    sesiones.enviar_convocatoria(u["comite"], s)
    aprobacion.proponer_listados(u["comite"], s, Decimal("20000"))
    aprobacion.registrar_acta(u["comite"], s, True, "Unanimidad", momento=despues_de(s))
    return b1, b2, e1, e2


def _sesion(u, ejercicio):
    s = sesiones.crear_sesion(u["comite"], ejercicio, TipoSesion.SEGUIMIENTO, fecha_sesion(6), "Sala de juntas de PROBOSQUE",
                              "Lista de asistencia y quórum\nSeguimiento de casos del ejercicio\nAsuntos generales")
    sesiones.agregar_documento(u["comite"], s, documento_sesion(), "Casos para seguimiento")
    sesiones.enviar_convocatoria(u["comite"], s)
    return s


def test_hu_2_4_recorrido_sesion_de_seguimiento(datos_e2e, psa, page, live_server, entrar, captura):  # noqa: F811
    u = {x.username: x for x in Usuario.objects.all()}
    cc = Ejercicio.objects.get(programa__clave="CC", anio=2026)
    joya, encinos, trojes, potrero = _acta(u, cc)
    exp = encinos
    s = _sesion(u, cc)

    entrar("comite")
    page.goto(f"{live_server.url}/dictamen/sesiones/{s.pk}/")
    expect(page.locator("[data-prueba=lista-espera]")).to_contain_text(trojes.folio)
    page.select_option("#id_tipo", "caso_fortuito")
    page.fill("#id_causa", "Aviso de incendio de la Delegación Amecameca del 12/11/2026.")
    page.fill("#id_descripcion", "Atender el aviso de incendio en la parte baja del predio y ajustar la propuesta FO-PB-520-B.")
    page.select_option("#id_expedientes", [str(exp.pk)])
    page.click("button:has-text('Registrar acuerdo')")
    expect(page.locator("#tabla-acuerdos")).to_contain_text("Dirección de Restauración y Fomento Forestal")
    expect(page.locator("#tabla-acuerdos")).to_contain_text("Causa: Aviso de incendio")
    captura("hu_2_4_01_acuerdo_con_expedientes_y_area_responsable")

    # Incidente: desistimiento de una persona beneficiaria (sale de la lista y libera su recurso).
    page.select_option("#id_tipo", "desistimiento")
    page.fill("#id_causa", "Escrito de desistimiento presentado en la Delegación el 10/11/2026.")
    page.fill("#id_descripcion", "Se acepta el desistimiento y se libera el recurso.")
    page.select_option("#id_expedientes", [str(joya.pk)])
    page.click("button:has-text('Registrar acuerdo')")
    expect(page.locator("[data-prueba=recurso-liberado]")).to_have_text("$10,000.00")
    captura("hu_2_4_06_desistimiento_libera_el_recurso")
    # Reasignación: si se salta el orden de la lista de espera, el sistema lo impide.
    page.select_option("#id_tipo", "reasignacion")
    page.fill("#id_descripcion", "Reasignar el recurso liberado.")
    page.select_option("#id_expedientes", [str(potrero.pk)])
    page.click("button:has-text('Registrar acuerdo')")
    expect(page.locator("#mensajes .alert-danger")).to_contain_text("orden de la lista de espera")
    page.select_option("#id_tipo", "reasignacion")
    page.fill("#id_descripcion", "Reasignar el recurso liberado a la primera solicitud de la lista de espera.")
    page.select_option("#id_expedientes", [str(trojes.pk)])
    page.click("button:has-text('Registrar acuerdo')")
    expect(page.locator("[data-prueba=movimientos]")).to_contain_text(trojes.folio)
    captura("hu_2_4_07_reasignacion_en_orden_de_la_lista_de_espera")
    page.goto(f"{live_server.url}/dictamen/beneficiarios/?ejercicio={cc.pk}")
    expect(page.locator("[data-prueba=reasignada]")).to_contain_text(trojes.folio)
    expect(page.locator("#tabla-bajas")).to_contain_text(joya.folio)
    captura("hu_2_4_08_beneficiarios_con_reasignacion_y_baja")
    page.goto(f"{live_server.url}/dictamen/candidatos/?ejercicio={cc.pk}")
    expect(page.locator("#tabla-candidatos")).to_contain_text(potrero.folio)
    captura("hu_2_4_09_candidatos_lista_de_espera")
    page.goto(f"{live_server.url}/recepcion/expediente/{trojes.folio}/?pestana=trazabilidad")
    expect(page.locator("#tabla-trazabilidad")).to_contain_text("Movimiento de listado")
    captura("hu_2_4_10_trazabilidad_de_la_reasignacion")

    entrar("dir_drff")
    expect(page.locator("[data-prueba=acuerdos-pendientes]")).to_contain_text("incendio")
    captura("hu_2_4_02_pendiente_en_la_bandeja_de_la_direccion")
    page.fill("[data-prueba=acuerdos-pendientes] input[name=observaciones]", "Se ajustó la propuesta con la Delegación.")
    page.click("button:has-text('Marcar cumplido')")
    expect(page.locator(".alert-success")).to_contain_text("cumplido")
    captura("hu_2_4_03_acuerdo_cumplido")

    pago = registrar_validada(u, psa, nombre="Predio Manantiales (PSAHEM)", modalidad=None,
                              solicitante="Comunidad de San Pedro")
    sp = _sesion(u, psa)
    seguimiento.registrar_acuerdo(u["comite"], sp, "instruccion_pago",
                                  "Instruir a la Fiduciaria el pago de la primera ministración (70 %).", [pago], ministracion=1)
    entrar("comite")
    page.goto(f"{live_server.url}/dictamen/sesiones/{sp.pk}/")
    expect(page.locator("#tabla-acuerdos")).to_contain_text("Ministración 1")
    captura("hu_2_4_04_instruccion_de_pago_psahem_por_ministracion")
    entrar("fiduciaria")
    expect(page.locator("[data-prueba=acuerdos-pendientes]")).to_contain_text("70 %")
    captura("hu_2_4_05_bandeja_de_la_fiduciaria")
