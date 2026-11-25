"""Vistas y utilidades comunes del módulo M2 (pestaña «Dictámenes» del expediente)."""
from django.http import Http404

from nucleo.models import TipoUnidad, expedientes_visibles

from ..comun import resultado_combinado


def mensajes_error(error):
    return error.messages if hasattr(error, "messages") else [str(error)]


def expediente_visible(request, folio):
    exp = expedientes_visibles(request.user).filter(folio=folio).first()
    if exp is None:
        raise Http404("No existe el expediente o no está entre los que atiende su unidad.")
    return exp


def contexto_dictamenes(request, exp):
    from ..juridico import cotejar
    from ..tecnico import TEXTO_SITUACION, situacion_plazo

    tipo = request.user.tipo_unidad
    tecnico = getattr(exp, "dictamen_tecnico", None)
    juridico = getattr(exp, "dictamen_juridico", None)
    plazo = situacion_plazo(exp)
    return {
        "tecnico": tecnico, "juridico": juridico,
        "resultado_combinado": resultado_combinado(exp),
        "plazo_dictamen": plazo, "texto_situacion": TEXTO_SITUACION.get(plazo["situacion"], ""),
        "cotejo": cotejar(exp) if tipo in (TipoUnidad.JURIDICA, TipoUnidad.DIRECCION) or request.user.is_superuser else None,
        "puede_dictaminar_tecnico": tipo == TipoUnidad.DIRECCION and exp.estado.clave == "validada" and tecnico is None,
        "puede_dictaminar_juridico": tipo == TipoUnidad.JURIDICA and exp.estado.clave == "validada" and juridico is None,
        "resoluciones": exp.resoluciones_comite.select_related("sesion"),
        "acuerdos": exp.acuerdos_comite.select_related("sesion", "unidad_responsable"),
        "movimientos": exp.movimientos_listado.select_related("acuerdo"),
    }
