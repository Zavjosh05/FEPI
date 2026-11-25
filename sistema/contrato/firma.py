"""HU-3.3 · Firma del contrato.

- ``registrar_firma``: la Delegación registra el contrato firmado (fecha y hora, quién firma, el archivo digitalizado y
  la **verificación de firmas y sello** por tipo de persona, que son datos en ``datos/contrato.json``). En MFS pide además
  el contrato de servicios técnicos con el RFN y la carta compromiso; en PEG, la credencial entregada (también datos).
  Deja acuse, el hito ``firma_contrato`` y el estado ``contratada``, y dice si la firma fue en la fecha programada.
- Dos fechas (R-03), ya configuradas por programa en ``nucleo.plazos``: ``firma_programada`` y ``firma_liberacion``. Una
  firma posterior a la programada pero anterior a la de liberación es válida y se marca «fuera de la fecha programada».
- ``revisar_firmas`` (lo corre ``manage.py revisar_plazos``): señala los contratos cuyo vencimiento para liberar el recurso
  ya pasó sin firma (estado ``sin_firma_en_plazo``, bitácora y aviso en la bandeja de la Dirección, decisión P-08).
  ``liberar_recurso`` **no es automático**: lo confirma una persona del área responsable con un motivo.
"""
import hashlib
from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from dictamen.comun import exigir_acceso, exigir_programa, exigir_unidad
from dictamen.seguimiento import exigir_vigente
from nucleo import dias_habiles, extensiones, plazos
from nucleo.acuses import emitir_acuse
from nucleo.catalogos import leer_json
from nucleo.models import Expediente, TipoUnidad, expedientes_visibles

from .models import ElementoFormalizacion, FirmaContrato, Firmante, SinFirma
from nucleo.trazabilidad import registra_usuario

ESTADOS_SIN_FIRMA = ("publicada", "notificada", "contrato_elaborado", "contrato_en_delegacion")
EXTENSIONES = (".pdf", ".jpg", ".jpeg", ".png")


# ----------------------------------------------------------------------------- datos por programa
@lru_cache(maxsize=2)
def _datos(ruta):
    return leer_json(ruta)


def datos_contrato():
    return _datos(str(settings.DATOS_DIR / "contrato.json"))


def puntos_de_verificacion(expediente):
    """Puntos de verificación de firmas y sello según el tipo de persona (datos, no código)."""
    cfg = datos_contrato()["verificacion_firmas"]
    clave = expediente.tipo_persona.clave
    clave = cfg.get("equivalencias", {}).get(clave, clave)
    return list(cfg["por_tipo_persona"].get(clave) or cfg["por_tipo_persona"][cfg["por_omision"]])


def formalizacion_propia(expediente):
    """``{"fundamento", "elementos": [...]}`` que el programa pide además del contrato (MFS y PEG), o vacío."""
    return datos_contrato()["formalizacion_propia"].get(expediente.programa.clave) or {"fundamento": "", "elementos": []}


def fechas_de_firma(expediente):
    """(fecha programada de firma, vencimiento para liberar el recurso), cada uno ``Vencimiento`` o None."""
    return (plazos.vencimiento(expediente, "firma_programada"), plazos.vencimiento(expediente, "firma_liberacion"))


def dias_que_faltan(vencimiento, hoy=None):
    """Días hábiles que faltan para la fecha (negativo si ya pasó); None si no hay fecha."""
    if vencimiento is None or not vencimiento.tiene_fecha:
        return None
    hoy = hoy or timezone.localdate()
    if hoy > vencimiento.vencimiento:
        return -dias_habiles.dias_habiles_entre(vencimiento.vencimiento, hoy)
    return dias_habiles.dias_habiles_entre(hoy, vencimiento.vencimiento)


# ----------------------------------------------------------------------------- consultas
def por_firmar(usuario):
    return expedientes_visibles(usuario).filter(estado__clave="contrato_en_delegacion")


def firmados(usuario):
    return FirmaContrato.objects.filter(expediente__in=expedientes_visibles(usuario)).select_related(
        "expediente__predio__municipio", "expediente__ejercicio__programa", "expediente__solicitante", "contrato")


def sin_firma(usuario, liberados=False):
    qs = SinFirma.objects.filter(expediente__in=expedientes_visibles(usuario)).select_related(
        "expediente__predio__municipio", "expediente__ejercicio__programa", "expediente__solicitante")
    if not liberados:   # la que el Comité ya dio de baja (HU-2.4) no queda por liberar
        return qs.filter(liberado_en__isnull=True).exclude(expediente__estado__clave="baja")
    return qs.filter(liberado_en__isnull=False)


# ----------------------------------------------------------------------------- firma
def _validar_archivo(archivo, nombre):
    if archivo is None or not getattr(archivo, "name", ""):
        raise ValidationError(f"Falta el archivo: {nombre}.")
    if not archivo.name.lower().endswith(EXTENSIONES):
        raise ValidationError(f"«{nombre}» debe ser PDF, JPG o PNG.")
    if getattr(archivo, "size", 1) == 0:
        raise ValidationError(f"«{nombre}» está vacío.")


def _contenido(archivo):
    archivo.seek(0)
    datos = archivo.read()
    archivo.seek(0)
    return datos


def _nombre(archivo, base):
    extension = "." + archivo.name.rsplit(".", 1)[-1].lower() if "." in archivo.name else ""
    return f"{base}{extension}"


@registra_usuario
def registrar_firma(usuario, expediente, firmado_en, firmante, firmante_nombre, archivo, verificacion,
                    elementos=None, observaciones="", momento=None):
    """La Delegación registra el contrato firmado.

    ``verificacion``: claves de los puntos verificados (deben ser todos). ``elementos``: ``{clave: {"archivo", "dato"}}``
    de la formalización propia del programa (MFS, PEG)."""
    exigir_unidad(usuario, TipoUnidad.DELEGACION)
    exigir_acceso(usuario, expediente)
    expediente.refresh_from_db()
    estado = expediente.estado.clave
    if estado == "sin_firma_en_plazo":
        raise ValidationError("El contrato ya está señalado como «sin firma en plazo»: la firma ya no se puede registrar. "
                              "El área responsable debe confirmar la liberación del recurso.")
    if estado == "recurso_liberado":
        raise ValidationError("El recurso de esta solicitud ya se liberó: la firma ya no se puede registrar.")
    exigir_vigente(expediente, "la firma del contrato ya no se puede registrar")
    if estado != "contrato_en_delegacion":
        raise ValidationError(f"El expediente está «{expediente.estado}»: solo se registra la firma de un contrato que "
                              "ya llegó a la Delegación.")
    contrato = getattr(expediente, "contrato", None)
    if contrato is None or not contrato.enviado:
        raise ValidationError("El contrato todavía no se envía a la Delegación.")
    ahora = momento or timezone.now()
    if firmado_en is None:
        firmado_en = ahora
    if firmado_en > ahora:
        raise ValidationError("La fecha y la hora de la firma no pueden ser futuras.")
    if firmado_en < contrato.enviado_en:
        raise ValidationError("La firma no puede ser anterior al envío del contrato a la Delegación "
                              f"({timezone.localtime(contrato.enviado_en):%d/%m/%Y %H:%M} h).")
    if firmante not in Firmante.values:
        raise ValidationError("Indique quién firma: la persona beneficiaria o su representante.")
    if not (firmante_nombre or "").strip():
        raise ValidationError("Indique el nombre de quien firma.")
    _validar_archivo(archivo, "el contrato firmado digitalizado")
    # verificación de firmas y sello
    puntos = puntos_de_verificacion(expediente)
    marcados = set(verificacion or ())
    faltan = [p["texto"] for p in puntos if p["clave"] not in marcados]
    if faltan:
        raise ValidationError("Falta verificar: " + "; ".join(faltan) + ". El contrato no se recibe incompleto.")
    # formalización propia del programa
    pedidos = formalizacion_propia(expediente)["elementos"]
    recibidos = elementos or {}
    for e in pedidos:
        r = recibidos.get(e["clave"]) or {}
        _validar_archivo(r.get("archivo"), e["nombre"])
        if e.get("dato") and not (r.get("dato") or "").strip():
            raise ValidationError(f"Falta el dato «{e['dato']['etiqueta']}» de {e['nombre']}.")
    # las dos fechas (R-03)
    programada, liberacion = fechas_de_firma(expediente)
    dia_firma = timezone.localtime(firmado_en).date()
    if liberacion is not None and liberacion.tiene_fecha and dia_firma > liberacion.vencimiento:
        raise ValidationError(
            f"La firma es del {dia_firma:%d/%m/%Y} y el vencimiento para liberar el recurso fue el "
            f"{liberacion.vencimiento:%d/%m/%Y}: el contrato queda señalado como «sin firma en plazo».")
    en_programada = not (programada is not None and programada.tiene_fecha and dia_firma > programada.vencimiento)
    contenido = _contenido(archivo)
    with transaction.atomic():
        firma = FirmaContrato.objects.create(
            contrato=contrato, expediente=expediente, firmado_en=firmado_en, firmante=firmante,
            firmante_nombre=firmante_nombre.strip(), huella=hashlib.sha256(contenido).hexdigest(),
            verificacion=[{"clave": p["clave"], "texto": p["texto"], "cumple": True} for p in puntos],
            fecha_programada=programada.vencimiento if programada is not None else None,
            fecha_liberacion=liberacion.vencimiento if liberacion is not None else None,
            en_fecha_programada=en_programada, dentro_de_plazo=True, observaciones=(observaciones or "").strip(),
            registrada_por=usuario, registrada_en=ahora)
        firma.archivo.save(_nombre(archivo, f"{contrato.folio}_firmado"), ContentFile(contenido), save=True)
        for e in pedidos:
            r = recibidos[e["clave"]]
            el = ElementoFormalizacion(firma=firma, clave=e["clave"], nombre=e["nombre"],
                                       dato_etiqueta=(e.get("dato") or {}).get("etiqueta", ""),
                                       dato=(r.get("dato") or "").strip())
            el.archivo.save(_nombre(r["archivo"], e["clave"]), ContentFile(_contenido(r["archivo"])), save=True)
        situacion = ("Dentro del plazo, en la fecha programada" if en_programada
                     else "Dentro del plazo, fuera de la fecha programada")
        renglones = [
            ("Contrato", contrato.folio), ("Solicitud", expediente.folio),
            ("Persona beneficiaria", expediente.solicitante.nombre),
            ("Firma", f"{Firmante(firmante).label}: {firma.firmante_nombre}"),
            ("Fecha y hora de la firma", f"{timezone.localtime(firmado_en):%d/%m/%Y %H:%M:%S} h"),
            ("Fecha programada de firma",
             f"{firma.fecha_programada:%d/%m/%Y}" if firma.fecha_programada else "Sin fecha en las reglas"),
            ("Vencimiento para liberar el recurso",
             f"{firma.fecha_liberacion:%d/%m/%Y}" if firma.fecha_liberacion else "Sin fecha en las reglas"),
            ("Situación", situacion), ("Huella del archivo (SHA-256)", firma.huella),
            ("Verificación de firmas y sello", f"{len(puntos)} de {len(puntos)} puntos verificados"),
        ] + [(e["nombre"], (recibidos[e["clave"]].get("dato") or "").strip() or "recibido")
             for e in pedidos] + [("Registra", usuario.unidad.nombre)]
        detalle = [{"clave": p["clave"], "texto": p["texto"], "estado": "Verificado"} for p in puntos]
        firma.acuse = emitir_acuse(
            expediente, "firma_contrato", f"Firma del contrato {contrato.folio}", usuario, renglones,
            destinatario=expediente.solicitante.nombre, detalle=detalle,
            encabezado_detalle=["Punto", "Verificación", "Estado"])
        firma.save(update_fields=["acuse"])
        plazos.registrar_hito(expediente, "firma_contrato", usuario, firmado_en, referencia=contrato.folio,
                              datos={"firma": firma.pk, "en_fecha_programada": en_programada})
        expediente.cambiar_estado(
            "contratada", usuario, tipo_evento="contrato_firmado", acuse=firma.acuse,
            descripcion=f"Contrato {contrato.folio} firmado el {timezone.localtime(firmado_en):%d/%m/%Y %H:%M} h "
                        f"({situacion.lower()})", datos={"firma": firma.pk})
        for gancho in extensiones.AL_FIRMAR:
            gancho(firma)
    return firma


# ----------------------------------------------------------------------------- sin firma en plazo
def senalar_sin_firma(expediente, hoy=None, momento=None):
    """Señala el contrato como sin firma en plazo (lo hace el sistema al vencer el plazo; idempotente)."""
    expediente.refresh_from_db()
    if expediente.estado.clave not in ESTADOS_SIN_FIRMA or SinFirma.objects.filter(expediente=expediente).exists():
        return None
    liberacion = plazos.vencimiento(expediente, "firma_liberacion")
    if liberacion is None or not liberacion.tiene_fecha:
        return None
    hoy = hoy or timezone.localdate()
    if hoy <= liberacion.vencimiento:
        return None
    motivo = (f"Venció el {liberacion.vencimiento:%d/%m/%Y} el plazo para firmar el contrato "
              f"({liberacion.texto_plazo} desde {liberacion.nombre_evento}) sin que se registrara la firma.")
    with transaction.atomic():
        senal = SinFirma.objects.create(expediente=expediente, vencio_el=liberacion.vencimiento, motivo=motivo,
                                        senalado_en=momento or timezone.now())
        expediente.cambiar_estado(
            "sin_firma_en_plazo", None, motivo=motivo, tipo_evento="sin_firma_en_plazo", por_sistema=True,
            descripcion="Contrato sin firma al vencer el plazo: queda señalado para liberar el recurso (la Dirección "
                        "debe confirmar la liberación).", datos={"vencio_el": liberacion.vencimiento.isoformat()})
    return senal


def revisar_firmas(hoy):
    """``manage.py revisar_plazos``: señala los contratos sin firma cuyo vencimiento para liberar el recurso ya pasó."""
    senalados = 0
    for exp in Expediente.objects.filter(estado__clave__in=ESTADOS_SIN_FIRMA, sin_firma__isnull=True).select_related(
            "estado", "ejercicio__programa"):
        if senalar_sin_firma(exp, hoy) is not None:
            senalados += 1
    return senalados


@registra_usuario
def liberar_recurso(usuario, expediente, motivo, momento=None):
    """El área responsable confirma la liberación del recurso de un contrato sin firma en plazo (con un motivo)."""
    exigir_unidad(usuario, TipoUnidad.DIRECCION)
    exigir_programa(usuario, expediente)
    exigir_acceso(usuario, expediente)
    expediente.refresh_from_db()
    senal = SinFirma.objects.filter(expediente=expediente).first()
    if expediente.estado.clave != "sin_firma_en_plazo" or senal is None:
        raise ValidationError("Solo se libera el recurso de un contrato señalado como «sin firma en plazo».")
    if not (motivo or "").strip():
        raise ValidationError("Indique el motivo de la liberación del recurso.")
    ahora = momento or timezone.now()
    with transaction.atomic():
        acuse = emitir_acuse(
            expediente, "liberacion_recurso", f"Liberación del recurso de {expediente.folio}", usuario,
            [("Solicitud", expediente.folio), ("Persona beneficiaria", expediente.solicitante.nombre),
             ("Vencimiento que pasó", f"{senal.vencio_el:%d/%m/%Y}" if senal.vencio_el else "—"),
             ("Motivo de la liberación", motivo.strip()),
             ("Fecha y hora", f"{timezone.localtime(ahora):%d/%m/%Y %H:%M:%S} h"), ("Confirma", usuario.unidad.nombre),
             ("Reasignación", "El recurso queda liberado para reasignarse a la lista de espera por acuerdo del Comité "
                              "(HU-2.4).")],
            destinatario=expediente.solicitante.nombre)
        senal.liberado_por, senal.liberado_en, senal.motivo_liberacion, senal.acuse_liberacion = (
            usuario, ahora, motivo.strip(), acuse)
        senal.save(update_fields=["liberado_por", "liberado_en", "motivo_liberacion", "acuse_liberacion"])
        expediente.cambiar_estado("recurso_liberado", usuario, motivo=motivo.strip(), tipo_evento="recurso_liberado",
                                  acuse=acuse, descripcion="Recurso liberado por falta de firma del contrato en plazo.")
        for gancho in extensiones.AL_LIBERAR_RECURSO:
            gancho(expediente, usuario)
    return senal
