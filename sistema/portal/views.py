"""Pantallas del portal de personas beneficiarias: entrada propia (separada de la del personal), primer acceso con el
código del acuse, «Mis expedientes», detalle de un expediente propio y consulta sin cuenta con folio + código."""
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from nucleo import montos, plazos
from nucleo.models import Acuse

from . import cuentas

SESION_CONSULTA = "portal_consulta"


def _expediente_permitido(request, folio):
    """El expediente si es de la cuenta externa o si se abrió con folio + código en esta sesión; si no, 404."""
    if cuentas.es_externo(request.user):
        exp = cuentas.expedientes_de(request.user).filter(folio=folio).first()
    else:
        exp = None
        if request.session.get(SESION_CONSULTA) == folio:
            from nucleo.models import Expediente
            exp = Expediente.objects.filter(folio=folio).first()
    if exp is None:
        raise Http404("No existe el expediente o no es suyo.")
    return exp


def inicio(request):
    if not cuentas.es_externo(request.user):
        return redirect("portal:entrar")
    return render(request, "portal/inicio.html", {"expedientes": cuentas.expedientes_de(request.user)})


def entrar(request):
    error = ""
    if request.method == "POST":
        curp = request.POST.get("curp", "").strip().upper()
        u = authenticate(request, username=curp, password=request.POST.get("contrasena", ""))
        if u is not None and hasattr(u, "cuenta_externa"):
            login(request, u)
            return redirect("portal:inicio")
        error = "La CURP o la contraseña no son correctas (el personal de PROBOSQUE entra por su propia pantalla)."
    return render(request, "portal/entrar.html", {"error": error})


def primer_acceso(request):
    error = ""
    if request.method == "POST":
        if request.POST.get("contrasena") != request.POST.get("confirmacion"):
            error = "Las dos contraseñas no coinciden."
        else:
            try:
                u = cuentas.primer_acceso(request.POST.get("curp"), request.POST.get("codigo"), request.POST.get("contrasena", ""))
            except ValidationError as e:
                error = " ".join(e.messages)
            else:
                login(request, u, backend="django.contrib.auth.backends.ModelBackend")
                messages.success(request, "Su cuenta quedó activa. La próxima vez entre con su CURP y su contraseña.")
                return redirect("portal:inicio")
    return render(request, "portal/primer_acceso.html", {"error": error})


def consulta(request):
    error = ""
    if request.method == "POST":
        exp = cuentas.consultar(request.POST.get("folio"), request.POST.get("codigo"))
        if exp is None:
            error = "El folio o el código no coinciden."
        else:
            request.session[SESION_CONSULTA] = exp.folio
            return redirect("portal:expediente", exp.folio)
    return render(request, "portal/consulta.html", {"error": error})


def expediente(request, folio):
    exp = _expediente_permitido(request, folio)
    venc = [v for v in plazos.vencimientos(exp).values() if v is not None and v.tiene_fecha]
    return render(request, "portal/expediente.html", {
        "exp": exp, "monto": montos.monto_si_aprobado(exp), "vencimientos": venc,
        "acuses": exp.acuses.exclude(tipo="alta_portal").order_by("fecha_hora"),
        "notificaciones": exp.notificaciones.filter(notificada_en__isnull=False).order_by("notificada_en"),
        "con_cuenta": cuentas.es_externo(request.user),
    })


def acuse(request, folio, acuse_folio):
    exp = _expediente_permitido(request, folio)
    a = Acuse.objects.filter(expediente=exp, folio=acuse_folio).exclude(tipo="alta_portal").first()
    if a is None or not a.archivo:
        raise Http404("No existe el acuse.")
    return FileResponse(a.archivo.open("rb"), content_type="application/pdf", filename=f"{a.folio}.pdf")


@require_POST
def salir(request):
    request.session.pop(SESION_CONSULTA, None)
    logout(request)
    return redirect("portal:entrar")
