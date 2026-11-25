"""HU-2.2 · Pantallas del dictamen jurídico y de los catálogos de incumplimiento."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from nucleo.models import Predio, TipoUnidad

from .. import juridico
from ..formularios.juridico import DictamenJuridicoForm, PersonaIncumplidaForm, PredioSancionadoForm
from ..models import PersonaIncumplida, PredioSancionado
from .comun import expediente_visible, mensajes_error


@login_required
def dictaminar(request, folio):
    exp = expediente_visible(request, folio)
    destino = reverse("recepcion:expediente", args=[folio]) + "?pestana=dictamenes"
    if request.user.tipo_unidad != TipoUnidad.JURIDICA:
        raise PermissionDenied("El dictamen jurídico lo emite la Unidad Jurídica.")
    if hasattr(exp, "dictamen_juridico") or exp.estado.clave != "validada":
        messages.info(request, "No hay dictamen jurídico pendiente para este expediente.")
        return redirect(destino)
    cotejo = juridico.cotejar(exp)
    legales = juridico.documentos_legales(exp)
    form = DictamenJuridicoForm(request.POST or None, tipos_documento=juridico.tipos_documento_propiedad(exp), initial={
        "resultado": "no_procedente" if cotejo else "procedente", "titular_documento": exp.solicitante.nombre,
        "titular_coincide": "si", "sin_conflicto": "si"})
    marcas = {}
    if request.method == "POST":
        for r in legales:
            valor = request.POST.get(f"doc_{r.requisito.clave}")
            marcas[r.requisito.clave] = {"valido": None if valor not in ("si", "no") else valor == "si",
                                         "observacion": request.POST.get(f"obs_{r.requisito.clave}", "")}
    if request.method == "POST" and form.is_valid():
        try:
            d = juridico.dictaminar(request.user, exp, form.cleaned_data["resultado"], form.cleaned_data["motivo"],
                                    propiedad=form.propiedad(), documentacion=marcas, exigir_revision=True)
        except (ValidationError, PermissionDenied) as e:
            for m in mensajes_error(e):
                messages.error(request, m)
        else:
            messages.success(request, f"Dictamen jurídico {d.get_resultado_display().lower()} registrado; se expidió el "
                                      f"documento {d.folio} y quedó adjunto al expediente.")
            return redirect(destino)
    filas = [{"r": r, "marca": marcas.get(r.requisito.clave, {})} for r in legales]
    return render(request, "dictamen/juridico/dictaminar.html", {
        "exp": exp, "form": form, "cotejo": cotejo, "filas_legales": filas,
        "superficie_a_acreditar": juridico.superficie_a_acreditar(exp),
        "tipos_documento": juridico.tipos_documento_propiedad(exp),
        "requisitos_propiedad": set(juridico.datos_dictamen()["propiedad"]["requisitos"].get(exp.programa.clave, [])),
    })


@login_required
def incumplidas(request):
    tipo = request.user.tipo_unidad
    if tipo not in (TipoUnidad.JURIDICA, TipoUnidad.DIRECCION, TipoUnidad.SECRETARIA_COMITE) and not request.user.is_superuser:
        raise PermissionDenied("Catálogo de la Unidad Jurídica.")
    puede_editar = tipo == TipoUnidad.JURIDICA
    form_persona = PersonaIncumplidaForm(prefix="persona")
    form_predio = PredioSancionadoForm(prefix="predio")
    if request.method == "POST":
        if not puede_editar:
            raise PermissionDenied("Solo la Unidad Jurídica edita el catálogo.")
        try:
            if request.POST.get("catalogo") == "persona":
                form_persona = PersonaIncumplidaForm(request.POST, prefix="persona")
                if form_persona.is_valid():
                    juridico.registrar_incumplida(request.user, **form_persona.cleaned_data)
                    messages.success(request, "Persona inscrita en el Listado de Personas Beneficiarias Incumplidas.")
                    return redirect("dictamen:incumplidas")
            else:
                form_predio = PredioSancionadoForm(request.POST, prefix="predio")
                if form_predio.is_valid():
                    datos = dict(form_predio.cleaned_data)
                    folio = datos.pop("folio_predio", "").strip()
                    datos["predio"] = Predio.objects.filter(folio__iexact=folio).first() if folio else None
                    juridico.registrar_predio_sancionado(request.user, **datos)
                    messages.success(request, "Predio registrado con procedimiento o sanción.")
                    return redirect("dictamen:incumplidas")
        except (ValidationError, PermissionDenied) as e:
            for m in mensajes_error(e):
                messages.error(request, m)
    return render(request, "dictamen/juridico/incumplidas.html", {
        "personas": PersonaIncumplida.objects.all(), "predios": PredioSancionado.objects.select_related("predio", "municipio"),
        "form_persona": form_persona, "form_predio": form_predio, "puede_editar": puede_editar,
        "historial": PersonaIncumplida.history.select_related("history_user").order_by("-history_date")[:20],
    })


@login_required
@require_POST
def baja(request, catalogo, pk):
    modelo = PersonaIncumplida if catalogo == "persona" else PredioSancionado
    registro = get_object_or_404(modelo, pk=pk)
    try:
        juridico.dar_de_baja(request.user, registro, request.POST.get("motivo", ""))
    except (ValidationError, PermissionDenied) as e:
        for m in mensajes_error(e):
            messages.error(request, m)
    else:
        messages.success(request, f"«{registro}» dado de baja; queda en el historial.")
    return redirect("dictamen:incumplidas")
