"""Recorrido completo del prototipo del sprint 1 con una sola solicitud.

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
from nucleo.demo import completar_requisitos, cuadro_en_municipio
from nucleo.models import Municipio, TransicionNoPermitida, bandeja
from recepcion import servicios as recepcion
from recepcion.models import EstadoRevision

from .fixtures_m2 import despues_de, documento_sesion, fecha_sesion

pytestmark = pytest.mark.django_db

UNIDADES = ("del_amecameca", "del_toluca", "dir_drff", "juridica", "comite")


def en_bandeja_de(exp, usuarios):
    """Usuarios de demostración que tienen el expediente en su bandeja."""
    return {u for u in UNIDADES if exp in bandeja(usuarios[u])}


def test_sprint_1_una_solicitud_recorre_recepcion_validacion_dictamenes_y_aprobacion(cc, usuarios, pdf):
    deleg, direccion = usuarios["del_amecameca"], usuarios["dir_drff"]
    jur, comite = usuarios["juridica"], usuarios["comite"]

    # --- M1.1 Registro en la Delegación (HU-1.1) ------------------------------------------------
    datos = recepcion.DatosSolicitud(
        ejercicio=cc, municipio=Municipio.objects.get(nombre="Amecameca"), nombre_predio="Predio del recorrido",
        tipo_persona=cc.tipos_persona.get(clave="fisica"), modalidad=cc.modalidades.get(clave="reforestacion"),
        solicitante_nombre="Persona del Recorrido", solicitante_tipo="fisica", es_refrendo=False,
        superficie_solicitada_ha=Decimal("6"),
    )
    exp = recepcion.registrar_solicitud(deleg, datos)
    assert exp.estado.clave == "recibida" and exp.fecha_recepcion
    assert exp.acuses.count() == 1                                   # acuse de recepción
    assert en_bandeja_de(exp, usuarios) == {"del_amecameca"}        # otra Delegación no lo ve

    # --- M1.2 Requisitos (HU-1.2): no se puede enviar con un faltante -----------------------------
    completar_requisitos(deleg, exp, faltar=("CC-REQ-13",))
    assert recepcion.problemas_para_enviar(exp)
    with pytest.raises(Exception):
        recepcion.enviar_a_direccion(deleg, exp)
    plano = exp.revisiones.get(requisito__clave="CC-REQ-13")
    recepcion.revisar_requisito(deleg, plano, EstadoRevision.ENTREGADO, archivo=pdf("plano.pdf"))
    assert not recepcion.problemas_para_enviar(exp)

    # --- M1.3 Polígono levantado en campo (HU-1.3) ----------------------------------------------
    pol = recepcion.registrar_poligono(deleg, exp, cuadro_en_municipio(exp.predio.municipio, 6), "dibujo",
                                       "delegacion", "Brigada de la Delegación", timezone.localdate())
    assert pol.vigente and 5.9 < float(pol.superficie_ha) < 6.1

    # --- Envío a la Dirección: relevo Delegación -> Dirección -------------------------------------
    with pytest.raises((PermissionDenied, TransicionNoPermitida)):
        recepcion.enviar_a_direccion(direccion, exp)                # solo la Delegación envía
    recepcion.enviar_a_direccion(deleg, exp)
    exp.refresh_from_db()
    assert exp.estado.clave == "enviada_direccion"
    assert en_bandeja_de(exp, usuarios) == {"dir_drff"}

    # --- M1.4 Flujo alterno A: aviso de faltantes, notificación y reenvío (HU-1.4) ----------------
    plano.refresh_from_db()
    aviso = recepcion.validar_expediente(direccion, exp, [plano.pk], "El plano no trae coordenadas")
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
    tecnico.dictaminar(direccion, exp, "factible", "Reforestación con densidad suficiente")
    exp.refresh_from_db()
    assert exp.estado.clave == "validada"                           # falta el jurídico
    assert en_bandeja_de(exp, usuarios) == {"juridica"}            # la Dirección ya dictaminó
    juridico.dictaminar(jur, exp, "procedente", "Documentación legal vigente")
    exp.refresh_from_db()
    assert exp.estado.clave == "dictaminada"
    assert en_bandeja_de(exp, usuarios) == {"comite"}              # relevo a la Secretaría Técnica

    # --- M2.3 Sesión de aprobación ---------------------------------------------------------------
    sesion = sesiones.crear_sesion(comite, cc, TipoSesion.APROBACION, fecha_sesion(6), "Sala de juntas",
                                   "Quórum\nListado preliminar\nAprobación de listados\nAutorización de publicación")
    sesiones.agregar_documento(comite, sesion, documento_sesion("listado.pdf"), "Listado preliminar")
    sesiones.enviar_convocatoria(comite, sesion)
    aprobacion.proponer_listados(comite, sesion, Decimal("500000"))
    resolucion = sesion.resoluciones.get(expediente=exp)
    assert resolucion.resultado == ResultadoListado.BENEFICIARIA
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
    acuerdo = seguimiento.registrar_acuerdo(comite, seg, "caso_fortuito", "Atender el aviso de siniestro", [exp])
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
