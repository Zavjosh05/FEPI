"""HU-2.4 · Sesiones de seguimiento: acuerdos tipificados con los expedientes a los que aplican y el área
que debe cumplirlos; instrucción de pago por ministración (PSAHEM) y validación de reportes por periodo (PEG).

Punto de conexión con los módulos M3–M6: ``RECEPTORES`` (tipo de acuerdo -> funciones). Por ahora
ningún módulo se registra, así que cumplir un acuerdo solo deja la constancia; cuando existan pagos
(M5) o seguimiento (M6), sus apps agregan aquí la función que ejecuta el acuerdo.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from nucleo.models import Evento, TipoUnidad, Unidad

from .comun import datos_dictamen, exigir_unidad
from .models import Acuerdo, EstadoAcuerdo, EstadoSesion, TipoSesion

RECEPTORES = {}  # {"instruccion_pago": [funcion(acuerdo)], ...}


def tipos_acuerdo(programa=None):
    tipos = datos_dictamen()["tipos_acuerdo"]
    if programa is None:
        return tipos
    return [t for t in tipos if not t.get("programas") or programa.clave in t["programas"]]


def tipo_acuerdo(clave):
    return next((t for t in datos_dictamen()["tipos_acuerdo"] if t["clave"] == clave), None)


def unidad_sugerida(clave_tipo):
    t = tipo_acuerdo(clave_tipo)
    return Unidad.objects.filter(clave=t.get("unidad")).first() if t else None


def registrar_acuerdo(usuario, sesion, tipo, descripcion, expedientes, unidad_responsable=None, ministracion=None,
                      periodo=""):
    exigir_unidad(usuario, TipoUnidad.SECRETARIA_COMITE)
    if sesion.tipo != TipoSesion.SEGUIMIENTO:
        raise ValidationError("Los acuerdos de seguimiento se toman en una sesión de seguimiento.")
    if not sesion.convocatoria_enviada:
        raise ValidationError("Primero se envía la convocatoria de la sesión.")
    if sesion.estado == EstadoSesion.CELEBRADA:
        raise ValidationError("La sesión ya se cerró.")
    definicion = tipo_acuerdo(tipo)
    if definicion is None:
        raise ValidationError("Tipo de acuerdo no reconocido.")
    programa = sesion.ejercicio.programa
    if definicion.get("programas") and programa.clave not in definicion["programas"]:
        raise ValidationError(f"«{definicion['nombre']}» no aplica al programa {programa.clave}.")
    expedientes = list(expedientes)
    if not expedientes:
        raise ValidationError("Indique a qué expedientes aplica el acuerdo.")
    if any(e.ejercicio_id != sesion.ejercicio_id for e in expedientes):
        raise ValidationError("Todos los expedientes deben ser del programa y ejercicio de la sesión.")
    unidad_responsable = unidad_responsable or unidad_sugerida(tipo)
    if unidad_responsable is None:
        raise ValidationError("Indique el área que debe cumplir el acuerdo.")
    if definicion.get("pide") == "ministracion":
        if not ministracion:
            raise ValidationError("La instrucción de pago se da por ministración: indique cuál.")
        numeros = set(sesion.ejercicio.ministraciones.values_list("numero", flat=True))
        if numeros and int(ministracion) not in numeros:
            raise ValidationError(f"El programa no tiene la ministración {ministracion}.")
    if definicion.get("pide") == "periodo" and not (periodo or "").strip():
        raise ValidationError("La validación de reportes se da por periodo: indique cuál.")
    if not (descripcion or "").strip():
        raise ValidationError("Escriba el texto del acuerdo.")
    with transaction.atomic():
        n = sesion.acuerdos.count() + 1
        acuerdo = Acuerdo.objects.create(
            sesion=sesion, numero=f"{sesion.numero}/{n:03d}", tipo=tipo, descripcion=descripcion.strip(),
            unidad_responsable=unidad_responsable, ministracion=ministracion or None, periodo=(periodo or "").strip(),
        )
        acuerdo.expedientes.set(expedientes)
        for e in expedientes:
            Evento.registrar(e, usuario, "acuerdo_comite",
                             f"Acuerdo {acuerdo.numero} ({definicion['nombre']}): {acuerdo.descripcion}. "
                             f"Debe cumplirlo: {unidad_responsable.nombre}.", datos={"acuerdo": acuerdo.pk})
    return acuerdo


def acuerdos_pendientes(unidad):
    return (Acuerdo.objects.filter(unidad_responsable=unidad, estado=EstadoAcuerdo.PENDIENTE)
            .select_related("sesion__ejercicio__programa").prefetch_related("expedientes"))


def cumplir(usuario, acuerdo, observaciones=""):
    """El área responsable marca el acuerdo como cumplido; se llama a los módulos registrados en RECEPTORES."""
    if usuario.unidad_id != acuerdo.unidad_responsable_id:
        raise PermissionDenied("Solo el área responsable marca el acuerdo como cumplido.")
    if acuerdo.estado == EstadoAcuerdo.CUMPLIDO:
        raise ValidationError("El acuerdo ya está cumplido.")
    with transaction.atomic():
        acuerdo.estado = EstadoAcuerdo.CUMPLIDO
        acuerdo.cumplido_en = timezone.now()
        acuerdo.cumplido_por = usuario
        acuerdo.observaciones_cumplimiento = observaciones
        acuerdo.save()
        for e in acuerdo.expedientes.all():
            Evento.registrar(e, usuario, "acuerdo_cumplido", f"Acuerdo {acuerdo.numero} cumplido. {observaciones}".strip(),
                             datos={"acuerdo": acuerdo.pk})
        for receptor in RECEPTORES.get(acuerdo.tipo, []):
            receptor(acuerdo)
    return acuerdo


def cerrar_sesion(usuario, sesion, observaciones="", momento=None):
    """Cierra la sesión de seguimiento; no antes de su fecha y hora (`momento`: solo servicios, pruebas y demo)."""
    exigir_unidad(usuario, TipoUnidad.SECRETARIA_COMITE)
    ahora = momento or timezone.now()
    if ahora < sesion.fecha_hora:
        raise ValidationError(f"La sesión no se cierra antes de celebrarse: está convocada para el "
                              f"{timezone.localtime(sesion.fecha_hora):%d/%m/%Y a las %H:%M} h.")
    if not sesion.acuerdos.exists():
        raise ValidationError("La sesión no tiene acuerdos.")
    sesion.estado = EstadoSesion.CELEBRADA
    sesion.acta_fecha = ahora
    sesion.observaciones_acta = observaciones
    sesion.save()
    return sesion


# ----------------------------------------------------------------------------- criterio 2
def ministraciones_sin_instruccion(expediente):
    """PSAHEM: ministraciones del programa que aún no tienen instrucción de pago a la Fiduciaria."""
    numeros = sorted(set(expediente.ejercicio.ministraciones.values_list("numero", flat=True)))
    con_instruccion = set(Acuerdo.objects.filter(tipo="instruccion_pago", expedientes=expediente)
                          .values_list("ministracion", flat=True))
    return [n for n in numeros if n not in con_instruccion]


def periodos_sin_validacion(ejercicio):
    """PEG: periodos de reportes (datos del ejercicio) que aún no tienen validación del Comité."""
    periodos = (ejercicio.datos or {}).get("periodos_reportes", [])
    validados = set(Acuerdo.objects.filter(tipo="validacion_reportes", sesion__ejercicio=ejercicio)
                    .values_list("periodo", flat=True))
    return [p for p in periodos if p not in validados]
