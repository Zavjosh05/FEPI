from django.conf import settings


def sistema(request):
    """Variables comunes de las plantillas."""
    usuario = getattr(request, "user", None)
    unidad = getattr(usuario, "unidad", None) if usuario and usuario.is_authenticated else None
    from django.urls import reverse

    from .extensiones import MENU

    menu = []
    if unidad is not None or (usuario is not None and usuario.is_authenticated and usuario.is_superuser):
        tipo = getattr(unidad, "tipo", None)
        for m in MENU:
            if m.get("tipos") is None or tipo in m["tipos"] or (usuario.is_superuser and unidad is None):
                menu.append({"nombre": m["nombre"], "url": reverse(m["url"]), "nombre_url": m["url"].split(":")[-1]})
    return {
        "menu_extra": menu,
        "unidad_actual": unidad,
        "MAPA_TESELAS_URL": settings.MAPA_TESELAS_URL,
    }
