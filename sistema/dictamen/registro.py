"""Registro del módulo M2 en los puntos de extensión del núcleo (bandejas, pestaña, menú, plazos)."""
from nucleo import extensiones
from nucleo.models import TipoUnidad


def filtro_bandeja(usuario, qs):
    """En «en dictamen» cada unidad ve solo lo que le falta dictaminar."""
    tipo = usuario.tipo_unidad
    if tipo == TipoUnidad.DIRECCION:
        return qs.exclude(estado__clave="validada", dictamen_tecnico__isnull=False)
    if tipo == TipoUnidad.JURIDICA:
        return qs.exclude(estado__clave="validada", dictamen_juridico__isnull=False)
    return qs


def panel_acuerdos(request):
    from .seguimiento import acuerdos_pendientes

    unidad = getattr(request.user, "unidad", None)
    if unidad is None:
        return None
    pendientes = list(acuerdos_pendientes(unidad))
    if not pendientes:
        return None
    return {"plantilla": "dictamen/seguimiento/_panel_pendientes.html", "contexto": {"acuerdos": pendientes}}


def contexto_pestana(request, exp):
    from .vistas.comun import contexto_dictamenes

    return contexto_dictamenes(request, exp)


def revisar_plazos(hoy):
    from .tecnico import revisar_plazos_dictamen

    return revisar_plazos_dictamen(hoy)


def registrar():
    if filtro_bandeja in extensiones.FILTROS_BANDEJA:
        return
    extensiones.FILTROS_BANDEJA.append(filtro_bandeja)
    extensiones.PANELES_BANDEJA.append(panel_acuerdos)
    extensiones.PESTANAS_EXPEDIENTE.append({"clave": "dictamenes", "nombre": "Dictámenes",
                                            "plantilla": "dictamen/pestana_dictamenes.html", "contexto": contexto_pestana})
    T = TipoUnidad
    extensiones.MENU.extend([
        {"nombre": "Listado preliminar", "url": "dictamen:listado", "tipos": [T.DIRECCION, T.JURIDICA, T.SECRETARIA_COMITE]},
        {"nombre": "Sesiones del Comité", "url": "dictamen:sesiones", "tipos": [T.SECRETARIA_COMITE, T.DIRECCION, T.JURIDICA]},
        {"nombre": "Incumplidas", "url": "dictamen:incumplidas", "tipos": [T.JURIDICA, T.DIRECCION, T.SECRETARIA_COMITE]},
    ])
    extensiones.REVISIONES_PLAZO.append(revisar_plazos)
    extensiones.DEMOS.append(cargar_demo)


def cargar_demo():
    from .demo import cargar_demo as cargar

    return cargar()
