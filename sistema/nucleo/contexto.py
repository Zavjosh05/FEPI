from django.conf import settings


def sistema(request):
    """Variables comunes de las plantillas."""
    usuario = getattr(request, "user", None)
    unidad = getattr(usuario, "unidad", None) if usuario and usuario.is_authenticated else None
    return {
        "unidad_actual": unidad,
        "MAPA_TESELAS_URL": settings.MAPA_TESELAS_URL,
    }
