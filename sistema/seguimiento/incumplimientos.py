"""HU-6.2 · Incumplimientos y reintegros.

- **Omisiones por subsanar** (``avisar_omision``): el área responsable avisa las omisiones por conducto de la Delegación con la
  fecha límite que ella fija (las reglas no dan días: «durante el periodo que determine el Comité», CC 8.1.9 a, línea 4699; el
  aviso lo dice), deja el hito ``aviso_omision`` con ``datos.vence`` (uso ``subsanar_omisiones``) y el expediente pasa a
  «omisiones por subsanar». Si se subsanan, ``dar_por_subsanadas`` regresa al estado previo. Si vence sin subsanar, ``revisar``
  (``manage.py revisar_plazos``) **lo señala** y una persona confirma la propuesta de cancelación (P-08: nada se ejecuta solo).
- **Señalamientos** (``Senalamiento``): el sistema prepara y una persona confirma con un clic (``confirmar``): omisión vencida →
  propuesta de cancelación; cheque vencido sin cobrar (PSAHEM 8.1.9.2 fr. VII) → propuesta de baja; reporte de Guardabosque no
  entregado o que no cumple (``AL_REPORTE_INCUMPLIDO``) → propuesta de suspensión, y con tres no presentados (PEG 8.1.9.2 f) →
  propuesta de baja; faltantes de la recepción vencidos → **desecho** de la solicitud; incidencia de incumplimiento de la
  verificación (``AL_INCIDENCIA``) → aviso de omisión.
- **Cancelación y baja** (acuerdo del Comité que cumple la Unidad Jurídica; ``reasignacion.ejecutar_acuerdo``): el expediente
  pasa a «cancelada», la persona se **inscribe en el Listado de Personas Beneficiarias Incumplidas** con el acuerdo como fundamento
  (``dictamen.juridico``), lo no ministrado queda como recurso liberado para la lista de espera, se prepara el **requerimiento de
  devolución** y la Delegación notifica la cancelación. Suspensión y levantamiento: acuerdo que cumple el área responsable.
- **Requerimiento** (``emitir_requerimiento``, Unidad Jurídica): monto = lo ministrado (o lo ministrado de más por la verificación,
  ``Verificacion.excedente_ministrado``) **más el valor de la planta no establecida** donde las reglas lo piden (PS 8.1.9 c d,
  línea 6042; RHF 8.1.9 c fr. 5, línea 3412: cantidad por el precio oficial, que las reglas no traen), y la **cuenta para el
  reintegro** que registra Administración y Finanzas por programa (``registrar_cuenta``; en PSAHEM, duda abierta R-14). Pasa a
  «en devolución» y la Delegación lo notifica. Administración y Finanzas **comprueba el depósito** (``comprobar_deposito``): el
  expediente queda «reintegrado» y el reintegro vuelve como recurso liberado.
"""
import hashlib
from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone

from dictamen import juridico
from dictamen import seguimiento as dictamen_seguimiento
from dictamen.comun import exigir_acceso, exigir_unidad
from nucleo import notificaciones, plazos
from nucleo.acuses import emitir_acuse
from nucleo.models import Evento, Expediente, TipoUnidad
from nucleo.templatetags.moneda import formato_moneda
from nucleo.trazabilidad import registra_usuario

from . import reasignacion
from .models import (AvisoOmision, CuentaReintegro, EstadoPropuesta, EstadoRequerimiento, Propuesta, Requerimiento,
                     Senalamiento)

CERO = Decimal("0")
CENTAVO = Decimal("0.01")
TIPOS_HU_6_2 = ("cancelacion", "suspension", "levantar_suspension", "baja_cheque", "baja_reportes")


def datos_incumplimientos():
    return reasignacion.datos_seguimiento()["incumplimientos"]


def _fmt(valor):
    return reasignacion._fmt(valor)


def _sancion(expediente, *claves):
    """Texto y numeral de una sanción de las reglas del programa (``Ejercicio.datos["sanciones"]``)."""
    for s in (expediente.ejercicio.datos or {}).get("sanciones", []) or []:
        if isinstance(s, dict) and s.get("clave") in claves:
            return f"{expediente.programa.clave} {s.get('numeral', '')}" + (f" (línea {s['linea']})" if s.get("linea") else "")
    return ""


def _puede(usuario, expediente, destino):
    return expediente.transiciones_posibles(usuario).filter(destino__clave=destino).exists()


# ----------------------------------------------------------------------------- montos
def cheques_vencidos(expediente, hoy=None):
    """Cheques entregados que vencieron sin cobrarse (PSAHEM): no cuentan como ministrado."""
    from pagos.cheques import vencimiento_cobro

    hoy = hoy or timezone.localdate()
    lista = []
    for c in expediente.cheques.filter(entregado_en__isnull=False, cobrado_en__isnull=True):
        v = vencimiento_cobro(c)
        if v is not None and v.tiene_fecha and v.estado(hoy) == "vencido":
            lista.append(c)
    return lista


def ministrado_efectivo(expediente):
    return max(CERO, reasignacion.ministrado(expediente) - sum((c.importe for c in cheques_vencidos(expediente)), CERO))


def planta_aplica(expediente):
    """Las reglas del programa piden reintegrar el valor de la planta no establecida (PS y RHF)."""
    regla = (expediente.ejercicio.datos or {}).get("valor_planta_no_establecida")
    return bool(regla) and isinstance(regla, dict) and regla.get("aplica", True) is not False


def fundamento_planta(expediente):
    regla = (expediente.ejercicio.datos or {}).get("valor_planta_no_establecida") or {}
    return f"{expediente.programa.clave} {regla.get('numeral', '')}" + (f" (línea {regla['linea']})" if regla.get("linea") else "")


def cuenta_vigente(programa):
    return CuentaReintegro.objects.filter(programa=programa, vigente=True).order_by("-registrada_en").first()


def config_cuenta(programa):
    cfg = datos_incumplimientos()["cuentas"]
    return {**cfg["por_omision"], **cfg.get(programa.clave, {})}


# ----------------------------------------------------------------------------- cuenta para reintegros
@registra_usuario
def registrar_cuenta(usuario, programa, titular, banco, cuenta, referencia="", nota=""):
    """Administración y Finanzas registra la cuenta para los reintegros del programa (la anterior deja de estar vigente)."""
    exigir_unidad(usuario, TipoUnidad.ADMIN_FINANZAS)
    if not ((titular or "").strip() and (banco or "").strip() and (cuenta or "").strip()):
        raise ValidationError("Escriba el titular, el banco y la cuenta.")
    with transaction.atomic():
        _actualizar(CuentaReintegro.objects.filter(programa=programa, vigente=True), vigente=False)
        return CuentaReintegro.objects.create(programa=programa, titular=titular.strip(), banco=banco.strip(),
                                              cuenta=cuenta.strip(), referencia=(referencia or "").strip(),
                                              nota=(nota or "").strip(), registrada_por=usuario)


# ----------------------------------------------------------------------------- omisiones
def puede_avisar(usuario, expediente):
    return (usuario.tipo_unidad == TipoUnidad.DIRECCION and usuario.unidad.programas.filter(pk=expediente.programa.pk).exists()
            and _puede(usuario, expediente, "omisiones_por_subsanar"))


@registra_usuario
def avisar_omision(usuario, expediente, omisiones, vence, causa="", incidencia=None, momento=None):
    """El área responsable avisa las omisiones con la fecha límite para subsanarlas (criterio 1)."""
    reasignacion._exigir_area(usuario, expediente.ejercicio)
    exigir_acceso(usuario, expediente)
    expediente.refresh_from_db()
    if not puede_avisar(usuario, expediente):
        raise ValidationError(f"En el estado «{expediente.estado}» no se avisan omisiones.")
    if not (omisiones or "").strip():
        raise ValidationError("Describa las omisiones que la persona debe subsanar.")
    ahora = momento or timezone.now()
    if isinstance(vence, str):
        vence = date.fromisoformat(vence)
    if vence is None:
        raise ValidationError("Cada omisión necesita su plazo: indique la fecha límite para subsanarla.")
    if vence <= timezone.localtime(ahora).date():
        raise ValidationError("La fecha límite para subsanar debe ser posterior al aviso.")
    nota = datos_incumplimientos()["omisiones"]["nota_plazo"]
    fundamento = _sancion(expediente, "suspension_temporal")
    with transaction.atomic():
        aviso = AvisoOmision.objects.create(
            expediente=expediente, omisiones=omisiones.strip(), causa=(causa or "").strip()[:300], vence=vence,
            plazo_texto=f"Hasta el {vence:%d/%m/%Y}, plazo fijado por el área responsable"[:400], incidencia=incidencia,
            estado_al_avisar=expediente.estado.clave, creado_por=usuario, creado_en=ahora)
        renglones = [("Expediente", f"{expediente.folio} · {expediente.programa.nombre}"),
                     ("Persona beneficiaria", expediente.beneficiaria.nombre), ("Omisiones por subsanar", aviso.omisiones),
                     ("Fecha límite para subsanar", f"{vence:%d/%m/%Y} (la fija el área responsable)"),
                     ("Causa", aviso.causa or "—"), ("Fecha y hora del aviso", _fmt(ahora)), ("Avisa", usuario.unidad.nombre),
                     ("Fundamento", fundamento)]
        aviso.acuse = emitir_acuse(expediente, "aviso_omision", f"Aviso de omisiones por subsanar · {expediente.folio}", usuario,
                                   renglones, destinatario=expediente.beneficiaria.nombre, nota=nota)
        aviso.notificacion = notificaciones.emitir_notificacion(
            expediente, "omision", f"Omisiones por subsanar hasta el {vence:%d/%m/%Y}", usuario, acuse_envio=aviso.acuse,
            destinatario=expediente.beneficiaria, renglones=renglones, observaciones=aviso.omisiones,
            datos={"aviso_omision": aviso.pk})
        aviso.save(update_fields=["acuse", "notificacion"])
        plazos.registrar_hito(expediente, "aviso_omision", usuario, ahora, referencia=aviso.acuse.folio,
                              datos={"vence": vence.isoformat(), "aviso": aviso.pk})
        expediente.cambiar_estado("omisiones_por_subsanar", usuario, motivo=aviso.omisiones, tipo_evento="aviso_omision",
                                  acuse=aviso.acuse, descripcion=f"Omisiones por subsanar hasta el {vence:%d/%m/%Y} ({aviso.acuse.folio}).",
                                  datos={"aviso": aviso.pk})
        if incidencia is not None:
            incidencia.atendida_en = ahora
            incidencia.save(update_fields=["atendida_en"])
            _actualizar(Senalamiento.objects.filter(tipo="incidencia", clave=f"incidencia-{incidencia.pk}"),
                        atendido_en=ahora, atendido_por=usuario, resultado=f"Aviso de omisión {aviso.acuse.folio}")
    return aviso


def aviso_vigente(expediente):
    return expediente.avisos_omision.filter(subsanada_en__isnull=True).order_by("-creado_en", "-id").first()


@registra_usuario
def dar_por_subsanadas(usuario, aviso, motivo, momento=None):
    """El área responsable comprueba que se subsanaron: el expediente vuelve al estado en que estaba."""
    exp = aviso.expediente
    reasignacion._exigir_area(usuario, exp.ejercicio)
    exp.refresh_from_db()
    if exp.estado.clave != "omisiones_por_subsanar" or aviso.subsanada_en:
        raise ValidationError("No hay omisiones por subsanar en este expediente.")
    if not (motivo or "").strip():
        raise ValidationError("Escriba cómo se subsanaron.")
    ahora = momento or timezone.now()
    with transaction.atomic():
        aviso.subsanada_en, aviso.subsanada_por, aviso.motivo_subsanacion = ahora, usuario, motivo.strip()
        aviso.save(update_fields=["subsanada_en", "subsanada_por", "motivo_subsanacion"])
        destino = aviso.estado_al_avisar if _puede(usuario, exp, aviso.estado_al_avisar) else "en_ejecucion"
        exp.cambiar_estado(destino, usuario, motivo=motivo.strip(), tipo_evento="omisiones_subsanadas",
                           descripcion=f"Omisiones subsanadas ({'en' if timezone.localtime(ahora).date() <= aviso.vence else 'fuera de'} "
                                       f"plazo): {motivo.strip()}", datos={"aviso": aviso.pk})
        _actualizar(Senalamiento.objects.filter(expediente=exp, tipo="omision_vencida", clave=f"aviso-{aviso.pk}",
                                                atendido_en__isnull=True),
                    atendido_en=ahora, atendido_por=usuario, resultado="Omisiones subsanadas")
    return aviso


# ----------------------------------------------------------------------------- señalamientos
def senalar(expediente, tipo, clave, descripcion, fundamento="", datos=None):
    """Crea el señalamiento una sola vez por situación; deja el renglón en la bitácora sin persona. Devuelve None si ya existía."""
    if Senalamiento.objects.filter(expediente=expediente, tipo=tipo, clave=clave).exists():
        return None
    try:
        with transaction.atomic():
            s = Senalamiento.objects.create(expediente=expediente, tipo=tipo, clave=clave[:80], descripcion=descripcion,
                                            fundamento=fundamento[:400], datos=datos or {})
    except IntegrityError:
        return None
    Evento.registrar(expediente, None, f"senalamiento_{tipo}", f"{descripcion} Se prepara: {s.config.get('accion', '').lower()} "
                     "(lo confirma una persona).", datos={"senalamiento": s.pk})
    return s


def _actualizar(qs, **campos):
    """Como ``qs.update(**campos)``, pero registro por registro para que cada cambio quede en el historial (trazabilidad)."""
    n = 0
    for obj in qs:
        for campo, valor in campos.items():
            setattr(obj, campo, valor)
        obj.save(update_fields=list(campos))
        n += 1
    return n


def abiertos(qs=None):
    return (qs if qs is not None else Senalamiento.objects.all()).filter(atendido_en__isnull=True).select_related(
        "expediente__ejercicio__programa", "expediente__estado", "expediente__delegacion")


def senalamientos_de(usuario):
    """Señalamientos abiertos que atiende la unidad: el área responsable (propuestas, incidencias, faltantes de la Dirección) y la
    Delegación (faltantes vencidos en ventanilla)."""
    from nucleo.models import expedientes_visibles

    qs = abiertos(Senalamiento.objects.filter(expediente__in=expedientes_visibles(usuario)))
    if usuario.tipo_unidad == TipoUnidad.DELEGACION:
        return qs.filter(tipo="faltantes_vencidos", expediente__estado__clave="recibida")
    if usuario.tipo_unidad == TipoUnidad.DIRECCION:
        return qs.exclude(tipo="faltantes_vencidos", expediente__estado__clave="recibida")
    return qs.none()


def al_incidencia(incidencia):
    """``extensiones.AL_INCIDENCIA`` (HU-4.2): una incidencia de incumplimiento queda señalada para avisar la omisión."""
    if incidencia.tipo != "incumplimiento":
        return
    senalar(incidencia.expediente, "incidencia", f"incidencia-{incidencia.pk}",
            f"La verificación registró un incumplimiento: {incidencia.descripcion}", datos={"incidencia": incidencia.pk})


def al_reporte_incumplido(evaluacion):
    """``extensiones.AL_REPORTE_INCUMPLIDO`` (HU-4.3): suspensión por ministración o, con tres reportes no presentados, baja."""
    from ejecucion.reportes import periodos_senalados

    exp = evaluacion.expediente
    cfg = datos_incumplimientos()["senalamientos"]
    no_entregados = [e for e in periodos_senalados(exp) if e.resultado == "no_entrego"]
    if len(no_entregados) >= datos_incumplimientos()["reportes_para_baja"]:
        senalar(exp, "baja_reportes", "baja", f"{len(no_entregados)} reportes mensuales no presentados ("
                + ", ".join(e.nombre_periodo or e.periodo for e in no_entregados) + ").", cfg["baja_reportes"]["fundamento"],
                {"periodos": [e.periodo for e in no_entregados]})
    else:
        senalar(exp, "reportes_incumplidos", f"periodo-{evaluacion.periodo}",
                f"El reporte de {evaluacion.nombre_periodo or evaluacion.periodo} quedó «{evaluacion.get_resultado_display().lower()}».",
                cfg["reportes_incumplidos"]["fundamento"], {"periodo": evaluacion.periodo})


def revisar(hoy):
    """``manage.py revisar_plazos``: señala (una vez) las omisiones vencidas, los cheques vencidos sin cobrar y los faltantes de la
    recepción vencidos. Solo prepara la propuesta: la confirma una persona (P-08)."""
    cfg = datos_incumplimientos()["senalamientos"]
    n = 0
    for aviso in (AvisoOmision.objects.filter(subsanada_en__isnull=True, vence__lt=hoy,
                                              expediente__estado__clave="omisiones_por_subsanar").select_related("expediente")):
        if aviso_vigente(aviso.expediente) != aviso:
            continue
        n += senalar(aviso.expediente, "omision_vencida", f"aviso-{aviso.pk}",
                     f"Venció el {aviso.vence:%d/%m/%Y} el plazo para subsanar las omisiones avisadas ({aviso.acuse.folio if aviso.acuse_id else ''}) "
                     "sin que se subsanaran.", _sancion(aviso.expediente, "suspension_temporal"), {"aviso": aviso.pk}) is not None
    from pagos.models import Cheque

    for c in Cheque.objects.filter(entregado_en__isnull=False, cobrado_en__isnull=True).select_related("expediente__estado"):
        if c.expediente.estado.final or c.expediente.estado.clave in ("cancelada", "en_devolucion", "reintegrada"):
            continue
        if c in cheques_vencidos(c.expediente, hoy):
            n += senalar(c.expediente, "cheque_vencido", f"cheque-{c.pk}",
                         f"El cheque {c.numero} (ministración {c.ministracion}, {formato_moneda(c.importe)}) venció sin cobrarse.",
                         cfg["cheque_vencido"]["fundamento"], {"cheque": c.pk}) is not None
    for exp in Expediente.objects.filter(estado__clave__in=("recibida", "faltantes"), eventos__tipo="plazo_vencido").distinct():
        ev = exp.eventos.filter(tipo="plazo_vencido").order_by("-fecha_hora").first()
        n += senalar(exp, "faltantes_vencidos", f"faltantes-{ev.pk}", ev.descripcion, cfg["faltantes_vencidos"]["fundamento"],
                     {"evento": ev.pk}) is not None
    return n


def texto_desecho(senalamiento):
    exp = senalamiento.expediente
    notif = exp.notificaciones.filter(tipo="faltantes", notificada_en__isnull=False).order_by("-notificada_en").first()
    texto = f"{senalamiento.descripcion} {senalamiento.fundamento}."
    if notif is not None and notif.acuse_notificacion_id:
        texto += f" Aviso de faltantes notificado el {timezone.localtime(notif.notificada_en):%d/%m/%Y} ({notif.acuse_notificacion.folio})."
    return texto


@registra_usuario
def confirmar(usuario, senalamiento, momento=None):
    """Una persona confirma lo que preparó el sistema (P-08): la propuesta al Comité o el desecho de la solicitud."""
    if senalamiento.atendido_en:
        raise ValidationError("Ese señalamiento ya se atendió.")
    exp = senalamiento.expediente
    exigir_acceso(usuario, exp)
    exp.refresh_from_db()
    ahora = momento or timezone.now()
    cfg = senalamiento.config
    with transaction.atomic():
        if senalamiento.tipo == "faltantes_vencidos":
            if not _puede(usuario, exp, "desechada"):
                raise PermissionDenied("El desecho lo confirma la Delegación (en ventanilla) o el área responsable (faltantes "
                                       "que avisó la Dirección).")
            motivo = texto_desecho(senalamiento)
            acuse = emitir_acuse(exp, "desecho", f"Solicitud desechada · {exp.folio}", usuario,
                                 [("Expediente", exp.folio), ("Persona solicitante", exp.solicitante.nombre), ("Motivo", motivo),
                                  ("Fecha y hora", _fmt(ahora)), ("Confirma", usuario.unidad.nombre)],
                                 destinatario=exp.solicitante.nombre)
            exp.cambiar_estado("desechada", usuario, motivo=motivo, tipo_evento="desecho_confirmado", acuse=acuse,
                               descripcion="Solicitud desechada: lo preparó el sistema al vencer el plazo y lo confirmó una persona.")
            resultado = f"Desecho confirmado ({acuse.folio})"
        elif cfg.get("propuesta"):
            p = reasignacion.proponer(usuario, exp, cfg["propuesta"], descripcion=_texto_preparado(senalamiento, cfg["propuesta"]),
                                      momento=ahora)
            senalamiento.propuesta = p
            resultado = f"Propuesta al Comité {p.acuse.folio}"
        else:
            raise ValidationError("Este señalamiento se atiende con su formulario (aviso de omisión con su plazo).")
        senalamiento.atendido_en, senalamiento.atendido_por, senalamiento.resultado = ahora, usuario, resultado[:300]
        senalamiento.save(update_fields=["atendido_en", "atendido_por", "resultado", "propuesta"])
    return senalamiento


def _texto_preparado(s, tipo):
    exp = s.expediente
    accion = {"cancelacion": "Cancelar el apoyo", "baja_cheque": "Dar de baja", "baja_reportes": "Dar de baja",
              "suspension": "Suspender temporalmente el apoyo"}[tipo]
    texto = f"{accion} del expediente {exp.folio} ({exp.beneficiaria.nombre}): {s.descripcion}"
    if tipo in ("cancelacion", "baja_cheque", "baja_reportes"):
        texto += " Inscribir a la persona en el Listado de Personas Beneficiarias Incumplidas y requerir la devolución."
    return texto + (f" Fundamento: {s.fundamento}." if s.fundamento else "")


# ----------------------------------------------------------------------------- propuestas de HU-6.2 (las ejecuta el acuerdo)
def tipos_propuesta(usuario_o_none, expediente):
    """Propuestas de incumplimiento que proceden para el expediente: ``[clave]``."""
    estado = expediente.estado.clave
    tipos = []
    abiertos_tipos = set(abiertos(expediente.senalamientos.all()).values_list("tipo", flat=True))
    puede_cancelar = estado in ("omisiones_por_subsanar", "suspendida", "caso_fortuito", "en_ejecucion", "contratada",
                                "planta_entregada", "vale_entregado", "pagada", "cheque_entregado", "comprobacion_enviada",
                                "verificada")
    if puede_cancelar:
        tipos.append("cancelacion")
    if estado in ("en_ejecucion", "contratada", "planta_entregada", "pagada", "cheque_entregado", "comprobacion_enviada",
                  "verificada", "omisiones_por_subsanar", "caso_fortuito"):
        tipos.append("suspension")
    if estado == "suspendida":
        tipos.append("levantar_suspension")
    if puede_cancelar and "cheque_vencido" in abiertos_tipos:
        tipos.append("baja_cheque")
    if puede_cancelar and "baja_reportes" in abiertos_tipos:
        tipos.append("baja_reportes")
    return tipos


def monto_por_devolver(expediente, base="ministrado"):
    from ejecucion import verificacion

    if base == "excedente":
        v = verificacion.vigente(expediente)
        return (v.excedente_ministrado or CERO) if v is not None else CERO
    return ministrado_efectivo(expediente)


@registra_usuario
def inscribir_en_listado(usuario, expediente, acuerdo, motivo):
    """Inscripción automática en el Listado de Personas Beneficiarias Incumplidas con el acuerdo como fundamento (criterio 3)."""
    persona = expediente.beneficiaria
    registro = juridico.registrar_incumplida(
        usuario, nombre=persona.nombre, curp=persona.curp or "", rfc=persona.rfc or "", persona=persona,
        programa=f"{expediente.programa.nombre} {expediente.ejercicio.anio}", motivo=motivo[:2000],
        acuerdo=f"Acuerdo {acuerdo.numero} ({acuerdo.sesion.numero})")
    Evento.registrar(expediente, usuario, "inscripcion_incumplidas",
                     f"{persona.nombre} inscrita en el Listado de Personas Beneficiarias Incumplidas (acuerdo {acuerdo.numero}).",
                     datos={"incumplida": registro.pk, "acuerdo": acuerdo.pk})
    return registro


def preparar_requerimiento(expediente, motivo, propuesta=None, acuerdo=None, base="ministrado"):
    """Requerimiento de devolución por emitir (o «sin recurso por devolver» si no hay monto ni planta que reintegrar)."""
    existente = expediente.requerimientos.exclude(estado=EstadoRequerimiento.SIN_MONTO).first()
    if existente is not None:
        return existente
    pagado = ministrado_efectivo(expediente)
    monto = monto_por_devolver(expediente, base)
    estado = EstadoRequerimiento.POR_EMITIR if monto > 0 or planta_aplica(expediente) else EstadoRequerimiento.SIN_MONTO
    r = Requerimiento.objects.create(expediente=expediente, propuesta=propuesta, acuerdo=acuerdo, motivo=motivo[:300], base=base,
                                     monto_ministrado=pagado, monto_base=monto, monto_total=monto, estado=estado)
    Evento.registrar(expediente, None, "requerimiento_preparado",
                     f"Requerimiento de devolución preparado: {formato_moneda(monto)} ({datos_incumplimientos()['reintegro']['bases'][base].lower()})"
                     + (", más el valor de la planta no establecida que determine la Unidad Jurídica" if planta_aplica(expediente) else "")
                     + "." if estado == EstadoRequerimiento.POR_EMITIR else "Sin recurso por devolver: no se ministró nada.",
                     datos={"requerimiento": r.pk})
    return r


def _ejecutar_cancelacion(propuesta, acuerdo, usuario):
    exp = propuesta.expedientes.get()
    if not propuesta.aprobada:
        Evento.registrar(exp, usuario, "acuerdo_ejecutado", f"El Comité no aprobó la propuesta (acuerdo {acuerdo.numero}).",
                         datos={"acuerdo": acuerdo.pk})
        return
    exp.refresh_from_db()
    motivo = reasignacion._motivo(acuerdo) + " " + propuesta.descripcion
    libera = reasignacion.por_ministrar(exp)
    # Sale de la Lista de Personas Beneficiarias con lo no ministrado, en el registro único de los listados (HU-2.4).
    dictamen_seguimiento.registrar_salida(usuario, exp, "baja" if propuesta.tipo.startswith("baja") else "cancelacion", libera,
                                          acuerdo, estado_nuevo="cancelada", referencia=f"Acuerdo {acuerdo.numero}",
                                          motivo=motivo[:2000], tipo_evento="cancelacion",
                                          descripcion=f"{propuesta.nombre_tipo} (acuerdo {acuerdo.numero}).")
    inscribir_en_listado(usuario, exp, acuerdo, propuesta.descripcion)
    preparar_requerimiento(exp, propuesta.nombre_tipo, propuesta, acuerdo, propuesta.datos.get("base", "ministrado"))
    notificaciones.emitir_notificacion(exp, "otro", f"Cancelación del apoyo y baja del programa ({exp.folio})", usuario,
                                       destinatario=exp.beneficiaria,
                                       renglones=[("Acuerdo del Comité", f"{acuerdo.numero} ({acuerdo.sesion.numero})"),
                                                  ("Motivo", propuesta.descripcion),
                                                  ("Listado de Personas Beneficiarias Incumplidas", "Inscrita por el acuerdo")],
                                       datos={"acuerdo": acuerdo.pk})
    _actualizar(abiertos(exp.senalamientos.all()), atendido_en=timezone.now(), atendido_por=usuario,
                resultado=f"Cancelado por el acuerdo {acuerdo.numero}")


def _ejecutar_suspension(propuesta, acuerdo, usuario):
    exp = propuesta.expedientes.get()
    if not propuesta.aprobada:
        return
    exp.refresh_from_db()
    if propuesta.tipo == "levantar_suspension":
        reasignacion._volver(exp, usuario, acuerdo, propuesta.datos.get("estado_previo"),
                             f"Suspensión levantada (acuerdo {acuerdo.numero}).")
        return
    exp.cambiar_estado("suspendida", usuario, motivo=reasignacion._motivo(acuerdo) + " " + propuesta.descripcion,
                       tipo_evento="suspension", descripcion=f"Apoyo suspendido temporalmente (acuerdo {acuerdo.numero}).",
                       datos={"acuerdo": acuerdo.pk})
    _actualizar(abiertos(exp.senalamientos.filter(tipo="reportes_incumplidos")),
                atendido_en=timezone.now(), atendido_por=usuario, resultado=f"Suspendido por el acuerdo {acuerdo.numero}")


# ----------------------------------------------------------------------------- requerimiento y reintegro
def plazo_reintegro(expediente, requerimiento):
    texto = datos_incumplimientos()["reintegro"]["nota_plazo"]
    v = expediente.ejercicio.plazo("reintegro")
    base = f"{v.texto_plazo} ({v.fundamento})" if v else "inmediato"
    desiste = requerimiento.propuesta_id and requerimiento.propuesta.tipo == "desistimiento"
    if desiste and expediente.ejercicio.plazo("desistimiento_reintegro"):
        d = expediente.ejercicio.plazo("desistimiento_reintegro")
        base += f"; por desistimiento: {d.texto_plazo} ({d.fundamento})"
    return f"Reintegro {base}. {texto}"[:400]


@registra_usuario
def emitir_requerimiento(usuario, requerimiento, plantas=0, precio_planta=None, fuente_precio="", momento=None):
    """La Unidad Jurídica emite el requerimiento con el monto y la cuenta para el depósito (criterio 2); lo notifica la Delegación."""
    exigir_unidad(usuario, TipoUnidad.JURIDICA)
    exp = requerimiento.expediente
    exp.refresh_from_db()
    if requerimiento.estado != EstadoRequerimiento.POR_EMITIR or exp.estado.clave != "cancelada":
        raise ValidationError("Solo se emite un requerimiento por emitir de un apoyo cancelado.")
    plantas = int(plantas or 0)
    monto_planta = CERO
    if plantas:
        if not planta_aplica(exp):
            raise ValidationError(f"Las reglas de {exp.programa.nombre} no piden el valor de la planta no establecida.")
        if precio_planta in (None, "") or Decimal(str(precio_planta)) <= 0 or not (fuente_precio or "").strip():
            raise ValidationError("Indique el precio por planta y su fuente (listado oficial de la Secretaría de Finanzas o "
                                  "costo de producción): las reglas no traen el importe.")
        monto_planta = (Decimal(plantas) * Decimal(str(precio_planta))).quantize(CENTAVO)
    total = requerimiento.monto_base + monto_planta
    ahora = momento or timezone.now()
    with transaction.atomic():
        requerimiento.plantas_no_establecidas, requerimiento.monto_planta, requerimiento.monto_total = plantas, monto_planta, total
        if plantas:
            requerimiento.precio_planta, requerimiento.fuente_precio = Decimal(str(precio_planta)), fuente_precio.strip()[:250]
        if total <= 0:
            requerimiento.estado = EstadoRequerimiento.SIN_MONTO
            requerimiento.save()
            Evento.registrar(exp, usuario, "requerimiento_sin_monto", "Sin recurso por devolver: no hay requerimiento que emitir.")
            return requerimiento
        cuenta = cuenta_vigente(exp.programa)
        if cuenta is None:
            raise ValidationError(f"Administración y Finanzas todavía no registra la cuenta para los reintegros de "
                                  f"{exp.programa.nombre}.")
        requerimiento.cuenta, requerimiento.emitido_por, requerimiento.emitido_en = cuenta, usuario, ahora
        requerimiento.plazo_texto = plazo_reintegro(exp, requerimiento)
        bases = datos_incumplimientos()["reintegro"]["bases"]
        renglones = [("Expediente", f"{exp.folio} · {exp.programa.nombre}"), ("Persona beneficiaria", exp.beneficiaria.nombre),
                     ("Motivo", requerimiento.motivo),
                     ("Acuerdo del Comité", f"{requerimiento.acuerdo.numero} ({requerimiento.acuerdo.sesion.numero})"
                      if requerimiento.acuerdo_id else "—"),
                     (bases.get(requerimiento.base, "Lo ministrado"), formato_moneda(requerimiento.monto_base))]
        if plantas:
            renglones.append(("Valor de la planta no establecida",
                              f"{plantas} plantas × {formato_moneda(requerimiento.precio_planta)} = {formato_moneda(monto_planta)} "
                              f"({requerimiento.fuente_precio}; {fundamento_planta(exp)})"))
        renglones += [("Monto por devolver", formato_moneda(total)), ("Cuenta para el depósito", cuenta.texto),
                      ("Plazo", requerimiento.plazo_texto), ("Fecha y hora", _fmt(ahora)), ("Emite", usuario.unidad.nombre)]
        nota = config_cuenta(exp.programa).get("duda", "")
        requerimiento.acuse = emitir_acuse(exp, "requerimiento_devolucion", f"Requerimiento de devolución · {exp.folio}", usuario,
                                           renglones, destinatario=exp.beneficiaria.nombre, nota=nota)
        requerimiento.notificacion = notificaciones.emitir_notificacion(
            exp, "devolucion", f"Requerimiento de devolución de {formato_moneda(total)}", usuario,
            acuse_envio=requerimiento.acuse, destinatario=exp.beneficiaria, renglones=renglones,
            datos={"requerimiento": requerimiento.pk})
        requerimiento.estado = EstadoRequerimiento.EMITIDO
        requerimiento.save()
        exp.cambiar_estado("en_devolucion", usuario, tipo_evento="requerimiento_devolucion", acuse=requerimiento.acuse,
                           descripcion=f"Requerimiento de devolución de {formato_moneda(total)} a la cuenta {cuenta.texto}.",
                           datos={"requerimiento": requerimiento.pk})
    return requerimiento


@registra_usuario
def comprobar_deposito(usuario, requerimiento, fecha, importe, referencia, archivo, momento=None):
    """Administración y Finanzas comprueba el depósito del reintegro: el expediente queda reintegrado."""
    exigir_unidad(usuario, TipoUnidad.ADMIN_FINANZAS)
    exp = requerimiento.expediente
    exp.refresh_from_db()
    if requerimiento.estado != EstadoRequerimiento.EMITIDO or exp.estado.clave != "en_devolucion":
        raise ValidationError("Solo se comprueba el depósito de un requerimiento emitido.")
    ahora = momento or timezone.now()
    if isinstance(fecha, str):
        fecha = date.fromisoformat(fecha)
    if fecha is None or fecha > timezone.localtime(ahora).date() or fecha < timezone.localtime(requerimiento.emitido_en).date():
        raise ValidationError("La fecha del depósito debe estar entre el requerimiento y hoy.")
    importe = Decimal(str(importe or 0)).quantize(CENTAVO)
    if importe != requerimiento.monto_total:
        raise ValidationError(f"El importe depositado ({formato_moneda(importe)}) no coincide con el requerido "
                              f"({formato_moneda(requerimiento.monto_total)}).")
    if not (referencia or "").strip():
        raise ValidationError("Escriba la referencia o el folio del depósito.")
    contenido, nombre = reasignacion._leer_archivo(archivo)
    if contenido is None:
        raise ValidationError("Falta el comprobante del depósito.")
    with transaction.atomic():
        requerimiento.deposito_fecha, requerimiento.deposito_importe = fecha, importe
        requerimiento.deposito_referencia, requerimiento.comprobado_por, requerimiento.comprobado_en = referencia.strip()[:120], usuario, ahora
        requerimiento.deposito_huella = hashlib.sha256(contenido).hexdigest()
        requerimiento.deposito_archivo.save(f"deposito_{nombre}", ContentFile(contenido), save=False)
        requerimiento.acuse_deposito = emitir_acuse(
            exp, "reintegro_comprobado", f"Comprobación del reintegro · {exp.folio}", usuario,
            [("Expediente", exp.folio), ("Requerimiento", requerimiento.acuse.folio if requerimiento.acuse_id else "—"),
             ("Importe depositado", formato_moneda(importe)), ("Fecha del depósito", f"{fecha:%d/%m/%Y}"),
             ("Referencia", requerimiento.deposito_referencia), ("Cuenta", requerimiento.cuenta.texto),
             ("Comprobante", f"SHA-256 {requerimiento.deposito_huella[:16]}…"), ("Comprueba", usuario.unidad.nombre),
             ("Fecha y hora", _fmt(ahora))], destinatario=exp.beneficiaria.nombre)
        requerimiento.estado = EstadoRequerimiento.DEPOSITADO
        requerimiento.save()
        exp.cambiar_estado("reintegrada", usuario, tipo_evento="reintegro", acuse=requerimiento.acuse_deposito,
                           descripcion=f"Reintegro de {formato_moneda(importe)} depositado el {fecha:%d/%m/%Y}.",
                           datos={"requerimiento": requerimiento.pk})
        reasignacion.registrar_recurso(exp, "reintegro", importe, usuario, requerimiento.acuse_deposito.folio,
                                       "Reintegro depositado")
    return requerimiento


# ----------------------------------------------------------------------------- consultas
def requerimientos_visibles(usuario):
    from nucleo.models import expedientes_visibles

    qs = Requerimiento.objects.select_related("expediente__ejercicio__programa", "expediente__estado", "cuenta", "acuse",
                                              "acuerdo__sesion")
    if usuario.tipo_unidad in (TipoUnidad.JURIDICA, TipoUnidad.ADMIN_FINANZAS) or usuario.is_superuser:
        return qs
    return qs.filter(expediente__in=expedientes_visibles(usuario))


def por_emitir():
    return Requerimiento.objects.filter(estado=EstadoRequerimiento.POR_EMITIR, expediente__estado__clave="cancelada")


def por_comprobar():
    return Requerimiento.objects.filter(estado=EstadoRequerimiento.EMITIDO, expediente__estado__clave="en_devolucion")


def propuestas_abiertas_de_cancelacion():
    return Propuesta.objects.filter(tipo__in=TIPOS_HU_6_2).exclude(estado=EstadoPropuesta.EJECUTADA)
