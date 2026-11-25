"""HU-6.3 · Cierre del ejercicio: resultados finales que coinciden con las verificaciones y los pagos (con la comprobación que
señala cada diferencia), cierre del expediente (también «sin recurso por devolver»), padrón de personas beneficiarias publicado
sin cuenta y actualizado solo, e informe anual al Comité con la fecha y la hora de su envío y de su recepción."""
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from dictamen.models import DocumentoSesion, PersonaIncumplida
from ejecucion import verificacion
from nucleo import extensiones, reloj
from nucleo.models import Evento
from pagos.models import SolicitudPago
from seguimiento import cierre, incumplimientos, reasignacion, registro
from seguimiento.models import CierreExpediente

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de, direccion_de
from .fixtures_m4 import *  # noqa: F401,F403
from .fixtures_m5 import *  # noqa: F401,F403
from .test_hu_4_2 import _archivo, _por_verificar
from .test_hu_6_1 import _acordar_y_cumplir, _desistir, _sesion
from .test_hu_6_2 import _con_omision_vencida, _cuenta, _cumplir

pytestmark = pytest.mark.django_db


def _concluida(pagada, usuarios, programa="CC"):
    """CC de 4 ha con el pago único, verificado y dado por concluido: todo cuadra."""
    exp = _por_verificar(pagada, usuarios, programa, "2026-11-12 10:00", date(2026, 11, 11), ha=4)
    with reloj.en("2026-11-20 10:00"):
        verificacion.registrar_verificacion(delegado_de(usuarios, exp), exp, "informe_final_firmado", _archivo("i.pdf"),
                                            superficie_verificada="4")
        verificacion.dar_por_concluida(usuarios["dir_drff"], exp)
    exp.refresh_from_db()
    return exp


def _cancelar(usuarios, exp, avisar=True):
    """Omisión sin subsanar, señalamiento confirmado y cancelación por acuerdo del Comité (queda ``cancelada``)."""
    if avisar:
        with reloj.en("2026-09-01 10:00"):
            incumplimientos.avisar_omision(direccion_de(usuarios, exp.ejercicio), exp, "No entregó la evidencia de los trabajos.",
                                           date(2026, 9, 15))
    incumplimientos.revisar(date(2026, 9, 16))
    s = incumplimientos.Senalamiento.objects.get(expediente=exp)
    incumplimientos.confirmar(usuarios["dir_drff"], s)
    s.refresh_from_db()
    _cumplir(usuarios, s.propuesta)
    exp.refresh_from_db()
    assert exp.estado.clave == "cancelada"
    return exp


def _cancelada_y_reintegrada(pagada, usuarios):
    exp, _ = _con_omision_vencida(pagada, usuarios)
    return _cancelar(usuarios, exp, avisar=False)


def _reintegrar(usuarios, exp):
    _cuenta(usuarios)
    req = exp.requerimientos.get()
    incumplimientos.emitir_requerimiento(usuarios["juridica"], req)
    req.refresh_from_db()
    incumplimientos.comprobar_deposito(usuarios["finanzas"], req, timezone.localdate(), req.monto_total, "DEP-6-3", _archivo("deposito.pdf"))
    exp.refresh_from_db()
    return req


def test_hu_6_3_criterios_y_necesidades_vienen_del_modelo(modelo, necesidades):
    hu = historia(modelo, "HU-6.3")
    assert "trazabilidad" in hu["criterios"][-1]
    assert hu["criterios"][:-1] == ["Los resultados finales coinciden con las verificaciones y los pagos.",
                               "El padrón está publicado y actualizado.",
                               "Existe la fecha y la hora del envío del informe al Comité."]
    funcion = next(f for m in modelo["modulos"] for f in m["funciones"] if f["id"] == "M6.3")
    assert {"CC-ARP-08", "MFS-ARP-08", "PS-ARP-08", "RHF-ARP-08", "PSA-ARP-08", "PEG-DPF-07"} <= set(funcion["necesidades"])
    assert "padrón" in necesidades["PEG-DPF-07"]["texto"].lower() or "padron" in necesidades["PEG-DPF-07"]["texto"].lower()


# ----------------------------------------------------------------------------- criterio 1
def test_hu_6_3_los_resultados_finales_coinciden_con_las_verificaciones_y_los_pagos_y_se_cierra(pagada, usuarios):
    exp = _concluida(pagada, usuarios)
    assert exp.estado.clave == "concluida"
    fila = cierre.resultado_expediente(exp)
    assert fila["diferencias"] == [] and fila["aprobado"] == fila["pagado"] > 0 and fila["reintegrado"] == 0
    assert "4 ha" in fila["verificado"]["texto"] and fila["puede_cerrar"]
    filas, total = cierre.resultados_ejercicio(exp.ejercicio)
    assert total["pagado"] == fila["pagado"] and total["aprobado"] == fila["aprobado"] and total["listos"] == 1
    with pytest.raises(PermissionDenied):
        cierre.cerrar_expediente(delegado_de(usuarios, exp), exp)
    with pytest.raises(PermissionDenied):
        cierre.cerrar_expediente(usuarios["dir_dpf"], exp)                      # otra Dirección
    with reloj.en("2026-11-23 10:30"):
        cierre.cerrar_expediente(usuarios["dir_drff"], exp)
    exp.refresh_from_db()
    c = exp.cierre
    assert exp.estado.clave == "ejercicio_cerrado" and c.tipo == "con_resultados" and c.cerrado_por == usuarios["dir_drff"]
    assert c.resumen["pagado"] == str(fila["pagado"]) and timezone.localtime(c.cerrado_en).strftime("%d/%m/%Y %H:%M") == "23/11/2026 10:30"
    assert dict(c.acuse.contenido["renglones"])["Cierre"] == "Cerrado con resultados finales"
    assert exp.eventos.filter(tipo="cierre_expediente", acuse=c.acuse).exists()
    with pytest.raises(ValidationError, match="ya está cerrado"):
        cierre.cerrar_expediente(usuarios["dir_drff"], exp)


def test_hu_6_3_la_comprobacion_senala_cada_diferencia_y_no_deja_cerrar(pagada, usuarios):
    a, b, c = pagada("CC", cuantas=3)
    # a) lo pagado rebasa lo aprobado y el pago no coincide con su solicitud
    SolicitudPago.objects.filter(expediente=a, ministracion=1).update(importe=Decimal("99999.00"))
    claves = {d["clave"] for d in cierre.comprobar_expediente(a)}
    assert {"pagado_mayor_aprobado", "pago_distinto_solicitud"} <= claves
    with pytest.raises(ValidationError, match="Pagado mayor que lo aprobado"):
        cierre.cerrar_expediente(usuarios["dir_drff"], a)
    # b) una ministración pagada sin la verificación que la regla exige
    sol = b.solicitudes_pago.get(ministracion=1)
    SolicitudPago.objects.create(expediente=b, ministracion=2, porcentaje=30, importe=Decimal("3600.00"), tipo_pago=sol.tipo_pago,
                                 estado="pagada", preparada_por=usuarios["dir_drff"])
    difs = cierre.comprobar_expediente(b)
    assert [d["clave"] for d in difs] == ["pagado_sin_verificacion"] and "Ministración 2" in difs[0]["detalle"]
    # c) sin diferencias, pero falta pagar la segunda ministración: todavía no se cierra
    assert cierre.comprobar_expediente(c) == []
    puede, motivo = cierre.puede_cerrar(c)
    assert not puede and "ministración 2" in motivo
    # las diferencias salen en los resultados del ejercicio y en el CSV
    filas, total = cierre.resultados_ejercicio(a.ejercicio)
    assert total["con_diferencias"] == 2 and {f["folio"] for f in filas if f["diferencias"]} == {a.folio, b.folio}
    texto = cierre.resultados_csv(a.ejercicio)
    assert "Pagado mayor que lo aprobado" in texto and "Pagado sin la verificación que la regla exige" in texto and "TOTAL" in texto


def test_hu_6_3_verificado_sin_pago_se_senala(pagada, usuarios):
    exp = _por_verificar(pagada, usuarios, "PS")
    with reloj.en("2026-10-05 10:00"):
        verificacion.registrar_verificacion(delegado_de(usuarios, exp), exp, "formato_verificacion", _archivo("f.pdf"),
                                            superficie_verificada="4")
    exp.refresh_from_db()
    assert exp.estado.clave == "verificada"
    difs = cierre.comprobar_expediente(exp)
    assert [d["clave"] for d in difs] == ["verificado_sin_pago"] and "ministración 2" in difs[0]["detalle"]
    assert not cierre.puede_cerrar(exp)[0]


def test_hu_6_3_cancelado_sin_requerimiento_resuelto_se_senala_y_con_el_reintegro_se_cierra(pagada, usuarios):
    exp = _cancelada_y_reintegrada(pagada, usuarios)
    assert [d["clave"] for d in cierre.comprobar_expediente(exp)] == ["cancelado_sin_requerimiento"]
    assert not cierre.puede_cerrar(exp)[0]
    _reintegrar(usuarios, exp)
    assert exp.estado.clave == "reintegrada" and cierre.comprobar_expediente(exp) == []
    fila = cierre.resultado_expediente(exp)
    assert fila["reintegrado"] == fila["pagado"] == Decimal("8400.00") and fila["liberado"] > fila["pagado"] - 1
    assert cierre.situacion_en_padron(exp)[0] == "cancelada"
    cierre.cerrar_expediente(usuarios["dir_drff"], exp)
    exp.refresh_from_db()
    assert exp.estado.clave == "ejercicio_cerrado" and exp.cierre.tipo == "reintegrada"
    assert cierre.situacion_en_padron(exp)[0] == "cancelada"                       # cerrado, sigue dado de baja
    assert PersonaIncumplida.objects.filter(persona=exp.beneficiaria, activa=True).exists()


def test_hu_6_3_cancelado_sin_recurso_por_devolver_se_cierra(entregado, usuarios):
    from datetime import timedelta

    exp, cheque = entregado()
    type(cheque).objects.filter(pk=cheque.pk).update(entregado_en=timezone.now() - timedelta(days=120))
    incumplimientos.revisar(timezone.localdate())
    s = incumplimientos.Senalamiento.objects.get(expediente=exp, tipo="cheque_vencido")
    incumplimientos.confirmar(usuarios["dir_drff"], s)
    s.refresh_from_db()
    _cumplir(usuarios, s.propuesta)
    exp.refresh_from_db()
    assert exp.estado.clave == "cancelada" and exp.requerimientos.get().estado == "sin_monto"
    assert cierre.comprobar_expediente(exp) == [] and cierre.puede_cerrar(exp) == (True, "")
    assert registro.siguiente_paso(usuarios["dir_drff"], exp)["texto"] == "Cerrar el expediente"
    cierre.cerrar_expediente(usuarios["dir_drff"], exp)
    exp.refresh_from_db()
    assert exp.estado.clave == "ejercicio_cerrado" and exp.cierre.tipo == "sin_recurso"
    assert exp.cierre.motivo == "Cerrado sin recurso por devolver" and exp.cierre.acuse.folio


def test_hu_6_3_cerrar_los_listos_deja_los_demas_abiertos_con_su_motivo(pagada, usuarios):
    listo = _concluida(pagada, usuarios)
    cerrados, omitidos = cierre.cerrar_listos(usuarios["dir_drff"], listo.ejercicio)
    assert cerrados == [listo] and omitidos == []
    assert cierre.cerrar_listos(usuarios["dir_drff"], listo.ejercicio) == ([], [])
    with pytest.raises(PermissionDenied):
        cierre.cerrar_listos(usuarios["dir_dpf"], listo.ejercicio)


# ----------------------------------------------------------------------------- criterio 2
def test_hu_6_3_el_padron_se_publica_sin_cuenta_con_las_columnas_de_las_reglas_y_se_actualiza_solo(pagada, usuarios, client, contrasena):
    exp, exp2 = pagada("CC", cuantas=2)
    persona = exp.beneficiaria
    persona.curp, persona.rfc, persona.telefono = "LAPB800101MMCRNT05", "LAPB800101AB1", "722 555 0100"
    persona.save()
    ej = exp.ejercicio
    url = reverse("padron:programa", args=[ej.programa.clave, ej.anio])
    assert client.get(url).status_code == 404                                         # aún no se publica
    with pytest.raises(PermissionDenied):
        cierre.publicar_padron(delegado_de(usuarios, exp), ej)
    with pytest.raises(PermissionDenied):
        cierre.publicar_padron(usuarios["dir_dpf"], ej)
    with reloj.en("2026-11-24 09:15"):
        publicacion = cierre.publicar_padron(usuarios["dir_drff"], ej)
    assert "CC 8.1.5 (línea 4600)" == publicacion.fundamento and publicacion.acuse.folio
    with pytest.raises(ValidationError, match="ya está publicado"):
        cierre.publicar_padron(usuarios["dir_drff"], ej)
    html = client.get(url).content.decode()                                          # sin iniciar sesión
    assert exp.folio in html and persona.nombre in html and "Vigente" in html and "24/11/2026" in html
    for privado in ("LAPB800101MMCRNT05", "LAPB800101AB1", "722 555 0100"):
        assert privado not in html
    assert "8.1.5" in html and "sprint" not in html.lower()
    assert "Padrón de personas beneficiarias" in client.get(reverse("padron:indice")).content.decode()
    texto = client.get(reverse("padron:csv", args=[ej.programa.clave, ej.anio])).content.decode("utf-8-sig")
    assert texto.splitlines()[0] == "Folio,Persona beneficiaria,Municipio,Predio,Modalidad,Monto del apoyo,Situación,Alta"
    assert exp.folio in texto and "LAPB800101" not in texto
    # La baja por cancelación se refleja sola, sin volver a publicar.
    _cancelar(usuarios, exp2)
    html = client.get(url).content.decode()
    assert exp2.folio in html and 'data-situacion="cancelada"' in html and "Baja por cancelación del apoyo" in html
    assert 'data-situacion="vigente"' in html


def test_hu_6_3_padron_del_peg_con_altas_bajas_y_sustituciones_sin_el_nombre_del_guardabosque(peg_contratado, usuarios, client):
    exp = peg_contratado()
    ej = exp.ejercicio
    assert exp.beneficiaria.nombre != exp.solicitante.nombre
    cierre.publicar_padron(usuarios["dir_dpf"], ej)
    url = reverse("padron:programa", args=[ej.programa.clave, ej.anio])
    html = client.get(url).content.decode()
    assert exp.solicitante.nombre in html and exp.beneficiaria.nombre not in html and "numeral 14" in html
    assert 'data-tipo="Alta"' in html and "9.4.3 a" in html
    Evento.registrar(exp, usuarios["dir_dpf"], "sustitucion_beneficiaria", "Persona beneficiaria sustituida.",
                     datos={"anterior": 1, "nueva": 2})
    _desistir(usuarios, exp)
    p = reasignacion.proponer(usuarios["dir_dpf"], exp, "desistimiento")
    _acordar_y_cumplir(usuarios, p)
    html = client.get(url).content.decode()
    assert 'data-tipo="Sustitución"' in html and 'data-tipo="Baja"' in html and 'data-situacion="baja"' in html
    assert exp.beneficiaria.nombre not in html
    assert "Núcleo agrario" in html and "Persona beneficiaria</th>" not in html


# ----------------------------------------------------------------------------- criterio 3
def test_hu_6_3_el_informe_anual_queda_con_la_fecha_y_la_hora_del_envio_y_de_su_recepcion(pagada, usuarios, client, contrasena):
    exp = _concluida(pagada, usuarios)
    ej = exp.ejercicio
    with pytest.raises(PermissionDenied):
        cierre.enviar_informe(usuarios["dir_dpf"], ej)
    with reloj.en("2026-12-15 09:30"):
        cierre.cerrar_expediente(usuarios["dir_drff"], exp)
        informe = cierre.enviar_informe(usuarios["dir_drff"], ej)
    local = timezone.localtime(informe.enviado_en)
    assert local.strftime("%d/%m/%Y %H:%M") == "15/12/2026 09:30" and informe.enviado_por == usuarios["dir_drff"]
    assert informe.archivo.read(4) == b"%PDF" and informe.huella
    renglones = dict(informe.acuse.contenido["renglones"])
    assert renglones["Fecha y hora del envío"].startswith("15/12/2026 09:30") and "Comité" in renglones["Destinatario"]
    assert informe.resumen["cerrados"] == 1 and informe.resumen["diferencias"] == []
    with pytest.raises(ValidationError, match="ya se envió"):
        cierre.enviar_informe(usuarios["dir_drff"], ej)
    # La Secretaría Técnica lo ve por recibir y registra su recepción en la sesión del Comité.
    client.login(username="comite", password=contrasena)
    assert 'data-prueba="panel-informes-por-recibir"' in client.get(reverse("nucleo:bandeja")).content.decode()
    with pytest.raises(PermissionDenied):
        cierre.registrar_recepcion(usuarios["dir_drff"], informe)
    sesion = _sesion(usuarios, ej)
    with reloj.en("2026-12-16 11:00"):
        cierre.registrar_recepcion(usuarios["comite"], informe, sesion, "Se presentará en la siguiente sesión.")
    informe.refresh_from_db()
    assert timezone.localtime(informe.recibido_en).strftime("%d/%m/%Y %H:%M") == "16/12/2026 11:00" and informe.sesion == sesion
    assert DocumentoSesion.objects.filter(sesion=sesion, nombre__startswith="Informe anual").exists() and informe.acuse_recepcion.folio
    with pytest.raises(ValidationError, match="ya está registrada"):
        cierre.registrar_recepcion(usuarios["comite"], informe, sesion)
    # El cierre del ejercicio: expedientes cerrados, padrón, informe y recepción.
    assert not cierre.estado_cierre(ej)["cerrado"]
    cierre.publicar_padron(usuarios["dir_drff"], ej)
    estado = cierre.estado_cierre(ej)
    assert estado["cerrado"] and all(p[2] for p in estado["pasos"])
    html = client.get(reverse("seguimiento:cierre_detalle", args=[ej.pk])).content.decode()
    assert "15/12/2026 a las 09:30 h" in html and "16/12/2026 a las 11:00 h" in html and "Ejercicio cerrado" in html


def test_hu_6_3_el_informe_lleva_las_diferencias_que_haya(pagada, usuarios):
    a, _ = pagada("CC", cuantas=2)
    SolicitudPago.objects.filter(expediente=a, ministracion=1).update(importe=Decimal("99999.00"))
    informe = cierre.enviar_informe(usuarios["dir_drff"], a.ejercicio)
    assert informe.resumen["con_diferencias"] == 1 and {d["folio"] for d in informe.resumen["diferencias"]} == {a.folio}
    assert {d["nombre"] for d in informe.resumen["diferencias"]} >= {"Pagado mayor que lo aprobado"}


# ----------------------------------------------------------------------------- pantallas
def test_hu_6_3_pantallas_del_area_la_secretaria_y_la_delegacion(pagada, usuarios, client, contrasena):
    exp = _concluida(pagada, usuarios)
    ej = exp.ejercicio
    menu = [m for m in extensiones.MENU if m["url"] == "seguimiento:cierre"]
    assert menu and menu[0]["grupo"] == "Seguimiento y cierre" and "admin_finanzas" in [str(t) for t in menu[0]["tipos"]]
    client.login(username="dir_drff", password=contrasena)
    pagina = client.get(reverse("seguimiento:cierre")).content.decode()
    assert 'data-prueba="ejercicios-cierre"' in pagina and ej.programa.nombre in pagina and "sprint" not in pagina.lower()
    html = client.get(reverse("seguimiento:cierre_detalle", args=[ej.pk])).content.decode()
    assert 'data-prueba="resultados-finales"' in html and exp.folio in html and 'data-prueba="cerrar-listos"' in html
    assert 'data-prueba="publicar-padron"' in html and 'data-prueba="enviar-informe"' in html and "HU-6" not in html
    csv = client.get(reverse("seguimiento:resultados_csv", args=[ej.pk]))
    assert csv["Content-Type"].startswith("text/csv") and exp.folio in csv.content.decode("utf-8-sig")
    # pestaña del expediente: sus resultados y el botón de cierre
    tab = client.get(reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=seguimiento").content.decode()
    assert 'data-prueba="resultados-expediente"' in tab and 'data-prueba="cerrar-expediente"' in tab
    r = client.post(reverse("seguimiento:cerrar_expediente", args=[exp.folio]))
    assert r.status_code == 302
    exp.refresh_from_db()
    assert exp.estado.clave == "ejercicio_cerrado" and CierreExpediente.objects.filter(expediente=exp).exists()
    tab = client.get(reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=seguimiento").content.decode()
    assert 'data-prueba="expediente-cerrado"' in tab and 'data-prueba="cerrar-expediente"' not in tab
    # otra Dirección y la Delegación no entran
    client.logout()
    client.login(username="dir_dpf", password=contrasena)
    assert client.get(reverse("seguimiento:cierre_detalle", args=[ej.pk])).status_code == 403
    client.logout()
    client.login(username=delegado_de(usuarios, exp).username, password=contrasena)
    assert client.get(reverse("seguimiento:cierre")).status_code == 403
    assert direccion_de(usuarios, ej) == usuarios["dir_drff"]


def test_hu_6_3_ya_no_queda_nada_por_construir_en_la_pestana(pagada, usuarios, client, contrasena):
    exp = pagada("CC")
    client.login(username="dir_drff", password=contrasena)
    html = client.get(reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=seguimiento").content.decode()
    assert 'data-prueba="por-construir"' not in html and 'data-prueba="resultados-expediente"' in html
    assert [h[0] for h in registro.historias_pendientes()] == []
