"""Un usuario externo (cuenta del portal) solo puede usar el portal: cualquier otra pantalla del sistema lo regresa a
«Mis expedientes» (o responde 403 si no es una consulta GET). Las páginas públicas de resultados y del padrón siguen abiertas."""
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

PERMITIDAS = ("/portal/", "/static/", "/contrato/resultados/", "/padron/", "/salud/")


class SoloPortalMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if usuario is not None and usuario.is_authenticated and hasattr(usuario, "cuenta_externa") \
                and not request.path.startswith(PERMITIDAS):
            if request.method in ("GET", "HEAD"):
                return redirect("portal:inicio")
            return HttpResponseForbidden("Las personas beneficiarias solo usan el portal.")
        return self.get_response(request)
