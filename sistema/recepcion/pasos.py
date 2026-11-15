"""Siguiente paso de M1 (P-13): lo que le toca a la Delegación o a la Dirección en recepción y validación."""
from django.urls import reverse

from nucleo.models import TipoUnidad

from .models import EstadoRevision


def _url(exp, pestana):
    return reverse("recepcion:expediente", args=[exp.folio]) + f"?pestana={pestana}"


def siguiente_paso(usuario, exp):
    from . import servicios

    estado, tipo = exp.estado.clave, usuario.tipo_unidad
    if tipo == TipoUnidad.DELEGACION and usuario.unidad_id == exp.delegacion_id:
        if estado == "faltantes":
            aviso = servicios.aviso_vigente(exp)
            if aviso and not aviso.notificado_en:
                return {"texto": "Registrar la notificación del aviso de faltantes", "url": _url(exp, "validacion"),
                        "ayuda": "La Dirección avisó faltantes; notifique a la persona solicitante."}
        if estado in ("recibida", "faltantes"):
            pendientes = exp.revisiones.filter(estado__in=[EstadoRevision.PENDIENTE, EstadoRevision.FALTANTE]).exists()
            if pendientes:
                return {"texto": "Revisar requisitos", "url": _url(exp, "requisitos"),
                        "ayuda": "Hay requisitos sin revisar o faltantes."}
            if exp.programa.usa_poligono and estado == "recibida" and not servicios.poligono_vigente(exp):
                return {"texto": "Levantar polígono", "url": _url(exp, "ubicacion"),
                        "ayuda": "Puede enviar sin polígono (se levanta después), pero el dictamen técnico lo necesita."}
            if not servicios.problemas_para_enviar(exp):
                return {"texto": "Reenviar a la Dirección" if estado == "faltantes" else "Enviar a la Dirección",
                        "url": _url(exp, "requisitos"), "ayuda": "El expediente está completo."}
            return {"texto": "Revisar requisitos", "url": _url(exp, "requisitos")}
    if tipo == TipoUnidad.DIRECCION and estado == "enviada_direccion":
        return {"texto": "Validar expediente", "url": reverse("recepcion:validar", args=[exp.folio])}
    return None
