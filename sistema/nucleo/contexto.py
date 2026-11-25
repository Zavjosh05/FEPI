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
                opcion = {"nombre": m["nombre"], "url": reverse(m["url"]), "nombre_url": m["url"].split(":")[-1]}
                grupo = m.get("grupo")
                if not grupo:
                    menu.append(opcion)
                    continue
                # Las opciones con el mismo «grupo» se muestran juntas en un menú desplegable.
                existente = next((x for x in menu if x.get("grupo") == grupo), None)
                if existente is None:
                    menu.append({"grupo": grupo, "opciones": [opcion], "nombres_url": [opcion["nombre_url"]]})
                else:
                    existente["opciones"].append(opcion)
                    existente["nombres_url"].append(opcion["nombre_url"])
    return {
        "menu_extra": menu,
        "unidad_actual": unidad,
        "MAPA_TESELAS_URL": settings.MAPA_TESELAS_URL,
    }
