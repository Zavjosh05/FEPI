"""HU-2.4 · Recorrido de la sesión de seguimiento con capturas."""
from playwright.sync_api import expect

from dictamen import seguimiento, sesiones
from dictamen.models import TipoSesion
from nucleo.models import Ejercicio, Usuario
from pruebas.fixtures_m2 import documento_sesion, fecha_sesion, psa, registrar_validada  # noqa: F401


def _sesion(u, ejercicio):
    s = sesiones.crear_sesion(u["comite"], ejercicio, TipoSesion.SEGUIMIENTO, fecha_sesion(6), "Sala de juntas de PROBOSQUE",
                              "Lista de asistencia y quórum\nSeguimiento de casos del ejercicio\nAsuntos generales")
    sesiones.agregar_documento(u["comite"], s, documento_sesion(), "Casos para seguimiento")
    sesiones.enviar_convocatoria(u["comite"], s)
    return s


def test_hu_2_4_recorrido_sesion_de_seguimiento(datos_e2e, psa, page, live_server, entrar, captura):  # noqa: F811
    u = {x.username: x for x in Usuario.objects.all()}
    cc = Ejercicio.objects.get(programa__clave="CC", anio=2026)
    exp = registrar_validada(u, cc, nombre="Predio Agua Blanca", solicitante="Hilario Gómez Becerril")
    s = _sesion(u, cc)

    entrar("comite")
    page.goto(f"{live_server.url}/dictamen/sesiones/{s.pk}/")
    page.select_option("#id_tipo", "caso_fortuito")
    page.fill("#id_descripcion", "Atender el aviso de incendio en la parte baja del predio y ajustar la propuesta FO-PB-520-B.")
    page.select_option("#id_expedientes", [str(exp.pk)])
    page.click("button:has-text('Registrar acuerdo')")
    expect(page.locator("#tabla-acuerdos")).to_contain_text("Dirección de Restauración y Fomento Forestal")
    captura("hu_2_4_01_acuerdo_con_expedientes_y_area_responsable")

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
