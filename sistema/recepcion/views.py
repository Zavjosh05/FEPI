import json
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from nucleo.models import Expediente, Persona, TipoPersonaGeneral, TipoUnidad, expedientes_visibles
from nucleo.pasos import siguiente_paso
from nucleo.views import _entregar_archivo

from . import geometria, servicios
from .forms import PoligonoForm, RegistroSolicitudForm, RevisionForm
from .models import EstadoRevision, Poligono, ResultadoValidacion

PESTANAS = [
    ("solicitud", "Solicitud"), ("requisitos", "Requisitos"), ("ubicacion", "Ubicación"),
    ("validacion", "Validación"), ("documentos", "Documentos y acuses"), ("bitacora", "Bitácora"),
]


def _mensajes_error(error):
    return error.messages if hasattr(error, "messages") else [str(error)]


def _expediente(request, folio):
    exp = expedientes_visibles(request.user).filter(folio=folio).first()
    if exp is None:
        raise Http404("No existe el expediente o no pertenece a su unidad.")
    return exp


# ----------------------------------------------------------------------------- HU-1.1
@login_required
def registrar(request):
    if request.user.tipo_unidad != TipoUnidad.DELEGACION:
        raise PermissionDenied("Solo la Delegación registra solicitudes en ventanilla.")
    es_htmx_recarga = request.headers.get("HX-Request") and request.method == "GET"
    if request.method == "POST":
        form = RegistroSolicitudForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            datos = servicios.DatosSolicitud(
                ejercicio=d["ejercicio"], municipio=d["municipio"], nombre_predio=d["nombre_predio"],
                tipo_persona=d["tipo_persona"], modalidad=d.get("modalidad"),
                solicitante_nombre=d["solicitante_nombre"], solicitante_tipo=form.tipo_general(d["tipo_persona"]),
                localidad=d["localidad"], superficie_solicitada_ha=d["superficie_solicitada_ha"], curp=d["curp"],
                rfc=d["rfc"], telefono=d["telefono"], correo=d["correo"], representante=d["representante"],
                con_representante_legal=d["con_representante_legal"], es_refrendo=d["es_refrendo"],
                predio_existente=d["predio_existente"], observaciones=d["observaciones"],
                beneficiaria_nombre=d.get("beneficiaria_nombre", ""), beneficiaria_curp=d.get("beneficiaria_curp", ""),
                beneficiaria_telefono=d.get("beneficiaria_telefono", ""),
            )
            try:
                exp = servicios.registrar_solicitud(request.user, datos)
            except ValidationError as e:
                for m in _mensajes_error(e):
                    form.add_error("municipio" if "municipio" in m else None, m)
            else:
                acuse = exp.acuses.get(tipo="recepcion")
                messages.success(request, f"Solicitud {exp.folio} registrada. Acuse de recepción {acuse.folio} "
                                          f"con fecha y hora {servicios.fmt_fecha_hora(acuse.fecha_hora)}.")
                return redirect("recepcion:expediente", exp.folio)
    else:
        # Al cambiar de programa (HTMX) se vuelve a pintar el formulario con sus tipos de persona y modalidades.
        form = RegistroSolicitudForm(initial=request.GET.dict() if es_htmx_recarga else None)
    return render(request, "recepcion/registrar.html", {"form": form, "delegacion": request.user.unidad})


@login_required
def delegacion_de_municipio(request):
    """Fragmento HTMX: qué Delegación atiende el municipio elegido."""
    from nucleo.models import Municipio

    m = Municipio.objects.select_related("delegacion").filter(pk=request.GET.get("municipio") or 0).first()
    return render(request, "recepcion/_delegacion_municipio.html", {"municipio": m, "delegacion": request.user.unidad})


# ----------------------------------------------------------------------------- expediente
@login_required
def expediente(request, folio):
    exp = _expediente(request, folio)
    pestana = request.GET.get("pestana", "solicitud")
    if pestana == "ubicacion" and not exp.programa.usa_poligono:
        pestana = "solicitud"
    contexto = contexto_expediente(request, exp)
    from nucleo.extensiones import PESTANAS_EXPEDIENTE

    pestanas = [p for p in PESTANAS if p[0] != "ubicacion" or exp.programa.usa_poligono]
    extra = {p["clave"]: p for p in PESTANAS_EXPEDIENTE}
    # Las pestañas de otros módulos van antes de «Documentos y acuses».
    pestanas[-2:-2] = [(p["clave"], p["nombre"]) for p in PESTANAS_EXPEDIENTE]
    if pestana not in {c for c, _ in pestanas}:
        pestana = "solicitud"
    if pestana in extra:
        contexto["plantilla_pestana"] = extra[pestana]["plantilla"]
        contexto.update(extra[pestana]["contexto"](request, exp))
    contexto.update({"pestana": pestana, "pestanas": pestanas})
    if pestana == "ubicacion":
        contexto["form_poligono"] = PoligonoForm()
    return render(request, "recepcion/expediente.html", contexto)


def contexto_expediente(request, exp):
    usuario = request.user
    es_delegacion = usuario.tipo_unidad == TipoUnidad.DELEGACION
    es_direccion = usuario.tipo_unidad == TipoUnidad.DIRECCION
    revisiones = list(exp.revisiones.select_related("requisito", "documento"))
    return {
        "exp": exp,
        "revisiones": revisiones,
        "resumen": {e: sum(1 for r in revisiones if r.estado == e) for e in EstadoRevision.values},
        "problemas_envio": servicios.problemas_para_enviar(exp),
        "puede_editar_requisitos": es_delegacion and exp.estado.clave in servicios.ESTADOS_EDITABLES_DELEGACION,
        "puede_enviar": es_delegacion and exp.transiciones_posibles(usuario).filter(destino__clave="enviada_direccion").exists(),
        "puede_validar": es_direccion and exp.transiciones_posibles(usuario).filter(destino__clave="validada").exists(),
        "puede_poligono": es_delegacion and exp.estado.clave in servicios.ESTADOS_POLIGONO and exp.programa.usa_poligono,
        "transiciones_motivo": [t for t in exp.transiciones_posibles(usuario) if t.requiere_motivo],
        "poligonos": list(exp.poligonos.select_related("registrado_por", "prestador")),
        "validaciones": list(exp.validaciones.prefetch_related("faltantes__requisito")),
        "aviso": servicios.aviso_vigente(exp) if exp.estado.clave == "faltantes" else None,
        "limite_recepcion": servicios.plazo_recepcion(exp),
        "vigencia_refrendo": servicios.vigencia_refrendo(exp) if exp.es_refrendo else None,
        "eventos": exp.eventos.select_related("usuario", "unidad", "acuse", "estado_origen", "estado_destino")
        .order_by("fecha_hora", "id"),     # cronológico; en un mismo instante, el orden en que se registraron (P-23)
        "historial": exp.history.select_related("history_user", "estado").order_by("-history_date")[:50],
        "es_delegacion": es_delegacion,
        "es_direccion": es_direccion,
        "siguiente_paso": siguiente_paso(usuario, exp),
        "sin_poligono": exp.programa.usa_poligono and not any(p.vigente for p in exp.poligonos.all()),
    }


# ----------------------------------------------------------------------------- HU-1.2
@login_required
@require_POST
def revisar_requisito(request, folio, pk):
    exp = _expediente(request, folio)
    revision = get_object_or_404(exp.revisiones.select_related("requisito"), pk=pk)
    form = RevisionForm(request.POST, request.FILES)
    error = None
    if form.is_valid():
        d = form.cleaned_data
        try:
            servicios.revisar_requisito(request.user, revision, d["estado"], archivo=d.get("archivo"),
                                        en_archivo_probosque=d["en_archivo_probosque"],
                                        fecha_documento=d.get("fecha_documento"), observaciones=d["observaciones"])
        except (ValidationError, PermissionDenied) as e:
            error = " ".join(_mensajes_error(e))
        revision.refresh_from_db()
    else:
        error = "Revise los datos: " + "; ".join(f"{k}: {' '.join(v)}" for k, v in form.errors.items())
    contexto = contexto_expediente(request, exp)
    contexto.update({"r": revision, "error_fila": error})
    respuesta = render(request, "recepcion/_fila_requisito.html", contexto)
    respuesta["HX-Trigger"] = "requisitos-actualizados"
    return respuesta


@login_required
def panel_envio(request, folio):
    exp = _expediente(request, folio)
    return render(request, "recepcion/_panel_envio.html", contexto_expediente(request, exp))


@login_required
@require_POST
def enviar(request, folio):
    exp = _expediente(request, folio)
    try:
        acuse = servicios.enviar_a_direccion(request.user, exp)
    except (ValidationError, PermissionDenied) as e:
        for m in _mensajes_error(e):
            messages.error(request, m)
        return redirect(reverse("recepcion:expediente", args=[folio]) + "?pestana=requisitos")
    messages.success(request, f"Expediente enviado a la Dirección el {servicios.fmt_fecha_hora(acuse.fecha_hora)}. "
                              f"Acuse {acuse.folio}.")
    return redirect(reverse("recepcion:expediente", args=[folio]) + "?pestana=documentos")


@login_required
@require_POST
def cambiar_con_motivo(request, folio):
    """Transiciones que piden motivo (por ejemplo, tener por desechada la solicitud)."""
    exp = _expediente(request, folio)
    try:
        t = exp.cambiar_estado(request.POST.get("destino", ""), request.user, motivo=request.POST.get("motivo", ""))
    except (ValidationError, PermissionDenied) as e:
        for m in _mensajes_error(e):
            messages.error(request, m)
    except Exception:  # destino inexistente
        messages.error(request, "Acción no reconocida.")
    else:
        messages.success(request, f"{t.accion}: hecho.")
    return redirect(reverse("recepcion:expediente", args=[folio]) + "?pestana=bitacora")


# ----------------------------------------------------------------------------- HU-1.3
@login_required
@require_POST
def registrar_poligono(request, folio):
    exp = _expediente(request, folio)
    form = PoligonoForm(request.POST, request.FILES)
    destino = reverse("recepcion:expediente", args=[folio]) + "?pestana=ubicacion"
    if not form.is_valid():
        for errores in form.errors.values():
            for m in errores:
                messages.error(request, m)
        return redirect(destino)
    d = form.cleaned_data
    try:
        if d.get("archivo"):
            geom, origen = geometria.leer_archivo(d["archivo"])
        else:
            geom, origen = geometria.leer_geojson_texto(d["dibujo"]), "dibujo"
        prestador = None
        if d["levantado_por"] == "prestador":
            prestador, _ = Persona.objects.get_or_create(
                rfn=d["prestador_rfn"], tipo=TipoPersonaGeneral.PRESTADOR, defaults={"nombre": d["responsable"]})
        pol = servicios.registrar_poligono(
            request.user, exp, geom, origen, d["levantado_por"], d["responsable"], d["fecha_levantamiento"],
            prestador=prestador, archivo=d.get("archivo"), motivo_cambio=d.get("motivo_cambio", ""),
        )
    except (ValidationError, PermissionDenied) as e:
        for m in _mensajes_error(e):
            messages.error(request, m)
        return redirect(destino)
    messages.success(request, f"Polígono registrado: {pol.superficie_ha} ha ({pol.get_tipo_cambio_display().lower()}).")
    if pol.aviso:
        messages.warning(request, pol.aviso)
    return redirect(destino)


@login_required
def poligonos_geojson(request, folio):
    exp = _expediente(request, folio)
    elementos = []
    for p in exp.poligonos.all():
        elementos.append({
            "type": "Feature", "geometry": json.loads(p.geom.geojson),
            "properties": {"id": p.pk, "vigente": p.vigente, "superficie_ha": float(p.superficie_ha),
                           "registrado": p.registrado_en.isoformat(), "tipo_cambio": p.get_tipo_cambio_display()},
        })
    municipio = exp.predio.municipio
    return JsonResponse({
        "poligonos": {"type": "FeatureCollection", "features": elementos},
        "municipio": {"type": "Feature", "geometry": json.loads(municipio.geom.geojson),
                      "properties": {"nombre": municipio.nombre}},
    })


@login_required
def archivo_poligono(request, folio, pk):
    exp = _expediente(request, folio)
    pol = get_object_or_404(Poligono, pk=pk, expediente=exp)
    if not pol.archivo:
        raise Http404
    return _entregar_archivo(pol.archivo, Path(pol.archivo.name).name)


# ----------------------------------------------------------------------------- HU-1.4
@login_required
def validar(request, folio):
    exp = _expediente(request, folio)
    contexto = contexto_expediente(request, exp)
    if not contexto["puede_validar"]:
        messages.warning(request, f"El expediente está «{exp.estado}»; no hay validación pendiente para su unidad.")
        return redirect(reverse("recepcion:expediente", args=[folio]) + "?pestana=validacion")
    if request.method == "POST":
        accion = request.POST.get("accion")
        marcados = request.POST.getlist("faltante")
        evaluacion = servicios.evaluar_para_validacion(exp)
        automaticos = [e for e in evaluacion if not e.valida]
        if accion == "validar" and (marcados or automaticos):
            messages.error(request, "Hay requisitos faltantes o no válidos: emita el aviso de faltantes.")
        elif accion == "faltantes" and not (marcados or automaticos):
            messages.error(request, "Marque al menos un requisito faltante para emitir el aviso.")
        else:
            try:
                val = servicios.validar_expediente(request.user, exp, marcados, request.POST.get("observaciones", ""))
            except (ValidationError, PermissionDenied) as e:
                for m in _mensajes_error(e):
                    messages.error(request, m)
            else:
                if val.resultado == ResultadoValidacion.VALIDADO:
                    messages.success(request, f"Expediente validado. Constancia {val.acuse.folio}.")
                else:
                    limite = f"{val.fecha_limite:%d/%m/%Y}" if val.fecha_limite else "sin plazo en las reglas"
                    messages.success(request, f"Aviso de faltantes {val.acuse.folio} emitido con fecha límite "
                                              f"{limite}; se notifica por conducto de "
                                              f"{exp.delegacion.nombre}.")
                return redirect(reverse("recepcion:expediente", args=[folio]) + "?pestana=validacion")
    contexto["evaluacion"] = servicios.evaluar_para_validacion(exp)
    from django.utils import timezone
    from nucleo import plazos

    venc = plazos.vencimiento(exp, "faltantes_direccion", fecha_evento=timezone.now())
    contexto["plazo_faltantes"] = venc.plazo if venc else None
    if venc and venc.tiene_fecha:
        contexto["limite_si_hoy"] = venc.vencimiento
    return render(request, "recepcion/validar.html", contexto)


@login_required
@require_POST
def notificar(request, folio):
    exp = _expediente(request, folio)
    aviso = servicios.aviso_vigente(exp)
    try:
        if aviso is None:
            raise ValidationError("No hay aviso de faltantes por notificar.")
        acuse = servicios.registrar_notificacion(request.user, aviso)
    except (ValidationError, PermissionDenied) as e:
        for m in _mensajes_error(e):
            messages.error(request, m)
    else:
        messages.success(request, f"Notificación registrada el {servicios.fmt_fecha_hora(acuse.fecha_hora)}. Acuse {acuse.folio}.")
    return redirect(reverse("recepcion:expediente", args=[folio]) + "?pestana=validacion")
