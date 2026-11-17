"""HU-2.3 · Sesión de aprobación: listados propuestos, ajuste del Comité con constancia, acta y autorización
de publicación. La convocatoria está en sesiones.py (común con las sesiones de seguimiento)."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from nucleo import montos, plazos
from nucleo.acuses import emitir_acuse
from nucleo.models import Evento, Expediente, TipoUnidad
from nucleo.templatetags.moneda import formato_moneda

from .comun import datos_dictamen, exigir_unidad, resultado_combinado
from .models import EstadoSesion, ResolucionSesion, ResultadoListado, TipoSesion

DESTINO = {ResultadoListado.BENEFICIARIA: "aprobada", ResultadoListado.LISTA_ESPERA: "lista_espera",
           ResultadoListado.NO_FACTIBLE: "no_factible"}


def criterios_priorizacion(expediente):
    """Criterios de priorización (datos/dictamen.json) que cumple el expediente."""
    cumplidos = []
    for c in datos_dictamen().get("priorizacion", {}).get(expediente.programa.clave, []):
        valor = getattr(expediente, c["campo"], None)
        valor = getattr(valor, "clave", valor)
        if valor in c["valores"]:
            cumplidos.append(c["criterio"])
    return cumplidos


def clave_orden(expediente):
    criterios = datos_dictamen().get("priorizacion", {}).get(expediente.programa.clave, [])
    cumplidos = set(criterios_priorizacion(expediente))
    return tuple(0 if c["criterio"] in cumplidos else 1 for c in criterios) + (expediente.fecha_recepcion, expediente.pk)


def monto_por_hectarea(ejercicio):
    """Solo para mostrar el monto de referencia en pantalla; el monto de cada solicitud lo calcula
    ``nucleo.montos.monto_aprobado`` según su modalidad."""
    return montos.monto_por_hectarea_referencia(ejercicio)


def candidatas(sesion):
    return (Expediente.objects.filter(ejercicio=sesion.ejercicio, estado__clave="dictaminada")
            .select_related("predio__municipio", "solicitante", "modalidad", "dictamen_tecnico", "dictamen_juridico"))


def proponer_listados(usuario, sesion, presupuesto=None):
    """Arma la propuesta: factibles en orden de priorización hasta donde alcance el recurso (beneficiarias),
    el resto en lista de espera con su orden, y las no factibles (CC 8.1.2 último párrafo; 9.4.3 fr. I)."""
    exigir_unidad(usuario, TipoUnidad.SECRETARIA_COMITE)
    if sesion.tipo != TipoSesion.APROBACION:
        raise ValidationError("Los listados se aprueban en una sesión de aprobación.")
    if sesion.estado == EstadoSesion.CELEBRADA:
        raise ValidationError("La sesión ya tiene acta.")
    if presupuesto is not None:
        sesion.presupuesto = presupuesto
        sesion.save(update_fields=["presupuesto"])
    factibles, no_factibles = [], []
    for exp in candidatas(sesion):
        (factibles if resultado_combinado(exp)[0] == "factible" else no_factibles).append(exp)
    factibles.sort(key=clave_orden)
    with transaction.atomic():
        sesion.resoluciones.all().delete()
        disponible = sesion.presupuesto
        orden = {ResultadoListado.BENEFICIARIA: 0, ResultadoListado.LISTA_ESPERA: 0}
        for exp in factibles:
            superficie = exp.dictamen_tecnico.superficie_factible_ha or exp.superficie_solicitada_ha or Decimal("0")
            monto = montos.monto_aprobado(exp, superficie).total
            if disponible is None or (monto is not None and monto <= disponible):
                resultado = ResultadoListado.BENEFICIARIA
                if disponible is not None:
                    disponible -= monto
            else:
                resultado = ResultadoListado.LISTA_ESPERA
            orden[resultado] += 1
            ResolucionSesion.objects.create(
                sesion=sesion, expediente=exp, resultado=resultado, resultado_propuesto=resultado,
                orden=orden[resultado], orden_propuesto=orden[resultado], monto=monto, criterios=criterios_priorizacion(exp),
            )
        for exp in no_factibles:
            ResolucionSesion.objects.create(sesion=sesion, expediente=exp, resultado=ResultadoListado.NO_FACTIBLE,
                                            resultado_propuesto=ResultadoListado.NO_FACTIBLE)
    return sesion.resoluciones.all()


def _renumerar(sesion, resultado):
    for i, r in enumerate(sesion.resoluciones.filter(resultado=resultado).order_by("orden", "pk"), 1):
        if r.orden != i:
            ResolucionSesion.objects.filter(pk=r.pk).update(orden=i)


def ajustar(usuario, resolucion, resultado, orden, motivo):
    """El Comité cambia el listado o el orden propuesto; queda la constancia (motivo e historial)."""
    exigir_unidad(usuario, TipoUnidad.SECRETARIA_COMITE)
    sesion = resolucion.sesion
    if sesion.estado == EstadoSesion.CELEBRADA:
        raise ValidationError("La sesión ya tiene acta; los listados no cambian.")
    if not (motivo or "").strip():
        raise ValidationError("Anote el motivo del ajuste del Comité.")
    if resultado not in ResultadoListado.values:
        raise ValidationError("Listado no reconocido.")
    if resolucion.resultado_propuesto == ResultadoListado.NO_FACTIBLE and resultado != ResultadoListado.NO_FACTIBLE:
        raise ValidationError("Una solicitud no factible o no procedente en sus dictámenes no pasa a los listados de apoyo.")
    with transaction.atomic():
        anterior = resolucion.resultado
        resolucion.resultado = resultado
        if resultado == ResultadoListado.NO_FACTIBLE:
            resolucion.orden = None
        else:
            # Se inserta en la posición pedida y se recorre el resto del listado.
            otros = list(sesion.resoluciones.filter(resultado=resultado).exclude(pk=resolucion.pk).order_by("orden", "pk"))
            posicion = max(1, min(int(orden or len(otros) + 1), len(otros) + 1))
            otros.insert(posicion - 1, resolucion)
            for i, r in enumerate(otros, 1):
                if r.pk != resolucion.pk and r.orden != i:
                    ResolucionSesion.objects.filter(pk=r.pk).update(orden=i)
            resolucion.orden = posicion
        resolucion.motivo_ajuste = motivo.strip()
        resolucion._change_reason = f"Ajuste del Comité: {motivo.strip()}"
        resolucion.save()
        if anterior != resultado:
            _renumerar(sesion, anterior)
        Evento.registrar(resolucion.expediente, usuario, "ajuste_comite",
                         f"Sesión {sesion.numero}: el Comité ajustó la propuesta a «{resolucion.get_resultado_display()}»"
                         + (f", lugar {resolucion.orden}" if resolucion.orden else "") + f". Motivo: {motivo.strip()}")
    return resolucion


def registrar_acta(usuario, sesion, autoriza_publicacion, observaciones="", momento=None):
    """Acta con los listados aprobados y la autorización de publicación; mueve cada expediente a su estado.

    No se registra antes de la fecha y hora de la sesión. `momento` (solo servicios, pruebas y demostración)
    es el instante contra el que se compara; por omisión, ahora."""
    exigir_unidad(usuario, TipoUnidad.SECRETARIA_COMITE)
    if sesion.tipo != TipoSesion.APROBACION:
        raise ValidationError("El acta con listados es de una sesión de aprobación.")
    if not sesion.convocatoria_enviada:
        raise ValidationError("Primero se envía la convocatoria.")
    if sesion.estado == EstadoSesion.CELEBRADA:
        raise ValidationError("La sesión ya tiene acta.")
    ahora = momento or timezone.now()
    if ahora < sesion.fecha_hora:
        raise ValidationError(f"El acta no se registra antes de la sesión: está convocada para el "
                              f"{timezone.localtime(sesion.fecha_hora):%d/%m/%Y a las %H:%M} h.")
    resoluciones = list(sesion.resoluciones.select_related("expediente__predio", "expediente__solicitante"))
    if not resoluciones:
        raise ValidationError("No hay listados que aprobar: genere la propuesta.")
    with transaction.atomic():
        detalle = []
        for resultado in (ResultadoListado.BENEFICIARIA, ResultadoListado.LISTA_ESPERA, ResultadoListado.NO_FACTIBLE):
            for r in sorted((x for x in resoluciones if x.resultado == resultado), key=lambda x: (x.orden or 0, x.pk)):
                texto = f"{r.expediente.folio} · {r.expediente.solicitante.nombre} · {r.expediente.predio.nombre}"
                if resultado == ResultadoListado.NO_FACTIBLE:
                    texto += f" — {resultado_combinado(r.expediente)[1]}"
                elif r.monto is not None:
                    texto += f" — {formato_moneda(r.monto)}"
                if r.motivo_ajuste:
                    texto += f" (ajuste del Comité: {r.motivo_ajuste})"
                detalle.append({"clave": r.get_resultado_display(), "texto": texto[:220],
                                "estado": str(r.orden) if r.orden else "—"})
        acuse = emitir_acuse(
            None, "acta_comite", f"Acta de la sesión de aprobación {sesion.numero}", usuario,
            [("Comité", (sesion.integrantes or {}).get("nombre", "")),
             ("Fecha y hora de la sesión", f"{timezone.localtime(sesion.fecha_hora):%d/%m/%Y %H:%M} h"),
             ("Registro del acta", f"{timezone.localtime(ahora):%d/%m/%Y %H:%M:%S} h"),
             ("Personas beneficiarias", str(sum(r.resultado == ResultadoListado.BENEFICIARIA for r in resoluciones))),
             ("Lista de espera", str(sum(r.resultado == ResultadoListado.LISTA_ESPERA for r in resoluciones))),
             ("No factibles", str(sum(r.resultado == ResultadoListado.NO_FACTIBLE for r in resoluciones))),
             ("Autorización de publicación",
              "Sí: en las Delegaciones Regionales Forestales y en la página de PROBOSQUE (9.4.3 fr. III)"
              if autoriza_publicacion else "No"),
             ("Observaciones", observaciones or "—")],
            destinatario="Integrantes del Comité", referencia=f"Sesión {sesion.numero}", detalle=detalle,
            encabezado_detalle=["Listado", "Solicitud", "Orden"],
        )
        sesion.acta_fecha = ahora
        sesion.autoriza_publicacion = bool(autoriza_publicacion)
        sesion.observaciones_acta = observaciones
        sesion.acuse_acta = acuse
        sesion.estado = EstadoSesion.CELEBRADA
        sesion.save()
        for r in resoluciones:
            r.expediente.cambiar_estado(
                DESTINO[r.resultado], usuario, tipo_evento="acta_comite", acuse=acuse,
                descripcion=f"Sesión {sesion.numero}: {r.get_resultado_display()}"
                + (f", lugar {r.orden}" if r.orden else ""),
                datos={"sesion": sesion.pk, "orden": r.orden},
            )
            if r.resultado == ResultadoListado.BENEFICIARIA:
                # Evento de arranque de plazos: en PEG la firma corre desde la aprobación del CASPEG (R-18).
                plazos.registrar_hito(r.expediente, "aprobacion_comite", usuario, ahora, referencia=sesion.numero,
                                      datos={"sesion": sesion.pk})
    return acuse
