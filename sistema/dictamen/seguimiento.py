"""HU-2.4 · Reasignaciones e incidentes: en las sesiones de seguimiento el Comité acuerda la atención de cada
incidente del ejercicio (desistimiento, cancelación, baja, sustitución, caso fortuito, suspensión, reintegro) y la
reasignación del recurso liberado a la lista de espera. Cada acuerdo lleva su causa, los expedientes a los que aplica y el
área que debe cumplirlo.

Efectos (``datos/dictamen.json`` → ``tipos_acuerdo[].efecto``):
- ``baja``: la persona beneficiaria sale de la Lista de Personas Beneficiarias (estado «baja») y su monto queda como
  recurso liberado;
- ``reasignacion``: entran a la Lista de Personas Beneficiarias las siguientes de la lista de espera, **en su orden**
  (lugar del acta), sin rebasar el recurso liberado que aún no se reasigna;
- ``sustitucion``: las dos cosas en un solo acuerdo (sale la persona beneficiaria y entra la siguiente de la lista);
- ``registro``: solo deja la constancia (caso fortuito, suspensión, reintegro, otro; en PSAHEM la instrucción de pago a
  la Fiduciaria por ministración y en PEG la validación de los reportes por periodo).
Cada salida y cada entrada queda en ``MovimientoListado`` (con su historial) y en la bitácora del expediente.

Convivencia con M6 (HU-6.1 y HU-6.2, sprint 3): ``MovimientoListado`` es el registro único de bajas, reasignaciones y recurso
liberado. Cuando el acuerdo resuelve una propuesta del área responsable (desistimiento con su acuse, cancelación, caso
fortuito, reasignación calculada por el área), se registra con ``aplicar_efecto=False`` y el efecto lo aplica M6 al cumplirse
el acuerdo con las mismas funciones de aquí (``registrar_salida``, ``registrar_entrada``, ``registrar_liberacion``). El
recurso por reasignar descuenta lo que ya está comprometido en una propuesta de reasignación en trámite (``COMPROMETIDO``),
así que el mismo recurso no se reasigna dos veces por los dos caminos.

Convivencia con M3 y M5 (sprint 2):
- la baja aplica a la persona beneficiaria mientras no tenga una ministración solicitada (aprobada, publicada, notificada,
  con contrato elaborado o por firmar, sin firma en plazo, contratada o con planta en trámite); con una ministración en
  curso o pagada lo que procede es el reintegro (acuerdo ``reintegro``). Dada de baja ya no puede firmar, recibir planta
  ni cobrar (``exigir_vigente``, que usan contrato y pagos);
- el recurso que la Dirección libera por un contrato sin firma en plazo (HU-3.3, ``contrato.firma.liberar_recurso``) entra
  también como recurso liberado (``al_liberar_recurso``, gancho ``AL_LIBERAR_RECURSO``) y el Comité lo reasigna igual;
- si los listados del acta ya se publicaron, la persona que entra por reasignación se publica con el acta de la sesión de
  seguimiento: al cerrarla con reasignaciones queda autorizada su publicación (``cerrar_sesion``, M3 HU-3.1).

Punto de conexión con los módulos M3–M6: ``RECEPTORES`` (tipo de acuerdo -> funciones). Por ahora
ningún módulo se registra, así que cumplir un acuerdo solo deja la constancia; cuando existan pagos
(M5) o seguimiento (M6), sus apps agregan aquí la función que ejecuta el acuerdo.
"""
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from nucleo.models import Evento, TipoUnidad, Unidad
from nucleo.templatetags.moneda import formato_moneda
from nucleo.trazabilidad import registra_usuario

from .comun import datos_dictamen, exigir_unidad
from .models import (
    Acuerdo, EstadoAcuerdo, EstadoSesion, MovimientoListado, ResolucionSesion, ResultadoListado, TipoMovimiento,
    TipoSesion,
)

CERO = Decimal("0")

# Estados de una persona beneficiaria que el Comité puede dar de baja (sin ministración solicitada ni pagada).
ESTADOS_CON_BAJA = ("aprobada", "publicada", "notificada", "contrato_elaborado", "contrato_en_delegacion",
                    "sin_firma_en_plazo", "contratada", "vale_entregado", "planta_entregada")
ESTADOS_CON_PAGO = ("ministracion_solicitada", "pagada", "remitida_fiduciaria", "cheque_emitido", "cheque_enviado",
                    "cheque_entregado")

RECEPTORES = {}  # {"instruccion_pago": [funcion(acuerdo)], ...}
COMPROMETIDO = []  # funciones (ejercicio) -> Decimal: recurso liberado ya reservado (propuestas de reasignación de M6)


def tipos_acuerdo(programa=None):
    tipos = datos_dictamen()["tipos_acuerdo"]
    if programa is None:
        return tipos
    return [t for t in tipos if not t.get("programas") or programa.clave in t["programas"]]


def tipo_acuerdo(clave):
    return next((t for t in datos_dictamen()["tipos_acuerdo"] if t["clave"] == clave), None)


def unidad_sugerida(clave_tipo, ejercicio=None):
    """Área que cumple el acuerdo por omisión (``datos/dictamen.json``). Si es una Dirección que no es Instancia
    Ejecutora del programa (la DRFF en PEG), se sugiere la Dirección del programa (Protección Forestal)."""
    t = tipo_acuerdo(clave_tipo)
    unidad = Unidad.objects.filter(clave=t.get("unidad")).first() if t else None
    if unidad is not None and ejercicio is not None and unidad.tipo == TipoUnidad.DIRECCION \
            and not unidad.programas.filter(pk=ejercicio.programa_id).exists():
        propia = Unidad.objects.filter(tipo=TipoUnidad.DIRECCION, programas=ejercicio.programa_id).first()
        return propia or unidad
    return unidad


def efecto(clave_tipo):
    t = tipo_acuerdo(clave_tipo)
    return (t or {}).get("efecto", "registro")


# ----------------------------------------------------------------------------- listas y recurso
def monto_aprobado(expediente):
    """Monto con el que el expediente está (o estaría) en los listados del acta de aprobación."""
    r = (ResolucionSesion.objects.filter(expediente=expediente, sesion__tipo=TipoSesion.APROBACION,
                                         sesion__estado=EstadoSesion.CELEBRADA)
         .order_by("-sesion__fecha_hora", "-pk").first())
    if r is not None and r.monto is not None:
        return r.monto
    from nucleo import montos

    return montos.monto_aprobado(expediente).total


def lista_de_espera(ejercicio):
    """Solicitudes que siguen en lista de espera, en su orden: [{"expediente", "lugar", "monto", "sesion"}]."""
    resoluciones = (ResolucionSesion.objects.filter(
        sesion__ejercicio=ejercicio, sesion__tipo=TipoSesion.APROBACION, sesion__estado=EstadoSesion.CELEBRADA,
        resultado=ResultadoListado.LISTA_ESPERA, expediente__estado__clave="lista_espera")
        .select_related("sesion", "expediente__solicitante", "expediente__predio__municipio", "expediente__delegacion")
        .order_by("sesion__fecha_hora", "orden", "pk"))
    vistos, lista = set(), []
    for r in resoluciones:
        if r.expediente_id in vistos:
            continue
        vistos.add(r.expediente_id)
        lista.append({"expediente": r.expediente, "lugar": r.orden, "monto": r.monto, "sesion": r.sesion})
    return lista


def movimientos_del_ejercicio(ejercicio):
    """Movimientos de listado del ejercicio: los de sus acuerdos y los que no vienen de un acuerdo (contrato sin firma en
    plazo, ajuste de superficie, reintegro)."""
    return MovimientoListado.objects.filter(Q(acuerdo__sesion__ejercicio=ejercicio)
                                            | Q(acuerdo__isnull=True, expediente__ejercicio=ejercicio))


def _con_monto(ejercicio):
    """Movimientos del ejercicio con monto, en orden (una sola consulta: la bandeja lo calcula por ejercicio)."""
    return list(movimientos_del_ejercicio(ejercicio).filter(monto__isnull=False)
                .select_related("expediente", "acuerdo").order_by("fecha_hora", "id"))


def totales_recurso(ejercicio, movimientos=None):
    """{"liberado": lo que salió o se liberó, "reasignado": lo que entró, "comprometido": reservado en propuestas}."""
    movimientos = _con_monto(ejercicio) if movimientos is None else movimientos
    liberado = sum((m.monto for m in movimientos if m.movimiento != TipoMovimiento.ENTRA), CERO)
    reasignado = sum((m.monto for m in movimientos if m.movimiento == TipoMovimiento.ENTRA), CERO)
    comprometido = sum((f(ejercicio) or CERO for f in COMPROMETIDO), CERO)
    return {"liberado": liberado, "reasignado": reasignado, "comprometido": comprometido}


def recurso_liberado(ejercicio):
    """Recurso liberado del ejercicio que aún no se reasigna ni está comprometido en una propuesta de reasignación."""
    t = totales_recurso(ejercicio)
    return t["liberado"] - t["reasignado"] - t["comprometido"]


def recursos_por_reasignar(ejercicio):
    """De qué movimientos viene el recurso por reasignar (los más antiguos se reasignan primero):
    ``[{"movimiento", "id", "expediente", "origen", "nombre_origen", "monto", "referencia"}]`` con lo que queda de cada uno."""
    movimientos = _con_monto(ejercicio)
    t = totales_recurso(ejercicio, movimientos)
    usado = t["reasignado"] + t["comprometido"]
    filas = []
    for m in movimientos:
        if m.movimiento == TipoMovimiento.ENTRA or m.monto <= 0:
            continue
        tomado = min(m.monto, usado)
        usado -= tomado
        if m.monto - tomado > 0:
            filas.append({"movimiento": m, "id": m.pk, "expediente": m.expediente, "origen": m.origen,
                          "nombre_origen": m.nombre_origen, "monto": m.monto - tomado,
                          "referencia": m.referencia or (m.acuerdo.numero if m.acuerdo_id else "")})
    return filas


def registrar_salida(usuario, expediente, origen, monto, acuerdo=None, estado_nuevo="baja", referencia="", motivo="",
                     descripcion="", tipo_evento="baja_comite", datos=None):
    """La persona beneficiaria sale de la Lista de Personas Beneficiarias: cambia de estado (``estado_nuevo``: «baja» o, si
    ya se le ministró, «cancelada») y queda el movimiento con lo que libera (lo no ministrado)."""
    expediente.refresh_from_db()
    anterior = expediente.estado.clave
    if estado_nuevo and anterior != estado_nuevo:
        expediente.cambiar_estado(estado_nuevo, usuario, motivo=motivo, tipo_evento=tipo_evento, descripcion=descripcion,
                                  datos={**(datos or {}), **({"acuerdo": acuerdo.pk} if acuerdo else {})})
    return MovimientoListado.objects.create(
        acuerdo=acuerdo, expediente=expediente, movimiento=TipoMovimiento.SALE, origen=origen, referencia=referencia[:120],
        estado_anterior=anterior, estado_nuevo=estado_nuevo or anterior,
        monto=None if monto is None else Decimal(monto).quantize(Decimal("0.01")), usuario=usuario,
        motivo="" if acuerdo is not None else (motivo or "")[:300])


def registrar_entrada(usuario, expediente, acuerdo, lugar, monto):
    """La solicitud de la lista de espera entra a la Lista de Personas Beneficiarias (el cambio de estado lo hace quien
    llama, con su descripción)."""
    return MovimientoListado.objects.create(acuerdo=acuerdo, expediente=expediente, movimiento=TipoMovimiento.ENTRA,
                                            origen="reasignacion", estado_anterior="lista_espera", estado_nuevo="aprobada",
                                            lugar_lista_espera=lugar, monto=monto, usuario=usuario,
                                            referencia=acuerdo.numero if acuerdo else "")


def registrar_liberacion(expediente, origen, monto, usuario=None, referencia="", descripcion="", momento=None):
    """Recurso que se libera sin que la persona salga de la lista (ajuste de superficie, reintegro depositado). Idempotente
    por expediente, origen y referencia."""
    monto = Decimal(monto or 0).quantize(Decimal("0.01"))
    if monto <= 0:
        return None
    existente = MovimientoListado.objects.filter(expediente=expediente, movimiento=TipoMovimiento.LIBERA, origen=origen,
                                                 referencia=referencia[:120]).first()
    if existente is not None:
        return existente
    m = MovimientoListado.objects.create(
        acuerdo=None, expediente=expediente, movimiento=TipoMovimiento.LIBERA, origen=origen, referencia=referencia[:120],
        motivo=descripcion[:300], estado_anterior=expediente.estado.clave, estado_nuevo=expediente.estado.clave,
        monto=monto, usuario=usuario, fecha_hora=momento or timezone.now())
    Evento.registrar(expediente, usuario, "recurso_liberado_registrado",
                     f"Recurso liberado para la lista de espera: {formato_moneda(monto)} ({m.nombre_origen.lower()}).",
                     datos={"movimiento": m.pk})
    return m


def _revisar_entradas(ejercicio, entran, liberado_aqui):
    """Las que entran deben ser las primeras de la lista de espera, en su orden, y caber en el recurso liberado."""
    lista = lista_de_espera(ejercicio)
    lugar = {x["expediente"].pk: x for x in lista}
    fuera = [e.folio for e in entran if e.pk not in lugar]
    if fuera:
        raise ValidationError("Solo entran solicitudes que están en la lista de espera del acta: " + ", ".join(fuera) + ".")
    siguientes = lista[:len(entran)]
    if {x["expediente"].pk for x in siguientes} != {e.pk for e in entran}:
        primeras = ", ".join(f"{x['expediente'].folio} (lugar {x['lugar']})" for x in siguientes)
        raise ValidationError(f"La reasignación sigue el orden de la lista de espera: corresponden {primeras}.")
    montos = [lugar[e.pk]["monto"] for e in entran]
    disponible = recurso_liberado(ejercicio) + liberado_aqui
    if all(m is not None for m in montos):
        requerido = sum(montos, CERO)
        if requerido > disponible:
            raise ValidationError(f"El recurso liberado sin reasignar ({formato_moneda(disponible)}) no alcanza para "
                                  f"{formato_moneda(requerido)}.")
    return [(e, lugar[e.pk]) for e in entran]


# ----------------------------------------------------------------------------- acuerdos
@registra_usuario
def registrar_acuerdo(usuario, sesion, tipo, descripcion, expedientes, unidad_responsable=None, ministracion=None,
                      periodo="", causa="", aplicar_efecto=True):
    """Registra el acuerdo y aplica su efecto en los listados (baja, reasignación o sustitución).

    ``aplicar_efecto=False``: el acuerdo resuelve una propuesta del área responsable (M6, HU-6.1 y HU-6.2); su efecto se
    aplica al cumplirse (``seguimiento.reasignacion.ejecutar_acuerdo``), no al registrarlo."""
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
    unidad_responsable = unidad_responsable or unidad_sugerida(tipo, sesion.ejercicio)
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
    claves_periodo = periodos_de_reportes(sesion.ejercicio)
    if definicion.get("pide") == "periodo" and claves_periodo and periodo.strip() not in claves_periodo:
        raise ValidationError(f"«{periodo}» no es un periodo de reportes del programa (son {', '.join(claves_periodo)}).")
    if not (descripcion or "").strip():
        raise ValidationError("Escriba el texto del acuerdo.")
    causa = (causa or "").strip()
    if definicion.get("incidente") and not causa:
        raise ValidationError("Indique la causa del incidente (escrito de desistimiento, dictamen, aviso de la Delegación…).")

    accion = efecto(tipo) if aplicar_efecto else "registro"
    salen, entran = [], []
    if accion in ("baja", "sustitucion"):
        con_pago = [f"{e.folio} («{e.estado}»)" for e in expedientes if e.estado.clave in ESTADOS_CON_PAGO]
        if con_pago:
            raise ValidationError("Ya tiene una ministración solicitada o pagada: en lugar de la baja procede el reintegro "
                                  "(acuerdo de reintegro o propuesta del área responsable con el reintegro de lo "
                                  "ministrado): " + ", ".join(con_pago) + ".")
        salen = [e for e in expedientes if e.estado.clave in ESTADOS_CON_BAJA]
    if accion in ("reasignacion", "sustitucion"):
        entran = [e for e in expedientes if e.estado.clave == "lista_espera"]
    if accion in ("baja", "reasignacion", "sustitucion"):
        otros = [f"{e.folio} («{e.estado}»)" for e in expedientes if e not in salen and e not in entran]
        if otros:
            esperado = {"baja": "personas beneficiarias aprobadas",
                        "reasignacion": "solicitudes de la lista de espera",
                        "sustitucion": "la persona beneficiaria que sale y la solicitud de la lista de espera que entra"}[accion]
            raise ValidationError(f"Este acuerdo aplica a {esperado}: " + ", ".join(otros) + ".")
    if accion == "sustitucion" and (not salen or not entran):
        raise ValidationError("En una sustitución sale al menos una persona beneficiaria y entra al menos una solicitud "
                              "de la lista de espera.")
    montos_salen = [monto_aprobado(e) for e in salen]
    liberado = sum((m for m in montos_salen if m is not None), CERO) if salen else None
    entradas = _revisar_entradas(sesion.ejercicio, entran, liberado or CERO) if entran else []
    reasignado = sum((x["monto"] for _, x in entradas if x["monto"] is not None), CERO) if entradas else None

    with transaction.atomic():
        n = sesion.acuerdos.count() + 1
        acuerdo = Acuerdo.objects.create(
            sesion=sesion, numero=f"{sesion.numero}/{n:03d}", tipo=tipo, descripcion=descripcion.strip(),
            unidad_responsable=unidad_responsable, ministracion=ministracion or None, periodo=(periodo or "").strip(),
            causa=causa, monto_liberado=liberado, monto_reasignado=reasignado,
        )
        acuerdo.expedientes.set(expedientes)
        for e in expedientes:
            Evento.registrar(e, usuario, "acuerdo_comite",
                             f"Acuerdo {acuerdo.numero} ({definicion['nombre']}): {acuerdo.descripcion}. "
                             f"Debe cumplirlo: {unidad_responsable.nombre}." + (f" Causa: {causa}." if causa else ""),
                             datos={"acuerdo": acuerdo.pk})
        for e, monto in zip(salen, montos_salen):
            registrar_salida(usuario, e, tipo, monto, acuerdo, motivo=causa or descripcion, referencia=acuerdo.numero,
                             descripcion=f"Acuerdo {acuerdo.numero}: sale de la Lista de Personas Beneficiarias "
                                         f"({definicion['nombre'].split(' (')[0].lower()})"
                                         + (f"; libera {formato_moneda(monto)}" if monto is not None else "") + ".")
        for e, x in entradas:
            e.cambiar_estado("aprobada", usuario, tipo_evento="reasignacion_comite",
                             descripcion=f"Acuerdo {acuerdo.numero}: entra a la Lista de Personas Beneficiarias desde el "
                                         f"lugar {x['lugar']} de la lista de espera"
                                         + (f" con {formato_moneda(x['monto'])}" if x["monto"] is not None else "") + ".",
                             datos={"acuerdo": acuerdo.pk, "lugar": x["lugar"]})
            registrar_entrada(usuario, e, acuerdo, x["lugar"], x["monto"])
    return acuerdo


def acuerdos_pendientes(unidad):
    return (Acuerdo.objects.filter(unidad_responsable=unidad, estado=EstadoAcuerdo.PENDIENTE)
            .select_related("sesion__ejercicio__programa").prefetch_related("expedientes"))


@registra_usuario
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


@registra_usuario
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
    # Con reasignaciones, el acta autoriza publicar a las personas que entran a la Lista de Personas Beneficiarias
    # (si los listados del acta de aprobación ya se publicaron, se publican con esta sesión: M3 HU-3.1).
    sesion.autoriza_publicacion = MovimientoListado.objects.filter(acuerdo__sesion=sesion,
                                                                   movimiento=TipoMovimiento.ENTRA).exists()
    sesion.save()
    return sesion


# ----------------------------------------------------------------------------- convivencia con M3 y M5
def exigir_vigente(expediente, accion):
    """La persona dada de baja por acuerdo del Comité ya no firma, no recibe planta ni cobra."""
    if expediente.estado.clave == "baja":
        mov = (MovimientoListado.objects.filter(expediente=expediente, movimiento=TipoMovimiento.SALE)
               .select_related("acuerdo").order_by("-fecha_hora").first())
        cual = f" (acuerdo {mov.acuerdo.numero})" if mov and mov.acuerdo_id else ""
        raise ValidationError(f"La persona beneficiaria fue dada de baja por acuerdo del Comité{cual}: {accion}.")


def al_liberar_recurso(expediente, usuario):
    """Gancho ``AL_LIBERAR_RECURSO`` (HU-3.3): el monto del contrato sin firma en plazo queda como recurso liberado para
    que el Comité lo reasigne a la lista de espera."""
    if MovimientoListado.objects.filter(expediente=expediente, movimiento=TipoMovimiento.SALE).exists():
        return None
    monto = monto_aprobado(expediente)
    senal = getattr(expediente, "sin_firma", None)
    referencia = senal.acuse_liberacion.folio if senal is not None and senal.acuse_liberacion_id else "Sin firma en plazo"
    mov = MovimientoListado.objects.create(
        acuerdo=None, expediente=expediente, movimiento=TipoMovimiento.SALE, origen="sin_firma", referencia=referencia,
        estado_anterior="sin_firma_en_plazo", estado_nuevo="recurso_liberado", monto=monto, usuario=usuario,
        motivo="Recurso liberado por falta de firma del contrato en plazo (HU-3.3).")
    Evento.registrar(expediente, usuario, "recurso_por_reasignar",
                     "El recurso liberado queda para reasignarse a la lista de espera por acuerdo del Comité"
                     + (f" ({formato_moneda(monto)})." if monto is not None else "."), datos={"movimiento": mov.pk})
    return mov


# ----------------------------------------------------------------------------- PSAHEM y PEG
def ministraciones_sin_instruccion(expediente):
    """PSAHEM: ministraciones del programa que aún no tienen instrucción de pago a la Fiduciaria."""
    numeros = sorted(set(expediente.ejercicio.ministraciones.values_list("numero", flat=True)))
    con_instruccion = set(Acuerdo.objects.filter(tipo="instruccion_pago", expedientes=expediente)
                          .values_list("ministracion", flat=True))
    return [n for n in numeros if n not in con_instruccion]


def periodos_de_reportes(ejercicio):
    """PEG: claves de los periodos de reportes de las reglas (``periodos_reportes``: renglones con ``clave`` o textos)."""
    return [p["clave"] if isinstance(p, dict) else p for p in (ejercicio.datos or {}).get("periodos_reportes", [])]


def periodos_sin_validacion(ejercicio):
    """PEG: periodos de reportes (datos del ejercicio) que aún no tienen validación del Comité."""
    periodos = periodos_de_reportes(ejercicio)
    validados = set(Acuerdo.objects.filter(tipo="validacion_reportes", sesion__ejercicio=ejercicio)
                    .values_list("periodo", flat=True))
    return [p for p in periodos if p not in validados]
