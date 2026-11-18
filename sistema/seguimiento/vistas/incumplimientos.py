"""HU-6.2 · Pantallas: incumplimientos por atender (lo que preparó el sistema), avisos de omisión con su plazo, requerimientos de
devolución, depósitos y cuentas para reintegros; y la parte de la pestaña «Seguimiento» del expediente."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from ejecucion.vistas.comun import expediente_visible, mensajes_error, responder_archivo
from nucleo.models import Programa, TipoUnidad

from .. import incumplimientos
from ..formularios.incumplimientos import AvisoOmisionForm, CuentaForm, DepositoForm, RequerimientoForm, SubsanarForm
from ..models import AvisoOmision, Requerimiento, Senalamiento


def _destino(folio):
    return reverse("recepcion:expediente", args=[folio]) + "?pestana=seguimiento"


def _volver(request, folio):
    return redirect(request.POST.get("siguiente") or _destino(folio))


def _errores(request, e):
    for m in mensajes_error(e):
        messages.error(request, m)


def _causas(exp):
    return [f"{c.get('numeral', '')}: {c.get('texto', '')}"[:290] for c in (exp.ejercicio.datos or {}).get("causas_incumplimiento", [])
            if isinstance(c, dict)]


UNIDADES = (TipoUnidad.DIRECCION, TipoUnidad.DELEGACION, TipoUnidad.JURIDICA, TipoUnidad.ADMIN_FINANZAS, TipoUnidad.SECRETARIA_COMITE)


@login_required
def pagina(request):
    u = request.user
    if u.tipo_unidad not in UNIDADES and not u.is_superuser:
        raise PermissionDenied("Esta pantalla no es de su unidad.")
    requerimientos = list(incumplimientos.requerimientos_visibles(u)[:200])
    programas = list(Programa.objects.order_by("clave"))
    cuentas = [{"programa": p, "cuenta": incumplimientos.cuenta_vigente(p), "config": incumplimientos.config_cuenta(p)}
               for p in programas]
    return render(request, "seguimiento/incumplimientos/pagina.html", {
        "senalamientos": list(incumplimientos.senalamientos_de(u)[:100]),
        "avisos": list(AvisoOmision.objects.filter(expediente__in=_visibles(u)).select_related(
            "expediente__ejercicio__programa", "acuse")[:100]),
        "requerimientos": requerimientos, "cuentas": cuentas,
        "es_juridica": u.tipo_unidad == TipoUnidad.JURIDICA, "es_finanzas": u.tipo_unidad == TipoUnidad.ADMIN_FINANZAS,
        "form_requerimiento": RequerimientoForm(), "form_deposito": DepositoForm(),
        "form_cuenta": CuentaForm(programas=programas) if u.tipo_unidad == TipoUnidad.ADMIN_FINANZAS else None,
    })


def _visibles(usuario):
    from nucleo.models import expedientes_visibles

    return expedientes_visibles(usuario)


@login_required
@require_POST
def avisar(request, folio):
    exp = expediente_visible(request, folio)
    form = AvisoOmisionForm(request.POST, causas=_causas(exp))
    if not form.is_valid():
        messages.error(request, "Describa las omisiones y su fecha límite para subsanarlas.")
        return redirect(_destino(folio))
    d = form.cleaned_data
    incidencia = None
    if d.get("incidencia"):
        from ejecucion.models import Incidencia

        incidencia = Incidencia.objects.filter(pk=d["incidencia"], expediente=exp).first()
    try:
        a = incumplimientos.avisar_omision(request.user, exp, d["omisiones"], d["vence"], d.get("causa", ""), incidencia)
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Aviso de omisiones enviado a la Delegación con el acuse {a.acuse.folio}; vence el "
                                  f"{a.vence:%d/%m/%Y}.")
    return redirect(_destino(folio))


@login_required
@require_POST
def subsanar(request, pk):
    aviso = get_object_or_404(AvisoOmision, pk=pk)
    expediente_visible(request, aviso.expediente.folio)
    form = SubsanarForm(request.POST)
    try:
        incumplimientos.dar_por_subsanadas(request.user, aviso, form.data.get("motivo", ""))
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, "Omisiones subsanadas; el expediente sigue su trámite.")
    return redirect(_destino(aviso.expediente.folio))


@login_required
@require_POST
def confirmar(request, pk):
    s = get_object_or_404(Senalamiento, pk=pk)
    expediente_visible(request, s.expediente.folio)
    try:
        incumplimientos.confirmar(request.user, s)
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Confirmado: {s.resultado}.")
    return _volver(request, s.expediente.folio)


@login_required
@require_POST
def emitir(request, pk):
    r = get_object_or_404(Requerimiento, pk=pk)
    form = RequerimientoForm(request.POST)
    form.is_valid()
    d = form.cleaned_data
    try:
        incumplimientos.emitir_requerimiento(request.user, r, d.get("plantas") or 0, d.get("precio_planta"), d.get("fuente_precio", ""))
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        r.refresh_from_db()
        messages.success(request, f"Requerimiento emitido ({r.acuse.folio}); la Delegación lo notifica." if r.acuse_id
                         else "Sin recurso por devolver.")
    return _volver(request, r.expediente.folio)


@login_required
@require_POST
def comprobar(request, pk):
    r = get_object_or_404(Requerimiento, pk=pk)
    form = DepositoForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Revise los datos del depósito.")
        return _volver(request, r.expediente.folio)
    d = form.cleaned_data
    try:
        incumplimientos.comprobar_deposito(request.user, r, d["fecha"], d["importe"], d["referencia"], d["archivo"])
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, "Depósito comprobado: el expediente queda reintegrado.")
    return _volver(request, r.expediente.folio)


@login_required
@require_POST
def registrar_cuenta(request):
    programas = list(Programa.objects.order_by("clave"))
    form = CuentaForm(request.POST, programas=programas)
    if not form.is_valid():
        messages.error(request, "Escriba el titular, el banco y la cuenta.")
        return redirect("seguimiento:incumplimientos")
    d = form.cleaned_data
    try:
        c = incumplimientos.registrar_cuenta(request.user, Programa.objects.get(pk=d["programa"]), d["titular"], d["banco"],
                                             d["cuenta"], d.get("referencia", ""))
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Cuenta para reintegros de {c.programa.nombre} registrada.")
    return redirect("seguimiento:incumplimientos")


@login_required
def archivo_deposito(request, pk):
    r = Requerimiento.objects.filter(pk=pk).select_related("expediente").first()
    if r is None or not r.deposito_archivo:
        raise Http404
    if request.user.tipo_unidad not in (TipoUnidad.ADMIN_FINANZAS, TipoUnidad.JURIDICA):
        expediente_visible(request, r.expediente.folio)
    return responder_archivo(request, r.deposito_archivo)


def contexto_incumplimientos_exp(request, exp):
    u = request.user
    puede_avisar = incumplimientos.puede_avisar(u, exp)
    incidencia = next((s for s in incumplimientos.senalamientos_de(u).filter(expediente=exp, tipo="incidencia")), None) \
        if u.tipo_unidad == TipoUnidad.DIRECCION else None
    reqs = list(exp.requerimientos.select_related("cuenta", "acuse", "acuerdo__sesion", "acuse_deposito"))
    return {
        "avisos_omision": list(exp.avisos_omision.select_related("acuse", "notificacion")),
        "senalamientos_exp": list(incumplimientos.senalamientos_de(u).filter(expediente=exp))
        if u.tipo_unidad in (TipoUnidad.DIRECCION, TipoUnidad.DELEGACION) else [],
        "puede_avisar": puede_avisar,
        "form_aviso": AvisoOmisionForm(causas=_causas(exp), initial={"incidencia": incidencia.datos.get("incidencia") if incidencia else None})
        if puede_avisar else None,
        "nota_plazo_omision": incumplimientos.datos_incumplimientos()["omisiones"]["nota_plazo"],
        "aviso_por_subsanar": incumplimientos.aviso_vigente(exp) if u.tipo_unidad == TipoUnidad.DIRECCION
        and exp.estado.clave == "omisiones_por_subsanar" else None,
        "form_subsanar": SubsanarForm(), "requerimientos_exp": reqs,
        "puede_emitir": u.tipo_unidad == TipoUnidad.JURIDICA, "puede_comprobar": u.tipo_unidad == TipoUnidad.ADMIN_FINANZAS,
        "planta_aplica": incumplimientos.planta_aplica(exp), "fundamento_planta": incumplimientos.fundamento_planta(exp),
        "form_requerimiento": RequerimientoForm(), "form_deposito": DepositoForm(),
        "cuenta_programa": incumplimientos.cuenta_vigente(exp.programa) if reqs else None,
        "inscripcion_listado": _inscripcion(exp) if exp.estado.clave in ("cancelada", "en_devolucion", "reintegrada") else None,
    }


def _inscripcion(exp):
    from dictamen.models import PersonaIncumplida

    return PersonaIncumplida.objects.filter(persona=exp.beneficiaria, activa=True).order_by("-fecha_inscripcion", "-pk").first()
