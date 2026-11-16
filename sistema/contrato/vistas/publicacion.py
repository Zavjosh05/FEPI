"""HU-3.1 · Pantallas: publicación (área responsable), bandeja de notificaciones (Delegación), página pública
de resultados (sin iniciar sesión) y el contexto de la pestaña «Contrato»."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from dictamen.models import ResultadoListado
from nucleo import dias_habiles, plazos
from nucleo.models import Ejercicio, Notificacion, TipoUnidad

from .. import publicacion
from ..formularios.publicacion import EntregaForm, PublicarForm
from ..models import Publicacion
from .comun import mensajes_error

TIPOS_QUE_VEN_PUBLICACION = (TipoUnidad.DIRECCION, TipoUnidad.SECRETARIA_COMITE, TipoUnidad.JURIDICA)


def _exigir_personal(request):
    if request.user.tipo_unidad not in TIPOS_QUE_VEN_PUBLICACION and not request.user.is_superuser:
        raise PermissionDenied("La publicación de resultados la atiende el área responsable del programa.")


# ----------------------------------------------------------------------------- publicación (área responsable)
@login_required
def lista(request):
    _exigir_personal(request)
    sesiones = list(publicacion.sesiones_publicables(request.user).order_by("-acta_fecha"))
    return render(request, "contrato/publicacion/lista.html", {
        "por_publicar": [s for s in sesiones if s.autoriza_publicacion and not hasattr(s, "publicacion")],
        "publicadas": [s for s in sesiones if hasattr(s, "publicacion")],
        "sin_autorizacion": [s for s in sesiones if not s.autoriza_publicacion],
        "puede_publicar": request.user.tipo_unidad == TipoUnidad.DIRECCION,
    })


@login_required
def detalle(request, pk):
    _exigir_personal(request)
    sesion = get_object_or_404(publicacion.sesiones_publicables(request.user), pk=pk)
    pub = getattr(sesion, "publicacion", None)
    form = PublicarForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            pub = publicacion.publicar(request.user, sesion, lugares=form.cleaned_data["lugares"])
        except (ValidationError, PermissionDenied) as e:
            for m in mensajes_error(e):
                messages.error(request, m)
        else:
            messages.success(request, f"Resultados publicados (acuse {pub.acuse.folio}). Los avisos quedaron en la "
                                      "bandeja de notificaciones de cada Delegación.")
            return redirect("contrato:publicacion", pub.sesion_id)
    resoluciones = sesion.resoluciones.select_related("expediente__predio__municipio", "expediente__solicitante")
    listados = [(clave, nombre, [r for r in resoluciones if r.resultado == clave])
                for clave, nombre in ResultadoListado.choices]
    limite, fundamento = publicacion.fecha_limite_publicacion(sesion.ejercicio, sesion.acta_fecha)
    return render(request, "contrato/publicacion/detalle.html", {
        "sesion": sesion, "pub": pub, "form": form, "listados": listados, "limite": limite, "fundamento": fundamento,
        "puede_publicar": request.user.tipo_unidad == TipoUnidad.DIRECCION and pub is None and sesion.autoriza_publicacion,
        "notificaciones": Notificacion.objects.filter(datos__publicacion=pub.pk).select_related(
            "expediente", "acuse_envio", "acuse_notificacion").order_by("expediente__folio", "tipo") if pub else [],
    })


# ----------------------------------------------------------------------------- notificaciones (Delegación)
@login_required
def bandeja_notificaciones(request):
    if request.user.tipo_unidad not in (TipoUnidad.DELEGACION, TipoUnidad.DIRECCION) and not request.user.is_superuser:
        raise PermissionDenied("Las notificaciones las entrega la Delegación y las envía el área responsable.")
    ver = request.GET.get("ver", "pendientes")
    aviso = request.GET.get("aviso", "")      # P-25: el folio del panel abre ya el formulario de ese aviso
    todas = publicacion.notificaciones_visibles(request.user)
    pendientes = todas.filter(notificada_en__isnull=True)
    if request.user.tipo_unidad == TipoUnidad.DELEGACION:
        pendientes = pendientes.filter(delegacion=request.user.unidad)
    qs = {"pendientes": pendientes, "entregadas": todas.filter(notificada_en__isnull=False)}.get(ver, todas)
    visibles = list(qs.order_by("-enviada_en", "-id").prefetch_related("expediente__ejercicio__plazos")[:200])
    with dias_habiles.inhabiles_en_memoria():     # los vencimientos de la lista no consultan el catálogo por renglón
        citas = publicacion.vencimientos_de(visibles)
        filas = [{"n": n, "vencimiento": citas.get(n.pk), "estado": citas[n.pk].estado() if n.pk in citas else "",
                  "puede_entregar": request.user.tipo_unidad == TipoUnidad.DELEGACION
                  and request.user.unidad_id == n.delegacion_id and n.notificada_en is None,
                  "abierta": str(n.pk) == aviso,
                  "form": EntregaForm(prefix=f"n{n.pk}")} for n in visibles]
    return render(request, "contrato/publicacion/notificaciones.html", {
        "filas": filas, "ver": ver, "total_pendientes": pendientes.count(), "total": todas.count(),
        "es_delegacion": request.user.tipo_unidad == TipoUnidad.DELEGACION, "volver": f"?ver={ver}",
    })


@login_required
@require_POST
def entregar(request, pk):
    notificacion = get_object_or_404(publicacion.notificaciones_visibles(request.user), pk=pk)
    form = EntregaForm(request.POST, prefix=f"n{pk}")
    if form.is_valid():
        try:
            acuse = publicacion.registrar_entrega(request.user, notificacion, form.cleaned_data["medio"],
                                                  form.cleaned_data["fecha_hora"], form.cleaned_data["observaciones"])
        except (ValidationError, PermissionDenied) as e:
            for m in mensajes_error(e):
                messages.error(request, m)
        else:
            messages.success(request, f"Notificación registrada (acuse {acuse.folio}).")
    else:
        for campo, errores in form.errors.items():
            for e in errores:
                messages.error(request, f"{form.fields[campo].label}: {e}")
    return redirect(reverse("contrato:notificaciones") + (request.POST.get("volver") or ""))


# ----------------------------------------------------------------------------- pestaña «Contrato»
def contexto_publicacion(request, exp):
    pub = exp.resultados_publicados.select_related("publicacion__acuse").order_by("-publicacion__publicada_en").first()
    notifs = list(exp.notificaciones.select_related("acuse_envio", "acuse_notificacion", "delegacion")
                  .order_by("enviada_en", "id"))
    filas = []
    for n in notifs:
        filas.append({"n": n, "vencimiento": publicacion.vencimiento_de(n),
                      "puede_entregar": request.user.tipo_unidad == TipoUnidad.DELEGACION
                      and request.user.unidad_id == n.delegacion_id and n.notificada_en is None,
                      "form": EntregaForm(prefix=f"n{n.pk}")})
    por_publicar = (exp.estado.clave == "aprobada" and request.user.tipo_unidad == TipoUnidad.DIRECCION)
    sesion = publicacion.sesion_de_expediente(exp) if por_publicar else None
    return {"resultado_publicado": pub, "notificaciones_exp": filas, "sesion_por_publicar": sesion,
            "plazo_publicacion": plazos.vencimiento(exp, "firma_programada")}


# ----------------------------------------------------------------------------- página pública (sin sesión)
def ultima_por_programa(publicaciones):
    """De varias publicaciones (de la más reciente a la más antigua), la última de cada programa y ejercicio,
    ordenadas por nombre del programa: un programa publica una vez por sesión del Comité, pero en el índice
    aparece una sola vez."""
    ultimas = {}
    for p in publicaciones:
        ultimas.setdefault(p.ejercicio_id, p)
    return sorted(ultimas.values(), key=lambda p: (p.ejercicio.programa.nombre, -p.ejercicio.anio))


def resultados(request):
    """Índice público: los programas y ejercicios que ya publicaron resultados."""
    return render(request, "contrato/publicacion/publica_indice.html",
                  {"publicaciones": ultima_por_programa(publicacion.publicaciones_publicas())})


LIMITE_PUBLICO = 250


def resultados_programa(request, clave, anio):
    """Listados publicados de un programa y ejercicio; busca por folio. Solo datos publicables."""
    ejercicio = get_object_or_404(Ejercicio.objects.select_related("programa"), programa__clave=clave.upper(), anio=anio)
    publicaciones = list(Publicacion.objects.filter(ejercicio=ejercicio).select_related("sesion").order_by("publicada_en"))
    if not publicaciones:
        raise Http404("Este programa aún no publica resultados.")
    folio = request.GET.get("folio", "").strip()
    renglones = list(publicacion.renglones_publicos(ejercicio, folio))
    completos = [(clave_l, nombre, [r for r in renglones if r.resultado == clave_l]) for clave_l, nombre in ResultadoListado.choices]
    # Cada listado muestra a lo más LIMITE_PUBLICO renglones; el resto se encuentra buscando por folio
    listados = [(c, n, filas[:LIMITE_PUBLICO], max(len(filas) - LIMITE_PUBLICO, 0)) for c, n, filas in completos]
    return render(request, "contrato/publicacion/publica_programa.html", {
        "ejercicio": ejercicio, "publicaciones": publicaciones, "listados": listados, "folio": folio,
        "total": len(renglones),
    })
