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


def url_llevar_a_sesion(ejercicio):
    """La sesión de aprobación abierta del ejercicio o, si no hay, el alta de una nueva (P-16)."""
    from django.urls import reverse

    from .models import EstadoSesion, SesionComite, TipoSesion

    abierta = (SesionComite.objects.filter(ejercicio=ejercicio, tipo=TipoSesion.APROBACION)
               .exclude(estado=EstadoSesion.CELEBRADA).order_by("fecha_hora").first())
    if abierta:
        return reverse("dictamen:sesion", args=[abierta.pk]), abierta
    return reverse("dictamen:sesion_nueva") + f"?tipo={TipoSesion.APROBACION}&ejercicio={ejercicio.pk}", None


def panel_por_sesionar(request):
    """Bandeja de la Secretaría Técnica: dictaminadas por ejercicio con la acción «Llevar a sesión de aprobación»."""
    from django.db.models import Count

    from nucleo.models import Ejercicio, bandeja

    if request.user.tipo_unidad != TipoUnidad.SECRETARIA_COMITE:
        return None
    conteo = (bandeja(request.user).filter(estado__clave="dictaminada").values("ejercicio")
              .annotate(n=Count("pk")).order_by("ejercicio"))
    grupos = []
    for fila in conteo:
        ej = Ejercicio.objects.select_related("programa").get(pk=fila["ejercicio"])
        url, sesion = url_llevar_a_sesion(ej)
        grupos.append({"ejercicio": ej, "n": fila["n"], "url": url, "sesion": sesion})
    if not grupos:
        return None
    return {"plantilla": "dictamen/aprobacion/_panel_por_sesionar.html", "contexto": {"grupos": grupos}}


def siguiente_paso(usuario, exp):
    """Siguiente paso de M2 en el expediente (P-13 y P-16)."""
    from django.urls import reverse

    from .models import DictamenJuridico, DictamenTecnico

    estado, tipo = exp.estado.clave, usuario.tipo_unidad
    if estado == "validada":
        if tipo == TipoUnidad.DIRECCION and not DictamenTecnico.objects.filter(expediente=exp).exists():
            return {"texto": "Elaborar el dictamen técnico", "url": reverse("dictamen:tecnico", args=[exp.folio])}
        if tipo == TipoUnidad.JURIDICA and not DictamenJuridico.objects.filter(expediente=exp).exists():
            return {"texto": "Elaborar el dictamen jurídico", "url": reverse("dictamen:juridico", args=[exp.folio])}
    if estado == "dictaminada" and tipo == TipoUnidad.SECRETARIA_COMITE:
        url, sesion = url_llevar_a_sesion(exp.ejercicio)
        return {"texto": "Llevar a sesión de aprobación", "url": url,
                "ayuda": f"Sesión {sesion.numero}" if sesion else "Aún no hay sesión de aprobación abierta: se crea una."}
    return None


def contexto_pestana(request, exp):
    from .vistas.comun import contexto_dictamenes

    return contexto_dictamenes(request, exp)


def superficie_factible(exp):
    """Superficie que cuenta para el monto: la factible del dictamen técnico (nucleo.montos)."""
    from .models import DictamenTecnico

    d = DictamenTecnico.objects.filter(expediente=exp).only("superficie_factible_ha").first()
    return d.superficie_factible_ha if d else None


def fuentes_trazabilidad(expediente):
    """Registros del módulo M2 en la pestaña «Trazabilidad»."""
    from .models import (Acuerdo, DictamenJuridico, DictamenTecnico, MovimientoListado, ResolucionSesion,
                         RevisionPropiedad)

    acuerdos = list(expediente.acuerdos_comite.values_list("pk", flat=True))
    return [
        ("Dictamen técnico", DictamenTecnico.history.filter(expediente_id=expediente.pk)),
        ("Dictamen jurídico", DictamenJuridico.history.filter(expediente_id=expediente.pk)),
        ("Propiedad o posesión", RevisionPropiedad.history.filter(
            dictamen_id__in=list(DictamenJuridico.objects.filter(expediente=expediente).values_list("pk", flat=True)))),
        ("Listados del Comité", ResolucionSesion.history.filter(expediente_id=expediente.pk)),
        ("Acuerdo del Comité", Acuerdo.history.filter(id__in=acuerdos)),
        ("Movimiento de listado", MovimientoListado.history.filter(expediente_id=expediente.pk)),
    ]


def revisar_plazos(hoy):
    from .tecnico import revisar_plazos_dictamen

    return revisar_plazos_dictamen(hoy)


def registrar():
    if filtro_bandeja in extensiones.FILTROS_BANDEJA:
        return
    extensiones.FILTROS_BANDEJA.append(filtro_bandeja)
    extensiones.PANELES_BANDEJA.append(panel_acuerdos)
    extensiones.PANELES_BANDEJA.append(panel_por_sesionar)
    extensiones.SIGUIENTES_PASOS.append(siguiente_paso)
    extensiones.TRAZABILIDAD.append(fuentes_trazabilidad)
    extensiones.PESTANAS_EXPEDIENTE.append({"clave": "dictamenes", "nombre": "Dictámenes",
                                            "plantilla": "dictamen/pestana_dictamenes.html", "contexto": contexto_pestana})
    T = TipoUnidad
    extensiones.MENU.extend([
        {"nombre": "Listado preliminar", "url": "dictamen:listado", "tipos": [T.DIRECCION, T.JURIDICA, T.SECRETARIA_COMITE],
         "grupo": "Listados"},
        {"nombre": "Candidatos", "url": "dictamen:candidatos",
         "tipos": [T.DELEGACION, T.DIRECCION, T.JURIDICA, T.SECRETARIA_COMITE], "grupo": "Listados"},
        {"nombre": "Beneficiarios", "url": "dictamen:beneficiarios",
         "tipos": [T.DELEGACION, T.DIRECCION, T.JURIDICA, T.SECRETARIA_COMITE], "grupo": "Listados"},
        {"nombre": "Sesiones del Comité", "url": "dictamen:sesiones", "grupo": "Dictamen y Comité", "tipos": [T.SECRETARIA_COMITE, T.DIRECCION, T.JURIDICA]},
        {"nombre": "Incumplidas", "url": "dictamen:incumplidas", "grupo": "Dictamen y Comité", "tipos": [T.JURIDICA, T.DIRECCION, T.SECRETARIA_COMITE]},
    ])
    extensiones.REVISIONES_PLAZO.append(revisar_plazos)
    extensiones.SUPERFICIE_APROBADA.append(superficie_factible)
    extensiones.DEMOS.append(cargar_demo)


def cargar_demo():
    from .demo import cargar_demo as cargar

    return cargar()
