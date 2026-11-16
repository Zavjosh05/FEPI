from django.conf import settings


def armar_menu(usuario, unidad, url_activa=""):
    """Entradas de la barra superior para una persona: enlaces sueltos y grupos por módulo.

    Cada entrada es ``{"nombre", "url", "nombre_url", "activo"}`` o, si es un grupo con varios enlaces,
    ``{"nombre", "grupo": True, "activo", "hijos": [...]}``. Un grupo que a esta unidad le deja un solo enlace se
    muestra como enlace simple. Los grupos van en el orden de ``extensiones.GRUPOS_MENU``.
    """
    from django.urls import reverse

    from .extensiones import GRUPOS_MENU, MENU

    if unidad is None and not (usuario is not None and usuario.is_authenticated and usuario.is_superuser):
        return []
    tipo = getattr(unidad, "tipo", None)
    sueltos, grupos = [], {g: [] for g in GRUPOS_MENU}
    for m in MENU:
        if not (m.get("tipos") is None or tipo in m["tipos"] or (usuario.is_superuser and unidad is None and not m.get("estricto"))):
            continue
        nombre_url = m["url"].split(":")[-1]
        entrada = {"nombre": m["nombre"], "url": reverse(m["url"]), "nombre_url": nombre_url,
                   "activo": nombre_url == url_activa}
        if m.get("grupo") in grupos:
            grupos[m["grupo"]].append(entrada)
        else:
            sueltos.append(entrada)
    menu = []
    for nombre, hijos in grupos.items():
        if len(hijos) == 1:
            menu.append(hijos[0])
        elif hijos:
            menu.append({"nombre": nombre, "grupo": True, "hijos": hijos, "activo": any(h["activo"] for h in hijos)})
    return menu + sueltos


def sistema(request):
    """Variables comunes de las plantillas."""
    usuario = getattr(request, "user", None)
    unidad = getattr(usuario, "unidad", None) if usuario and usuario.is_authenticated else None
    url_activa = request.resolver_match.url_name if getattr(request, "resolver_match", None) else ""
    return {
        "menu_extra": armar_menu(usuario, unidad, url_activa),
        "unidad_actual": unidad,
        "MAPA_TESELAS_URL": settings.MAPA_TESELAS_URL,
    }
