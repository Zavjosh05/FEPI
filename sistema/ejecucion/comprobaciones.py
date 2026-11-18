"""HU-4.1 · Envío de comprobaciones.

- ``tipos_de_envio``: lo que pide el programa (``datos/ejecucion.json``: avisos de término, de caso fortuito y de cambio de
  polígono, Informe Final, Bitácora o solicitud de auditoría de MFS, reportes mensuales y acuses de depósito de PEG), con el
  fundamento de las ROP; en MFS, solo los del régimen de pago del expediente (estudio técnico o certificación FSC).
- ``registrar_envio``: **un solo servicio para los dos medios**. La persona beneficiaria (o el Guardabosque) lo envía desde el
  portal con su cuenta (solo a sus expedientes, ``portal.models.AccesoExpediente``) o la Delegación del expediente registra la
  misma entrega recibida en ventanilla, con quién la entregó y quién la recibió. Cada envío deja la fecha y la hora, el acuse
  en PDF, el renglón de la bitácora, el hito que corresponda (``conclusion_actividades``, ``siniestro`` con la fecha del
  siniestro, ``informe_final``, ``entrega_entregable``, ``reporte_mensual``…) y el cambio de estado que pide el flujo
  (``comprobacion_enviada`` o ``caso_fortuito``). Si el tipo tiene plazo (``nucleo.plazos``) queda dicho si llegó en plazo;
  fuera de plazo se registra igual y queda señalado.
- Si la primera comprobación que cambia el estado llega con el expediente aún en ``pagada``, ``cheque_entregado`` o
  ``planta_entregada``, el sistema registra antes el inicio de la ejecución (``en_ejecucion``, sin persona en la bitácora).
  Lo que llega por el portal cambia el estado como lo haría el sistema (``por_sistema``): la cuenta externa no tiene unidad.
- ``fuente_entregable``: soporte ``entregable`` de ``pagos.solicitudes.FUENTES`` (segunda ministración de MFS: la Bitácora en
  estudio técnico, la solicitud o el Plan de auditoría en FSC; ROP MFS 7.2, líneas 6871 y 6885).
- ``marcar_revisada``: la Delegación deja constancia de que revisó lo que llegó por el portal (panel de su bandeja).
"""
import hashlib
from datetime import date, datetime, time
from functools import lru_cache

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from nucleo import montos, plazos
from nucleo.acuses import emitir_acuse
from nucleo.catalogos import leer_json
from nucleo.models import Evento, TipoUnidad, Transicion, expedientes_visibles
from portal import cuentas

from .models import Comprobacion, MedioEnvio


# ----------------------------------------------------------------------------- datos
@lru_cache(maxsize=2)
def _datos(ruta):
    return leer_json(ruta)


def datos_ejecucion():
    return _datos(str(settings.DATOS_DIR / "ejecucion.json"))


def regimen(expediente):
    return montos.regimen_de_pago(expediente, montos.superficie_aprobada(expediente))


def tipos_de_envio(expediente):
    """Tipos que el programa del expediente admite: ``[{"clave", "nombre", "fundamento", ...}]``."""
    d = datos_ejecucion()
    r = regimen(expediente)
    lista = []
    for propio in d["programas"].get(expediente.programa.clave, {}).get("envios", []):
        t = {**d["tipos_envio"][propio["tipo"]], **propio, "clave": propio["tipo"]}
        if t.get("regimenes") and r not in t["regimenes"]:
            continue
        lista.append(t)
    return lista


def tipo_de_envio(expediente, clave):
    t = next((x for x in tipos_de_envio(expediente) if x["clave"] == clave), None)
    if t is None:
        raise ValidationError(f"{expediente.programa.nombre} no recibe «{clave}» como comprobación.")
    return t


def periodos(expediente):
    """PEG: periodos de los reportes (``Ejercicio.datos["periodos_reportes"]``)."""
    return [p for p in (expediente.ejercicio.datos or {}).get("periodos_reportes", []) if isinstance(p, dict)]


def puede_enviar(expediente):
    """(True, "") o (False, motivo): se comprueba desde la firma del contrato y mientras el apoyo siga vigente."""
    if getattr(expediente, "firma_contrato", None) is None:
        return False, "Las comprobaciones se envían una vez firmado el contrato."
    if expediente.estado.final or expediente.estado.clave in datos_ejecucion()["estados_sin_envios"]:
        return False, f"El expediente está «{expediente.estado}»: ya no recibe comprobaciones."
    return True, ""


# ----------------------------------------------------------------------------- consultas
def comprobaciones_visibles(usuario):
    return Comprobacion.objects.filter(expediente__in=expedientes_visibles(usuario)).select_related(
        "expediente__ejercicio__programa", "expediente__solicitante", "expediente__predio", "acuse", "enviada_por",
        "recibida_por")


def por_revisar(usuario):
    """Delegación: lo que llegó por el portal a sus expedientes y todavía no revisa."""
    if usuario.tipo_unidad != TipoUnidad.DELEGACION:
        return Comprobacion.objects.none()
    # Los reportes y los acuses de depósito de los Guardabosques se revisan con su resultado (HU-4.3, ``reportes.revisar``).
    tipos = sorted({t for c in datos_ejecucion()["reportes"]["programas"].values() for t in c["tipos_revisables"]})
    return comprobaciones_visibles(usuario).filter(medio=MedioEnvio.PORTAL, revisada_en__isnull=True).exclude(tipo__in=tipos)


def fuente_entregable(expediente, numero):
    """Soporte «entregable» de la segunda ministración de MFS (``pagos.solicitudes.FUENTES``)."""
    r = regimen(expediente)
    tipos = [t for t in tipos_de_envio(expediente) if r in t.get("entregable_de", [])]
    c = expediente.comprobaciones.filter(tipo__in=[t["clave"] for t in tipos]).order_by("enviada_en", "id").first()
    if c is None:
        nombres = " o ".join(t["nombre"][:1].lower() + t["nombre"][1:] for t in tipos) or "el entregable"
        return (False, f"Todavía no se entrega la {nombres} (envío de comprobaciones, HU-4.1); hasta entonces la ministración "
                       "no se puede solicitar.", "", "")
    medio = "por el portal" if c.por_portal else "en la Delegación"
    return (True, f"{c.nombre}: entregada {medio} el {timezone.localtime(c.enviada_en):%d/%m/%Y %H:%M} h.",
            c.acuse.folio if c.acuse else f"Comprobación {c.pk}", reverse("ejecucion:archivo", args=[c.pk]))


# ----------------------------------------------------------------------------- registro
def _medio(usuario, expediente):
    if cuentas.es_externo(usuario):
        if not cuentas.expedientes_de(usuario).filter(pk=expediente.pk).exists():
            raise PermissionDenied("El expediente no es suyo.")
        return MedioEnvio.PORTAL
    if usuario.tipo_unidad == TipoUnidad.DELEGACION and usuario.unidad_id == expediente.delegacion_id:
        return MedioEnvio.VENTANILLA
    raise PermissionDenied("La comprobación la envía la persona beneficiaria desde el portal o la registra la Delegación "
                           "del expediente cuando se entrega en persona.")


def _leer_archivo(archivo):
    if archivo is None or not getattr(archivo, "name", ""):
        return None, ""
    nombre = archivo.name.rsplit("/", 1)[-1]
    if not nombre.lower().endswith(tuple(datos_ejecucion()["extensiones_archivo"])):
        raise ValidationError("El documento debe ser PDF, JPG o PNG.")
    archivo.seek(0)
    contenido = archivo.read()
    if not contenido:
        raise ValidationError("El archivo está vacío.")
    return contenido, nombre


def _momento_de(fecha):
    return timezone.make_aware(datetime.combine(fecha, time(12, 0)))


def _fmt(valor):
    return f"{timezone.localtime(valor):%d/%m/%Y %H:%M:%S} h"


def registrar_envio(usuario, expediente, tipo, archivo=None, descripcion="", fecha_hecho=None, periodo="",
                    persona_entrega="", momento=None):
    """Registra el envío (portal) o la entrega (ventanilla) con su acuse. Devuelve la ``Comprobacion``."""
    medio = _medio(usuario, expediente)
    expediente.refresh_from_db()
    puede, motivo = puede_enviar(expediente)
    if not puede:
        raise ValidationError(motivo)
    t = tipo_de_envio(expediente, tipo)
    ahora = momento or timezone.now()
    hoy = timezone.localtime(ahora).date()
    if isinstance(fecha_hecho, str) and fecha_hecho:
        fecha_hecho = date.fromisoformat(fecha_hecho)
    if t.get("fecha_hecho"):
        if not fecha_hecho:
            raise ValidationError(f"Falta la fecha: {t['fecha_hecho'].lower()}.")
        if fecha_hecho > hoy:
            raise ValidationError("La fecha del hecho no puede ser posterior al envío.")
    else:
        fecha_hecho = None
    nombre_periodo = ""
    if t.get("pide_periodo"):
        disponibles = {p["clave"]: p for p in periodos(expediente)}
        if periodo not in disponibles:
            raise ValidationError("Elija el periodo que reporta.")
        if date.fromisoformat(disponibles[periodo]["inicio"]) > hoy:
            raise ValidationError("No se puede reportar un periodo que todavía no empieza.")
        nombre_periodo = disponibles[periodo].get("nombre", periodo)
        from . import reportes  # HU-4.3: un reporte devuelto para corregir se puede volver a enviar

        if t.get("un_envio_por_periodo") and reportes.hay_envio_vigente(expediente, tipo, periodo):
            raise ValidationError(f"Ya se entregó el {t['nombre'].lower()} de {nombre_periodo}.")
    else:
        periodo = ""
    contenido, nombre_archivo = _leer_archivo(archivo)
    if contenido is None and t.get("requiere_archivo"):
        raise ValidationError(f"Falta el documento de «{t['nombre']}».")
    portal = medio == MedioEnvio.PORTAL
    persona = (persona_entrega or "").strip() or expediente.beneficiaria.nombre
    estado_previo = expediente.estado.clave
    with transaction.atomic():
        c = Comprobacion(
            expediente=expediente, tipo=tipo, nombre=t["nombre"][:200], fundamento=t.get("fundamento", "")[:400],
            medio=medio, enviada_en=ahora, enviada_por=usuario, persona_entrega=persona[:250],
            recibida_por=None if portal else usuario, descripcion=(descripcion or "").strip(), fecha_hecho=fecha_hecho,
            periodo=periodo, plazo_uso=t.get("plazo") or "", estado_al_enviar=estado_previo)
        if contenido is not None:
            c.huella = hashlib.sha256(contenido).hexdigest()
            c.archivo.save(f"{tipo}_{nombre_archivo}", ContentFile(contenido), save=False)
        c.save()
        if t.get("hito"):
            fecha_hito = _momento_de(fecha_hecho) if t.get("hito_en_fecha_hecho") and fecha_hecho else ahora
            plazos.registrar_hito(expediente, t["hito"], usuario, fecha_hito, referencia=f"{t['nombre'][:90]}",
                                  datos={"comprobacion": c.pk, "periodo": periodo, "medio": medio})
        _calificar_plazo(c, expediente, t, hoy)
        c.acuse = _acuse(c, expediente, t, usuario, portal, persona, nombre_periodo)
        c.save()
        Evento.registrar(expediente, usuario, "comprobacion",
                         f"{t['nombre']} {'enviado desde el portal' if portal else 'entregado en la Delegación'} el "
                         f"{_fmt(ahora)}" + (f" ({c.situacion_plazo})" if c.en_plazo is not None else "") + ".",
                         acuse=c.acuse, datos={"comprobacion": c.pk, "tipo": tipo, "medio": medio})
        _cambiar_estado(c, expediente, t, usuario, portal)
    return c


def _calificar_plazo(c, expediente, t, hoy):
    if not t.get("plazo"):
        c.plazo_texto = "Las reglas no dan un plazo para esta entrega." if not t.get("pide_periodo") else \
            "Las reglas no dan el día de entrega de cada mes (R-18): se registra sin calificar el plazo."
        return
    v = plazos.vencimiento(expediente, t["plazo"])
    if v is None:
        c.plazo_texto = "El programa no tiene ese plazo."
        return
    c.plazo_texto = f"{v.nombre}: {v.texto}"[:300]
    if v.tiene_fecha:
        c.vence = v.vencimiento
        c.en_plazo = hoy <= v.vencimiento


def _acuse(c, expediente, t, usuario, portal, persona, nombre_periodo):
    renglones = [
        ("Comprobación", t["nombre"]), ("Expediente", f"{expediente.folio} · {expediente.programa.nombre}"),
        ("Persona beneficiaria", expediente.beneficiaria.nombre), ("Medio", c.get_medio_display()),
        ("Fecha y hora", _fmt(c.enviada_en)),
    ]
    if portal:
        renglones.append(("Envía", f"{persona} (cuenta del portal {usuario.username})"))
    else:
        renglones += [("Entrega", persona),
                      ("Recibe", f"{usuario.get_full_name() or usuario.username}, {usuario.unidad.nombre}")]
    if nombre_periodo:
        renglones.append(("Periodo que reporta", nombre_periodo))
    if c.fecha_hecho:
        renglones.append((t.get("fecha_hecho") or "Fecha", f"{c.fecha_hecho:%d/%m/%Y}"))
    if c.archivo:
        renglones.append(("Documento", f"{c.nombre_archivo} (SHA-256 {c.huella[:16]}…)"))
    if c.descripcion:
        renglones.append(("Descripción", c.descripcion[:500]))
    renglones.append(("Plazo", c.plazo_texto + (f" · {c.situacion_plazo.upper()}" if c.en_plazo is not None else "")))
    if t.get("fundamento"):
        renglones.append(("Fundamento", t["fundamento"]))
    nota = ("Fuera de plazo: se registra igual y queda señalado." if c.en_plazo is False else
            "El mismo registro vale para lo que se envía por el portal y lo que se entrega en la Delegación.")
    return emitir_acuse(expediente, "comprobacion", f"Acuse de {t['nombre'][:180]}", usuario, renglones,
                        destinatario=expediente.delegacion.nombre, nota=nota, referencia=t["clave"])


def _hay_transicion(expediente, destino):
    from django.db.models import Q

    return Transicion.objects.filter(origen=expediente.estado, destino__clave=destino).filter(
        Q(programa__isnull=True) | Q(programa=expediente.programa)).exists()


def _cambiar_estado(c, expediente, t, usuario, portal):
    destino = t.get("estado_destino")
    if not destino:
        return
    expediente.refresh_from_db()
    medio = "enviado desde el portal" if portal else "entregado en la Delegación"
    if destino == "comprobacion_enviada" and expediente.estado.clave in datos_ejecucion()["estados_previos_a_la_ejecucion"]:
        expediente.cambiar_estado(
            "en_ejecucion", None, por_sistema=True, tipo_evento="inicio_ejecucion",
            descripcion=f"Inicio de la ejecución de las actividades: el sistema lo registra al recibir la primera "
                        f"comprobación ({t['nombre']}, {medio}).", datos={"comprobacion": c.pk})
        expediente.refresh_from_db()
    if not _hay_transicion(expediente, destino):
        return  # el flujo no lo pide desde este estado (por ejemplo, el informe después del aviso de término)
    descripcion = f"{t['nombre']} {medio} el {_fmt(c.enviada_en)} (acuse {c.acuse.folio})."
    if portal:
        expediente.cambiar_estado(destino, None, por_sistema=True, tipo_evento="comprobacion_estado", acuse=c.acuse,
                                  descripcion=descripcion + f" Lo envió {c.persona_entrega} desde su cuenta.",
                                  datos={"comprobacion": c.pk})
    else:
        expediente.cambiar_estado(destino, usuario, tipo_evento="comprobacion_estado", acuse=c.acuse,
                                  descripcion=descripcion, datos={"comprobacion": c.pk})
    c.cambio_estado = destino
    c.save(update_fields=["cambio_estado"])


def marcar_revisada(usuario, comprobacion, momento=None):
    """La Delegación del expediente revisa lo que llegó por el portal (queda la fecha, la hora y quién)."""
    exp = comprobacion.expediente
    if usuario.tipo_unidad != TipoUnidad.DELEGACION or usuario.unidad_id != exp.delegacion_id:
        raise PermissionDenied("La revisa la Delegación del expediente.")
    from . import reportes

    if reportes.es_revisable(comprobacion):
        raise ValidationError("Los reportes mensuales y los acuses de depósito se revisan con su resultado: revisado, con "
                              "observaciones o devuelto para corregir.")
    if not comprobacion.por_portal:
        raise ValidationError("Lo entregado en ventanilla ya lo recibió la Delegación.")
    if comprobacion.revisada_en:
        raise ValidationError("Ya se revisó.")
    comprobacion.revisada_por, comprobacion.revisada_en = usuario, momento or timezone.now()
    comprobacion.save(update_fields=["revisada_por", "revisada_en"])
    Evento.registrar(exp, usuario, "comprobacion_revisada",
                     f"{comprobacion.nombre} recibido por el portal: revisado por {usuario.unidad.nombre}.",
                     datos={"comprobacion": comprobacion.pk})
    return comprobacion
