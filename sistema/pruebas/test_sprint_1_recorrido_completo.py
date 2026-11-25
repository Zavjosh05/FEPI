"""Recorrido completo del prototipo del sprint 1 con una sola solicitud, en cada programa con reglas (CC, PS,
RHF y PSAHEM).

«Una solicitud de prueba recorre la recepción, la validación, los dictámenes y la sesión de aprobación.»
Cada paso lo hace la unidad que le toca y se comprueba el relevo: el expediente sale de una bandeja y
entra en la siguiente, con su estado, su acuse y su renglón en la bitácora. Incluye el flujo alterno A
(aviso de faltantes y reenvío) y un acuerdo de una sesión de seguimiento.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from dictamen import aprobacion, juridico, seguimiento, sesiones, tecnico
from dictamen.models import ResultadoListado, TipoSesion
from nucleo import montos
from nucleo.demo import completar_requisitos, cuadro_en_municipio
from nucleo.models import Ejercicio, Municipio, TransicionNoPermitida, bandeja
from recepcion import servicios as recepcion
from recepcion.models import EstadoRevision

from .fixtures_m2 import despues_de, documento_sesion, fecha_sesion, propiedad_en_regla

pytestmark = pytest.mark.django_db

UNIDADES = ("del_amecameca", "del_toluca", "dir_drff", "juridica", "comite")


def en_bandeja_de(exp, usuarios):
    """Usuarios de demostración que tienen el expediente en su bandeja."""
    return {u for u in UNIDADES if exp in bandeja(usuarios[u])}


# programa: (modalidad, tipo de persona, superficie en ha, tipo de acuerdo de seguimiento)
PROGRAMAS = {
    "CC": ("reforestacion", "fisica", "6", "caso_fortuito"),
    "PS": ("plantacion_forestal_comercial", "fisica", "3", "caso_fortuito"),
    "RHF": ("rfi_modalidad_dos", "fisica", "2", "caso_fortuito"),
    "PSA": ("cuenca_alta", "fisica", "25", "caso_fortuito"),
}


def requisito_para_faltar(exp):
    """Primer requisito que se entrega con documento (el que la Dirección marcará como faltante)."""
    return next(r for r in exp.revisiones.select_related("requisito").order_by("requisito__orden")
                if r.requisito.requiere_documento and not r.requisito.es_condicional)


@pytest.mark.parametrize("programa", list(PROGRAMAS))
def test_sprint_1_una_solicitud_recorre_recepcion_validacion_dictamenes_y_aprobacion(programa, usuarios, pdf):
    deleg, direccion = usuarios["del_amecameca"], usuarios["dir_drff"]
    jur, comite = usuarios["juridica"], usuarios["comite"]
    cc = Ejercicio.objects.get(programa__clave=programa, anio=2026)
    modalidad, tipo, superficie, tipo_acuerdo = PROGRAMAS[programa]

    # --- M1.1 Registro en la Delegación (HU-1.1) ------------------------------------------------
    datos = recepcion.DatosSolicitud(
        ejercicio=cc, municipio=Municipio.objects.get(nombre="Amecameca"), nombre_predio="Predio del recorrido",
        tipo_persona=cc.tipos_persona.get(clave=tipo), modalidad=cc.modalidades.get(clave=modalidad, seleccionable=True),
        solicitante_nombre="Persona del Recorrido", solicitante_tipo="fisica", es_refrendo=False,
        superficie_solicitada_ha=Decimal(superficie),
    )
    exp = recepcion.registrar_solicitud(deleg, datos)
    assert exp.estado.clave == "recibida" and exp.fecha_recepcion
    assert exp.acuses.count() == 1                                   # acuse de recepción
    assert en_bandeja_de(exp, usuarios) == {"del_amecameca"}        # otra Delegación no lo ve

    # --- M1.2 Requisitos (HU-1.2): no se puede enviar con un faltante -----------------------------
    plano = requisito_para_faltar(exp)
    completar_requisitos(deleg, exp, faltar=(plano.requisito.clave,))
    assert recepcion.problemas_para_enviar(exp)
    with pytest.raises(Exception):
        recepcion.enviar_a_direccion(deleg, exp)
    plano.refresh_from_db()
    recepcion.revisar_requisito(deleg, plano, EstadoRevision.ENTREGADO, archivo=pdf("plano.pdf"))
    assert not recepcion.problemas_para_enviar(exp)

    # --- M1.3 Polígono levantado en campo (HU-1.3) ----------------------------------------------
    pol = recepcion.registrar_poligono(deleg, exp, cuadro_en_municipio(exp.predio.municipio, float(superficie)), "dibujo",
                                       "delegacion", "Brigada de la Delegación", timezone.localdate())
    assert pol.vigente and abs(float(pol.superficie_ha) - float(superficie)) < 0.1

    # --- Envío a la Dirección: relevo Delegación -> Dirección -------------------------------------
    with pytest.raises((PermissionDenied, TransicionNoPermitida)):
        recepcion.enviar_a_direccion(direccion, exp)                # solo la Delegación envía
    recepcion.enviar_a_direccion(deleg, exp)
    exp.refresh_from_db()
    assert exp.estado.clave == "enviada_direccion"
    assert en_bandeja_de(exp, usuarios) == {"dir_drff"}

    # --- M1.4 Flujo alterno A: aviso de faltantes, notificación y reenvío (HU-1.4) ----------------
    plano.refresh_from_db()
    aviso = recepcion.validar_expediente(direccion, exp, [plano.pk], "Un faltante",
                                         observaciones_requisitos={plano.pk: "El plano no trae coordenadas"})
    assert aviso.observaciones_requisitos.get(revision=plano).observacion == "El plano no trae coordenadas"
    exp.refresh_from_db()
    assert exp.estado.clave == "faltantes" and aviso.fecha_limite
    assert en_bandeja_de(exp, usuarios) == {"del_amecameca"}        # regresa a la Delegación
    recepcion.registrar_notificacion(deleg, aviso)                  # por conducto de la Delegación
    plano.refresh_from_db()
    recepcion.revisar_requisito(deleg, plano, EstadoRevision.ENTREGADO, archivo=pdf("plano_corregido.pdf"))
    recepcion.enviar_a_direccion(deleg, exp)
    recepcion.validar_expediente(direccion, exp)
    exp.refresh_from_db()
    assert exp.estado.clave == "validada"

    # --- M2.1 y M2.2 Dictámenes en paralelo: Dirección y Unidad Jurídica --------------------------
    assert en_bandeja_de(exp, usuarios) == {"dir_drff", "juridica"}
    with pytest.raises((PermissionDenied, TransicionNoPermitida)):
        exp.cambiar_estado("no_factible", direccion, "Sin pasar por el Comité")
    dt = tecnico.dictaminar(direccion, exp, "factible", "Reforestación con densidad suficiente")
    assert dt.documento.expediente == exp and dt.folio.startswith("DT-")       # documento del dictamen adjunto
    exp.refresh_from_db()
    assert exp.estado.clave == "validada"                           # falta el jurídico
    assert exp.dictamen_tecnico.analisis["superficie_en_rango"] is True    # rango de su modalidad o cuenca
    assert exp.dictamen_tecnico.fecha_limite                        # plazo de dictaminación de sus reglas
    assert en_bandeja_de(exp, usuarios) == {"juridica"}            # la Dirección ya dictaminó
    dj = juridico.dictaminar(jur, exp, "procedente", "Documentación legal vigente", propiedad=propiedad_en_regla(exp))
    assert dj.propiedad.acreditada and dj.documento.expediente == exp and dj.folio.startswith("DJ-")
    exp.refresh_from_db()
    assert exp.estado.clave == "dictaminada"
    assert en_bandeja_de(exp, usuarios) == {"comite"}              # relevo a la Secretaría Técnica

    # --- M2.3 Sesión de aprobación ---------------------------------------------------------------
    sesion = sesiones.crear_sesion(comite, cc, TipoSesion.APROBACION, fecha_sesion(6), "Sala de juntas",
                                   "Quórum\nListado preliminar\nAprobación de listados\nAutorización de publicación")
    assert sesion.integrantes["nombre"].startswith("Comité") and (programa != "PSA" or "FIPASAHEM" in sesion.integrantes["nombre"])
    sesiones.agregar_documento(comite, sesion, documento_sesion("listado.pdf"), "Listado preliminar")
    sesiones.enviar_convocatoria(comite, sesion)
    aprobacion.proponer_listados(comite, sesion, Decimal("500000"))
    resolucion = sesion.resoluciones.get(expediente=exp)
    assert resolucion.resultado == ResultadoListado.BENEFICIARIA
    calculado = montos.monto_aprobado(exp)
    assert resolucion.monto == calculado.total > 0 and calculado.ministraciones  # monto de su modalidad
    acta = aprobacion.registrar_acta(comite, sesion, True, "Aprobado por unanimidad", momento=despues_de(sesion))
    exp.refresh_from_db()
    sesion.refresh_from_db()
    assert exp.estado.clave == "aprobada" and sesion.autoriza_publicacion and acta.archivo
    assert en_bandeja_de(exp, usuarios) == {"dir_drff"}            # el área responsable publica (M3)

    # --- M2.4 Sesión de seguimiento: el acuerdo llega al área que debe cumplirlo -------------------
    seg = sesiones.crear_sesion(comite, cc, TipoSesion.SEGUIMIENTO, fecha_sesion(8), "Sala de juntas",
                                "Quórum\nCasos de seguimiento")
    sesiones.agregar_documento(comite, seg, documento_sesion("casos.pdf"), "Casos")
    sesiones.enviar_convocatoria(comite, seg)
    acuerdo = seguimiento.registrar_acuerdo(comite, seg, tipo_acuerdo, "Atender el aviso de siniestro", [exp],
                                            causa="Aviso de siniestro de la Delegación")
    assert acuerdo in seguimiento.acuerdos_pendientes(acuerdo.unidad_responsable)
    responsable = next(u for u in usuarios.values() if u.unidad_id == acuerdo.unidad_responsable_id)
    seguimiento.cumplir(responsable, acuerdo, "Atendido")
    assert acuerdo not in seguimiento.acuerdos_pendientes(acuerdo.unidad_responsable)

    # --- Rastro completo: cada relevo dejó su renglón en la bitácora y los envíos, su acuse --------
    estados = [e.estado_destino.clave for e in exp.eventos.order_by("fecha_hora", "pk") if e.estado_destino_id]
    assert estados == ["recibida", "enviada_direccion", "faltantes", "enviada_direccion", "validada",
                       "dictaminada", "aprobada"] or estados[1:] == [
                       "enviada_direccion", "faltantes", "enviada_direccion", "validada", "dictaminada", "aprobada"]
    assert all(e.usuario_id and e.fecha_hora for e in exp.eventos.all())
    assert exp.acuses.count() >= 5 and all(a.archivo for a in exp.acuses.all())
    assert exp.documentos.filter(tipo="dictamen").count() == 2

    # --- Trazabilidad: cada unidad dejó su registro en el historial de la base de datos -----------
    from nucleo.trazabilidad import historial_expediente
    quienes = {f["usuario"].username for f in historial_expediente(exp) if f["usuario"]}
    assert {"del_amecameca", "dir_drff", "juridica", "comite"} <= quienes


@pytest.mark.parametrize("programa,modalidad", [("CC", "refrendo"), ("CC", "pago_unico_hasta_5_ha"),
                                                ("PSA", "fondos_concurrentes"), ("PSA", "refrendo")])
def test_sprint_1_modalidades_no_seleccionables_se_rechazan_al_registrar(programa, modalidad, usuarios):
    from django.core.exceptions import ValidationError

    ej = Ejercicio.objects.get(programa__clave=programa, anio=2026)
    datos = recepcion.DatosSolicitud(
        ejercicio=ej, municipio=Municipio.objects.get(nombre="Amecameca"), nombre_predio="Predio X",
        tipo_persona=ej.tipos_persona.get(clave="fisica"), modalidad=ej.modalidades.get(clave=modalidad),
        solicitante_nombre="Persona X", solicitante_tipo="fisica")
    with pytest.raises(ValidationError):
        recepcion.registrar_solicitud(usuarios["del_amecameca"], datos)
