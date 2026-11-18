"""HU-6.3 · Pantallas: resultados finales y comprobación por programa y ejercicio, cierre de expedientes, publicación del padrón,
informe anual al Comité y su recepción, y la parte de la pestaña «Seguimiento» del expediente."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from dictamen.models import SesionComite
from ejecucion.vistas.comun import expediente_visible, mensajes_error, responder_archivo
from nucleo.models import Ejercicio, TipoUnidad

from .. import cierre
from ..formularios.cierre import RecepcionInformeForm
from ..models import InformeAnual

AVISO_ACCESO = ("Los resultados finales los consulta el área responsable, la Secretaría Técnica, la Unidad Jurídica y "
                "Administración y Finanzas.")


def _errores(request, e):
    for m in mensajes_error(e):
        messages.error(request, m)


def _ejercicio(request, pk):
    ejercicio = Ejercicio.objects.select_related("programa").filter(pk=pk).first()
    if ejercicio is None:
        raise Http404("No existe el ejercicio.")
    if not cierre.puede_ver(request.user):
        raise PermissionDenied(AVISO_ACCESO)
    if request.user.tipo_unidad == TipoUnidad.DIRECCION and not cierre.es_area_responsable(request.user, ejercicio):
        raise PermissionDenied("Su Dirección no es Instancia Ejecutora de este programa.")
    return ejercicio


@login_required
def pagina(request):
    if not cierre.puede_ver(request.user):
        raise PermissionDenied(AVISO_ACCESO)
    tarjetas = []
    for ej in cierre.ejercicios_de(request.user):
        exps = cierre.expedientes_de(ej)
        tarjetas.append({"ejercicio": ej, "expedientes": exps.count(),
                         "cerrados": exps.filter(estado__clave="ejercicio_cerrado").count(),
                         "padron": cierre.padron_publicado(ej), "informe": cierre.informe_de(ej)})
    por_recibir = list(cierre.informes_por_recibir()) if request.user.tipo_unidad == TipoUnidad.SECRETARIA_COMITE else []
    return render(request, "seguimiento/cierre/pagina.html", {"tarjetas": tarjetas, "por_recibir": por_recibir})


@login_required
def detalle(request, pk):
    ej = _ejercicio(request, pk)
    filas, total = cierre.resultados_ejercicio(ej)
    informe = cierre.informe_de(ej)
    u = request.user
    return render(request, "seguimiento/cierre/detalle.html", {
        "ejercicio": ej, "filas": filas, "total": total, "estado": cierre.estado_cierre(ej, total), "informe": informe,
        "padron": cierre.padron_publicado(ej), "cfg_padron": cierre.config_padron(ej), "cfg_informe": cierre.config_informe(ej),
        "comite": cierre.nombre_comite(ej), "cfg_cierre": cierre.datos_cierre(), "es_area": cierre.es_area_responsable(u, ej),
        "puede_recibir": u.tipo_unidad == TipoUnidad.SECRETARIA_COMITE and informe is not None and informe.recibido_en is None,
        "form_recepcion": RecepcionInformeForm(sesiones=cierre.sesiones_para_informe(informe)) if informe is not None else None})


@login_required
def resultados_csv(request, pk):
    ej = _ejercicio(request, pk)
    respuesta = HttpResponse(cierre.resultados_csv(ej), content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="resultados_finales_{ej.programa.clave}_{ej.anio}.csv"'
    return respuesta


@login_required
@require_POST
def cerrar_expediente(request, folio):
    exp = expediente_visible(request, folio)
    try:
        cierre.cerrar_expediente(request.user, exp)
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        exp.refresh_from_db()
        messages.success(request, f"Expediente {folio} cerrado (acuse {exp.cierre.acuse.folio}).")
    destino = request.POST.get("siguiente", "")
    return redirect(destino if destino.startswith("/") and not destino.startswith("//")
                    else f"/recepcion/expediente/{folio}/?pestana=seguimiento")


@login_required
@require_POST
def cerrar_listos(request, pk):
    ej = _ejercicio(request, pk)
    try:
        cerrados, omitidos = cierre.cerrar_listos(request.user, ej)
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        if cerrados:
            messages.success(request, f"{len(cerrados)} expediente(s) cerrado(s) con sus resultados finales.")
        else:
            messages.info(request, "Ningún expediente está listo para cerrar: revise las diferencias señaladas.")
        for e, motivo in omitidos:
            messages.error(request, f"{e.folio}: {motivo}")
    return redirect("seguimiento:cierre_detalle", pk)


@login_required
@require_POST
def publicar_padron(request, pk):
    ej = _ejercicio(request, pk)
    try:
        p = cierre.publicar_padron(request.user, ej)
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Padrón publicado (acuse {p.acuse.folio}): la página pública se actualiza sola.")
    return redirect("seguimiento:cierre_detalle", pk)


@login_required
@require_POST
def enviar_informe(request, pk):
    ej = _ejercicio(request, pk)
    try:
        i = cierre.enviar_informe(request.user, ej)
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Informe anual enviado al Comité (acuse {i.acuse.folio}).")
    return redirect("seguimiento:cierre_detalle", pk)


@login_required
def informe_archivo(request, pk):
    ej = _ejercicio(request, pk)
    informe = InformeAnual.objects.filter(ejercicio=ej).first()
    if informe is None:
        raise Http404("El informe anual todavía no se envía.")
    return responder_archivo(request, informe.archivo)


@login_required
@require_POST
def recepcion_informe(request, pk):
    ej = _ejercicio(request, pk)
    informe = get_object_or_404(InformeAnual, ejercicio=ej)
    form = RecepcionInformeForm(request.POST, sesiones=cierre.sesiones_para_informe(informe))
    if not form.is_valid():
        messages.error(request, "Revise la sesión elegida.")
        return redirect("seguimiento:cierre_detalle", pk)
    d = form.cleaned_data
    sesion = SesionComite.objects.filter(pk=d["sesion"]).first() if d.get("sesion") else None
    try:
        cierre.registrar_recepcion(request.user, informe, sesion, d.get("observaciones", ""))
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, "Recepción del informe registrada con su fecha y su hora.")
    return redirect("seguimiento:cierre_detalle", pk)


def contexto_cierre_exp(request, exp):
    """Pestaña «Seguimiento» del expediente: sus resultados finales y, para el área responsable, el cierre."""
    if not hasattr(exp, "firma_contrato"):
        return {"cierre_exp": None}
    fila = cierre.resultado_expediente(exp)
    area = request.user.tipo_unidad == TipoUnidad.DIRECCION and cierre.es_area_responsable(request.user, exp.ejercicio)
    return {"cierre_exp": fila, "puede_cerrar_exp": area and fila["puede_cerrar"]}
