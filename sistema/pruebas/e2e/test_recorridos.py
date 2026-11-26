"""Recorridos de Playwright, uno por historia, con capturas en entregas/sprint_1/capturas/."""
import json
import re

import pytest
from playwright.sync_api import expect

from nucleo.demo import cargar_demo, completar_requisitos, cuadro_en_municipio
from nucleo.models import Ejercicio, Expediente, Municipio, Usuario
from recepcion import servicios


def _solicitud(usuario="del_amecameca", municipio="Amecameca", refrendo=False, nombre="Predio La Joya"):
    cc = Ejercicio.objects.get(programa__clave="CC", anio=2026)
    datos = servicios.DatosSolicitud(
        ejercicio=cc, municipio=Municipio.objects.get(nombre=municipio), nombre_predio=nombre,
        tipo_persona=cc.tipos_persona.get(clave="fisica"), modalidad=cc.modalidades.get(clave="reforestacion"),
        solicitante_nombre="Silvia Romero Ávila", solicitante_tipo="fisica", es_refrendo=refrendo,
    )
    return servicios.registrar_solicitud(Usuario.objects.get(username=usuario), datos)


def _elegir(page, selector, patron):
    """Elige la opción cuyo texto coincide con la expresión regular (select_option pide texto exacto)."""
    opciones = page.locator(f"{selector} option").all()
    for o in opciones:
        if re.search(patron, o.inner_text()):
            page.select_option(selector, o.get_attribute("value"))
            return
    raise AssertionError(f"No hay opción {patron} en {selector}")


def test_hu_1_1_recorrido_registro_de_la_solicitud(datos_e2e, page, live_server, entrar, captura):
    cargar_demo()
    page.goto(f"{live_server.url}/entrar/")
    captura("hu_1_1_01_inicio_de_sesion")
    entrar("del_amecameca")
    expect(page.locator("[data-prueba=unidad]")).to_contain_text("Amecameca")
    captura("hu_1_1_02_bandeja_delegacion")

    page.click("text=Registrar solicitud >> nth=0")
    page.wait_for_url("**/recepcion/registrar/")
    _elegir(page, "#id_tipo_persona", "Persona física")
    _elegir(page, "#id_modalidad", "Reforestación")
    page.fill("#id_nombre_predio", "Predio Tepetlixpa Alto")
    page.fill("#id_superficie_solicitada_ha", "4.5")
    page.fill("#id_solicitante_nombre", "Teresa Aguilar Montiel")
    page.fill("#id_curp", "AUMT750210MMCGNR03")
    _elegir(page, "#id_municipio", "^Toluca")
    expect(page.locator("#delegacion-municipio")).to_contain_text("Delegación Regional Forestal Toluca")
    captura("hu_1_1_03_registro_municipio_de_otra_delegacion")
    page.click("button:has-text('Registrar y generar acuse')")
    expect(page.locator("[data-prueba=error-municipio]")).to_contain_text("Delegación Regional Forestal Toluca")
    captura("hu_1_1_04_registro_rechazado")

    _elegir(page, "#id_municipio", "^Tepetlixpa")
    expect(page.locator("#delegacion-municipio")).to_contain_text("lo atiende esta Delegación")
    page.click("button:has-text('Registrar y generar acuse')")
    page.wait_for_url("**/recepcion/expediente/**")
    expect(page.locator(".alert-success")).to_contain_text("Acuse de recepción")
    expect(page.locator("[data-prueba=acuse-recepcion]")).to_be_visible()
    captura("hu_1_1_05_solicitud_registrada_con_acuse")
    exp = Expediente.objects.get(predio__nombre="Predio Tepetlixpa Alto")
    assert exp.acuses.filter(tipo="recepcion").exists()

    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server.url}/bandeja/")
    captura("hu_1_1_06_bandeja_movil")


def test_hu_1_2_recorrido_revision_y_envio(datos_e2e, page, live_server, entrar, captura, tmp_path):
    exp = _solicitud()
    entrar("del_amecameca")
    page.goto(f"{live_server.url}/recepcion/expediente/{exp.folio}/?pestana=requisitos")
    expect(page.locator("[data-prueba=boton-enviar]")).to_be_disabled()
    captura("hu_1_2_01_requisitos_sin_revisar")

    curp = exp.revisiones.get(requisito__clave="CC-REQ-08")
    fila = page.locator(f"#req-{curp.pk}")
    archivo = tmp_path / "curp.pdf"
    from nucleo.demo import _pdf_demo
    archivo.write_bytes(_pdf_demo("CURP"))
    fila.locator("button:has-text('Revisar')").click()
    fila.locator("select[name=estado]").select_option("entregado")
    fila.locator("input[name=archivo]").set_input_files(str(archivo))
    fila.locator("button:has-text('Guardar')").click()
    expect(page.locator(f"#req-{curp.pk} [data-prueba=estado-req]")).to_have_text("Entregado")
    expect(page.locator("[data-prueba=panel-envio]")).to_contain_text("1 entregados")
    captura("hu_1_2_02_requisito_entregado_htmx")

    completar_requisitos(Usuario.objects.get(username="del_amecameca"), exp)
    page.reload()
    expect(page.locator("[data-prueba=boton-enviar]")).to_be_enabled()
    captura("hu_1_2_03_expediente_completo")
    page.click("[data-prueba=boton-enviar]")
    page.wait_for_url("**pestana=documentos")
    expect(page.locator("#tabla-acuses")).to_contain_text("envío del expediente digital")
    captura("hu_1_2_04_envio_con_acuse")

    entrar("dir_drff")
    expect(page.locator("#tabla-bandeja")).to_contain_text(exp.folio)
    captura("hu_1_2_05_bandeja_direccion")


def test_hu_1_3_recorrido_ubicacion_del_predio(datos_e2e, page, live_server, entrar, captura, tmp_path):
    exp = _solicitud()
    entrar("del_amecameca")
    page.goto(f"{live_server.url}/recepcion/expediente/{exp.folio}/?pestana=ubicacion")
    page.wait_for_selector("#mapa[data-listo='1']")
    captura("hu_1_3_01_ubicacion_sin_poligono")

    ruta = tmp_path / "poligono_campo.geojson"
    ruta.write_text(json.dumps({"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"nombre": "Predio La Joya"},
        "geometry": json.loads(cuadro_en_municipio(exp.predio.municipio, 12).geojson)}]}))
    page.set_input_files("#id_archivo", str(ruta))
    # Al elegir el archivo se ve en el mapa (vista previa) antes de registrarlo
    expect(page.locator("[data-prueba=vista-previa-poligono]")).to_contain_text("aún sin registrar")
    expect(page.locator("[data-prueba=vista-previa-poligono]")).to_contain_text("12.00 ha, dentro del municipio")
    assert page.evaluate("() => { let n = 0; window.mapaPoligono.eachLayer(l => { if (l.getTooltip && l.getTooltip() "
                         "&& String(l.getTooltip().getContent()).includes('sin registrar')) n++; }); return n; }") >= 1
    assert not exp.poligonos.exists()
    captura("hu_1_3_02a_vista_previa_del_archivo")
    page.fill("#id_responsable", "Ing. Carlos Ortega")
    page.click("button:has-text('Registrar polígono')")
    page.wait_for_selector("#mapa[data-listo='1']")
    expect(page.locator("[data-prueba=poligono-vigente]")).to_contain_text("ha")
    captura("hu_1_3_02_poligono_cargado")

    # Respaldo: dibujar el nuevo polígono en el mapa con Leaflet-Geoman (cambio de lugar).
    page.click(".leaflet-pm-icon-polygon")
    caja = page.locator("#mapa").bounding_box()
    x0, y0 = caja["x"] + caja["width"] * 0.15, caja["y"] + caja["height"] * 0.2
    puntos = [(x0, y0), (x0 + 90, y0), (x0 + 90, y0 + 70), (x0, y0 + 70)]
    for x, y in puntos:
        page.mouse.click(x, y)
    page.mouse.click(*puntos[0])
    page.wait_for_function("document.querySelector('#form-poligono input[name=dibujo]').value.length > 0")
    page.fill("#id_responsable", "Servicios Técnicos Forestales del Oriente")
    page.select_option("#id_levantado_por", "prestador")
    page.fill("#id_prestador_rfn", "RFN-MEX-PSF-0421")
    page.fill("#id_motivo_cambio", "La persona solicitante propuso otra área del predio.")
    captura("hu_1_3_03_dibujo_en_el_mapa")
    page.click("button:has-text('Registrar polígono')")
    page.wait_for_selector("#mapa[data-listo='1']")
    expect(page.locator("#historial-poligonos tbody tr")).to_have_count(2)
    expect(page.locator("#historial-poligonos")).to_contain_text("Anterior")
    captura("hu_1_3_04_historial_anterior_y_nuevo")
    assert exp.poligonos.count() == 2 and exp.poligonos.filter(vigente=True).count() == 1


def test_hu_1_4_recorrido_validacion_y_aviso_de_faltantes(datos_e2e, page, live_server, entrar, captura):
    from django.utils import timezone

    deleg = Usuario.objects.get(username="del_amecameca")
    exp = _solicitud(nombre="Predio Los Encinos")
    completar_requisitos(deleg, exp)
    servicios.enviar_a_direccion(deleg, exp)
    hoy = timezone.localdate()
    refrendo = _solicitud(refrendo=True, nombre="Predio Refrendo Las Palomas")
    completar_requisitos(deleg, refrendo, fecha_archivo=hoy.replace(year=hoy.year - 2))
    servicios.enviar_a_direccion(deleg, refrendo)

    entrar("dir_drff")
    captura("hu_1_4_01_bandeja_direccion")
    page.goto(f"{live_server.url}/recepcion/expediente/{exp.folio}/validar/")
    plano = exp.revisiones.get(requisito__clave="CC-REQ-13")
    ine = exp.revisiones.get(requisito__clave="CC-REQ-06")
    page.check(f"input[name=faltante][value='{plano.pk}']")
    page.check(f"input[name=faltante][value='{ine.pk}']")
    page.fill(f"#obs-{plano.pk}", "El plano no trae la coordenada de un vértice del predio.")
    page.fill("#observaciones", "Se piden dos documentos.")
    # Sin la observación del segundo faltante el navegador no deja emitir el aviso (campo obligatorio).
    page.click("button:has-text('Emitir aviso de faltantes')")
    expect(page).to_have_url(f"{live_server.url}/recepcion/expediente/{exp.folio}/validar/")
    page.fill(f"#obs-{ine.pk}", "La identificación oficial está vencida.")
    captura("hu_1_4_02_pantalla_de_validacion")
    page.click("button:has-text('Emitir aviso de faltantes')")
    page.wait_for_url("**pestana=validacion")
    expect(page.locator("[data-prueba=fecha-limite]")).to_be_visible()
    expect(page.locator("[data-prueba=faltantes-con-observacion]")).to_contain_text("La identificación oficial está vencida.")
    expect(page.locator("[data-prueba=faltantes-con-observacion]")).to_contain_text("El plano no trae la coordenada")
    captura("hu_1_4_03_aviso_de_faltantes_con_fecha_limite")

    entrar("del_amecameca")
    page.goto(f"{live_server.url}/recepcion/expediente/{exp.folio}/?pestana=validacion")
    page.click("button:has-text('Registrar notificación')")
    expect(page.locator("[data-prueba=aviso-faltantes]")).to_contain_text("Notificado a la persona solicitante")
    captura("hu_1_4_04_notificacion_por_conducto_de_la_delegacion")

    entrar("dir_drff")
    page.goto(f"{live_server.url}/recepcion/expediente/{refrendo.folio}/validar/")
    expect(page.locator("#tabla-validacion")).to_contain_text("vigente")
    captura("hu_1_4_05_refrendo_documentacion_vigente")
    page.click("button:has-text('Validar expediente')")
    page.wait_for_url("**pestana=validacion")
    expect(page.locator("[data-prueba=estado]")).to_have_text("Validado · en dictamen")
    captura("hu_1_4_06_expediente_validado")
    page.goto(f"{live_server.url}/recepcion/expediente/{refrendo.folio}/?pestana=bitacora")
    captura("hu_1_4_07_bitacora")
    page.goto(f"{live_server.url}/recepcion/expediente/{exp.folio}/?pestana=trazabilidad")
    expect(page.locator("#tabla-trazabilidad")).to_contain_text("Observación de la validación")
    captura("hu_1_4_08_trazabilidad")
