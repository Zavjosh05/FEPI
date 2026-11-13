"""Lo que comparten las historias del módulo M2: datos propios, permisos y el paso a «dictaminada»."""
from functools import lru_cache

from django.conf import settings
from django.core.exceptions import PermissionDenied

from nucleo.catalogos import leer_json
from nucleo.models import Evento, TipoUnidad, puede_ver_expediente


def datos_dictamen():
    return _datos(str(settings.DATOS_DIR / "dictamen.json"))


@lru_cache(maxsize=4)
def _datos(ruta):
    return leer_json(ruta)


def exigir_unidad(usuario, *tipos):
    if usuario.tipo_unidad not in tipos:
        nombres = ", ".join(TipoUnidad(t).label for t in tipos)
        raise PermissionDenied(f"Esta acción le corresponde a: {nombres}.")


def exigir_acceso(usuario, expediente):
    if not puede_ver_expediente(usuario, expediente):
        raise PermissionDenied("El expediente no está entre los que atiende su unidad.")


def exigir_programa(usuario, expediente):
    """La Dirección solo dictamina los programas de los que es Instancia Ejecutora."""
    if usuario.tipo_unidad == TipoUnidad.DIRECCION and not usuario.unidad.programas.filter(
            pk=expediente.programa.pk).exists():
        raise PermissionDenied("Su Dirección no es Instancia Ejecutora de este programa.")


def resultado_combinado(expediente):
    """('factible' | 'no_factible' | 'pendiente', texto) con los dos dictámenes."""
    tecnico = getattr(expediente, "dictamen_tecnico", None)
    juridico = getattr(expediente, "dictamen_juridico", None)
    if (tecnico and tecnico.resultado == "no_factible") or (juridico and juridico.resultado == "no_procedente"):
        motivos = []
        if tecnico and tecnico.resultado == "no_factible":
            motivos.append(f"Técnico: {tecnico.motivo}")
        if juridico and juridico.resultado == "no_procedente":
            motivos.append(f"Jurídico: {juridico.motivo}")
        return "no_factible", " · ".join(motivos)
    if tecnico and juridico:
        return "factible", "Técnicamente factible y jurídicamente procedente"
    return "pendiente", "Falta el dictamen " + ("jurídico" if tecnico else "técnico" if juridico else "técnico y jurídico")


def completar_si_ya_hay_dos(expediente, usuario):
    """Cuando existen los dos dictámenes, el expediente queda «dictaminada» (bandeja de la Secretaría Técnica)."""
    expediente.refresh_from_db()
    tiene_tecnico = hasattr(expediente, "dictamen_tecnico")
    tiene_juridico = hasattr(expediente, "dictamen_juridico")
    if tiene_tecnico and tiene_juridico and expediente.estado.clave == "validada":
        resultado, texto = resultado_combinado(expediente)
        expediente.cambiar_estado(
            "dictaminada", usuario, tipo_evento="dictaminada",
            descripcion=f"Dictámenes técnico y jurídico completos ({texto}); pasa a la Secretaría Técnica del Comité.",
            datos={"resultado": resultado},
        )
        return True
    return False


def registrar_evento(expediente, usuario, tipo, descripcion, **campos):
    return Evento.registrar(expediente, usuario, tipo, descripcion, **campos)
