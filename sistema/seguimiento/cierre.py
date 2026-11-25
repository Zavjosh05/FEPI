"""HU-6.3 · Cierre del ejercicio.

- **Resultados finales** por programa y ejercicio (``resultados_ejercicio``): por expediente con contrato firmado, lo aprobado, lo
  verificado, lo pagado (ministraciones), lo reintegrado y lo liberado, y la **comprobación** (``comprobar_expediente``) que señala
  cada diferencia: pagado mayor que lo aprobado, verificado sin pago, pagado sin la verificación que la regla exige, cancelado
  sin requerimiento resuelto, reintegrado mayor que lo pagado y pago distinto de su solicitud. Las diferencias y su gravedad son
  datos (``datos/seguimiento.json``, ``cierre.diferencias``).
- **Cierre del expediente** (``cerrar_expediente``): con los resultados que cuadran, el área responsable cierra el expediente
  concluido, reintegrado o cancelado sin recurso por devolver, con su acuse (transiciones de ``datos/flujo_tramite.json``).
- **Padrón** de personas beneficiarias (``padron``, ``publicar_padron``): se publica sin cuenta, solo con las columnas que las
  reglas del programa permiten, y se calcula en cada consulta, así que refleja solo las bajas, cancelaciones y sustituciones.
- **Informe anual al Comité** (``enviar_informe``, ``registrar_recepcion``): PDF con los resultados finales y las diferencias, con
  el acuse de su envío (fecha y hora) y el registro de su recepción en una sesión del Comité.
"""
import csv
import hashlib
import io
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q, Sum
from django.template.loader import render_to_string
from django.utils import timezone

from dictamen import seguimiento as dictamen_seguimiento
from dictamen.comun import exigir_programa, exigir_unidad
from dictamen.models import DocumentoSesion, EstadoSesion, SesionComite, TipoMovimiento
from ejecucion import verificacion
from nucleo import acuses, montos
from nucleo.acuses import emitir_acuse
from nucleo.models import Ejercicio, Evento, Expediente, TipoUnidad, Transicion
from nucleo.templatetags.moneda import formato_moneda
from nucleo.trazabilidad import registra_usuario
from pagos import solicitudes

from . import reasignacion
from .models import CierreExpediente, EstadoRequerimiento, InformeAnual, PadronPublicacion

CERO = Decimal("0")
CENTAVO = Decimal("0.01")
EN_PROCESO_DE_PAGO = ("ministracion_solicitada", "remitida_fiduciaria", "cheque_emitido", "cheque_enviado")
SIN_RESOLVER = ("cancelada", "en_devolucion", "reintegrada")
TIPOS_QUE_VEN = (TipoUnidad.DIRECCION, TipoUnidad.SECRETARIA_COMITE, TipoUnidad.JURIDICA, TipoUnidad.ADMIN_FINANZAS)


def datos_cierre():
    return reasignacion.datos_seguimiento()["cierre"]


def _fmt(valor):
    return reasignacion._fmt(valor)


# ----------------------------------------------------------------------------- quién ve qué
def puede_ver(usuario):
    return usuario.is_authenticated and (usuario.tipo_unidad in TIPOS_QUE_VEN or usuario.is_superuser)


def es_area_responsable(usuario, ejercicio):
    return usuario.tipo_unidad == TipoUnidad.DIRECCION and usuario.unidad.programas.filter(pk=ejercicio.programa_id).exists()


def ejercicios_de(usuario):
    """Ejercicios con personas beneficiarias (contrato firmado) que el usuario puede consultar."""
    if not puede_ver(usuario):
        return Ejercicio.objects.none()
    qs = Ejercicio.objects.filter(expedientes__firma_contrato__isnull=False).select_related("programa").distinct()
    if usuario.tipo_unidad == TipoUnidad.DIRECCION:
        qs = qs.filter(programa__in=usuario.unidad.programas.all())
    return qs.order_by("programa__nombre", "-anio")


def expedientes_de(ejercicio):
    """Personas beneficiarias del ejercicio: expedientes con el contrato firmado (aunque luego causen baja)."""
    return (Expediente.objects.filter(ejercicio=ejercicio, firma_contrato__isnull=False)
            .select_related("ejercicio__programa", "predio__municipio", "solicitante", "persona_beneficiaria", "estado",
                            "firma_contrato", "cierre", "modalidad").order_by("folio"))


# ----------------------------------------------------------------------------- montos de un expediente
def pagado(expediente):
    return reasignacion.ministrado(expediente)


def reintegrado(expediente):
    return expediente.requerimientos.filter(estado=EstadoRequerimiento.DEPOSITADO).aggregate(t=Sum("deposito_importe"))["t"] or CERO


def liberado(expediente):
    """Lo que el expediente liberó para la lista de espera (salida de la lista o recurso liberado; HU-2.4 y HU-6.1)."""
    return (expediente.movimientos_listado.filter(movimiento__in=(TipoMovimiento.SALE, TipoMovimiento.LIBERA))
            .aggregate(t=Sum("monto"))["t"] or CERO)


def aprobado(expediente):
    """Lo que el Comité aprobó, sin el ajuste por la verificación (``reasignacion.total_aprobado``)."""
    return reasignacion.total_aprobado(expediente)


def aprobado_ajustado(expediente):
    """El monto aprobado ajustado a lo verificado donde las reglas lo piden (``montos.monto_aprobado``)."""
    return montos.monto_aprobado(expediente).total or CERO


def verificado(expediente):
    """``{"texto", "resultado", "superficie", "importe"}``: la verificación en campo, o la evaluación de reportes en PEG."""
    v = verificacion.vigente(expediente)
    if v is not None:
        texto = v.get_resultado_display()
        if v.superficie_verificada_ha is not None:
            texto += f" · {v.superficie_verificada_ha.normalize():f} ha"
        return {"texto": texto, "resultado": v.resultado, "superficie": v.superficie_verificada_ha, "importe": v.total_verificado}
    total = expediente.evaluaciones_periodo.count()
    if total:
        cumple = expediente.evaluaciones_periodo.filter(resultado="cumple").count()
        return {"texto": f"{cumple} de {total} periodos de reportes cumplen", "resultado": "reportes", "superficie": None,
                "importe": None}
    return {"texto": "Sin verificación", "resultado": "", "superficie": None, "importe": None}


# ----------------------------------------------------------------------------- comprobación
def _diferencia(clave, detalle):
    d = datos_cierre()["diferencias"][clave]
    return {"clave": clave, "nombre": d["nombre"], "gravedad": d["gravedad"], "texto": d["texto"], "detalle": detalle}


def requerimiento_resuelto(expediente):
    """El requerimiento de devolución está depositado o resuelto sin monto (o no hay nada que devolver)."""
    if expediente.requerimientos.filter(estado__in=(EstadoRequerimiento.DEPOSITADO, EstadoRequerimiento.SIN_MONTO)).exists():
        return True
    return not expediente.requerimientos.exists() and pagado(expediente) <= 0


def comprobar_expediente(expediente, pagado_=None, aprobado_=None, reintegrado_=None):
    """Diferencias entre lo aprobado, verificado, pagado y reintegrado del expediente (vacía si todo cuadra)."""
    pagado_ = pagado(expediente) if pagado_ is None else pagado_
    reintegrado_ = reintegrado(expediente) if reintegrado_ is None else reintegrado_
    ajustado = aprobado_ajustado(expediente) if aprobado_ is None else aprobado_
    clave_estado = expediente.estado.clave
    cierre = getattr(expediente, "cierre", None)
    difs = []
    if (pagado_ - reintegrado_) - ajustado > CENTAVO / 2:
        difs.append(_diferencia("pagado_mayor_aprobado", f"Pagado {formato_moneda(pagado_)}"
                                + (f", reintegrado {formato_moneda(reintegrado_)}" if reintegrado_ else "")
                                + f"; aprobado {formato_moneda(ajustado)}."))
    planta = expediente.requerimientos.filter(estado=EstadoRequerimiento.DEPOSITADO).aggregate(t=Sum("monto_planta"))["t"] or CERO
    if reintegrado_ - pagado_ - planta > CENTAVO / 2:
        difs.append(_diferencia("reintegrado_mayor_pagado", f"Reintegrado {formato_moneda(reintegrado_)}; pagado {formato_moneda(pagado_)}"
                                + (f" más {formato_moneda(planta)} de planta no establecida." if planta else ".")))
    v = verificacion.vigente(expediente)
    en_curso = (clave_estado in EN_PROCESO_DE_PAGO or clave_estado in SIN_RESOLVER or clave_estado in ("recurso_liberado", "baja")
                or (cierre is not None and cierre.tipo != "con_resultados"))
    if v is not None and not en_curso and (v.resultado != "incumplimiento" or (v.datos or {}).get("aprobada_por_comite")):
        faltan = verificacion.ministraciones_pendientes(expediente)
        if faltan:
            difs.append(_diferencia("verificado_sin_pago", f"Falta pagar la ministración {faltan[0]}."))
    for sol in expediente.solicitudes_pago.filter(estado="pagada").order_by("ministracion"):
        sin = [s["nombre"] for s in solicitudes.soportes_requeridos(expediente, sol.ministracion)
               if solicitudes.fuente_de(s["clave"]) in ("verificacion_campo", "evaluacion_reportes")
               and not solicitudes.FUENTES[solicitudes.fuente_de(s["clave"])](expediente, sol.ministracion)[0]]
        if sin:
            difs.append(_diferencia("pagado_sin_verificacion", f"Ministración {sol.ministracion} pagada sin: {'; '.join(sin)}."))
            break
    if (clave_estado in SIN_RESOLVER or (cierre is not None and cierre.tipo in ("reintegrada", "sin_recurso"))) \
            and not requerimiento_resuelto(expediente):
        difs.append(_diferencia("cancelado_sin_requerimiento", f"Se ministraron {formato_moneda(pagado_)}; el requerimiento "
                                                                 "no está depositado ni resuelto sin monto."))
    for pago in expediente.pagos.select_related("solicitud"):
        if pago.importe != pago.solicitud.importe:
            difs.append(_diferencia("pago_distinto_solicitud", f"Ministración {pago.ministracion}: pagado "
                                    f"{formato_moneda(pago.importe)}, solicitado {formato_moneda(pago.solicitud.importe)}."))
            break
    return difs


def hay_errores(diferencias):
    return any(d["gravedad"] == "error" for d in diferencias)


def resultado_expediente(expediente):
    """Una fila de los resultados finales: aprobado, verificado, pagado, reintegrado, liberado y diferencias."""
    p, r = pagado(expediente), reintegrado(expediente)
    ap, aj = aprobado(expediente), aprobado_ajustado(expediente)
    difs = comprobar_expediente(expediente, p, aj, r)
    cierre = getattr(expediente, "cierre", None)
    puede, motivo = puede_cerrar(expediente, difs)
    return {"expediente": expediente, "folio": expediente.folio, "persona": expediente.beneficiaria.nombre,
            "municipio": expediente.predio.municipio.nombre, "estado": expediente.estado, "aprobado": ap, "ajustado": aj,
            "verificado": verificado(expediente), "pagado": p, "reintegrado": r, "liberado": liberado(expediente),
            "diferencias": difs, "cierre": cierre, "puede_cerrar": puede and cierre is None, "motivo_no_cierra": motivo,
            "situacion": situacion_en_padron(expediente)[0]}


def resultados_ejercicio(ejercicio):
    filas = [resultado_expediente(e) for e in expedientes_de(ejercicio)]
    total = {k: sum((f[k] for f in filas), CERO) for k in ("aprobado", "ajustado", "pagado", "reintegrado", "liberado")}
    recurso = dictamen_seguimiento.totales_recurso(ejercicio)
    total["reasignado"] = recurso["reasignado"]
    total["por_reasignar"] = max(CERO, recurso["liberado"] - recurso["reasignado"])
    total["cerrados"] = sum(1 for f in filas if f["cierre"] is not None)
    total["expedientes"] = len(filas)
    total["con_diferencias"] = sum(1 for f in filas if f["diferencias"])
    total["listos"] = sum(1 for f in filas if f["puede_cerrar"])
    return filas, total


# ----------------------------------------------------------------------------- cierre del expediente
def _hay_transicion(expediente, destino):
    return Transicion.objects.filter(origen=expediente.estado, destino__clave=destino).filter(
        Q(programa__isnull=True) | Q(programa=expediente.programa)).exists()


def puede_cerrar(expediente, diferencias=None):
    """(True, "") o (False, motivo): se cierra si los resultados cuadran y está en un estado desde el que se cierra."""
    cfg = datos_cierre()["cierre_expediente"]
    clave = expediente.estado.clave
    if clave == "ejercicio_cerrado":
        return False, "Ya está cerrado."
    if clave not in cfg["desde"] and clave not in cfg["concluir_desde"]:
        return False, f"Se cierra cuando está concluido, reintegrado o cancelado sin recurso por devolver (hoy: «{expediente.estado}»)."
    difs = comprobar_expediente(expediente) if diferencias is None else diferencias
    if hay_errores(difs):
        return False, "Hay diferencias entre lo aprobado, verificado, pagado y reintegrado: " + "; ".join(d["nombre"] for d in difs) + "."
    if clave == "cancelada" and not expediente.requerimientos.filter(estado=EstadoRequerimiento.SIN_MONTO).exists() \
            and not (not expediente.requerimientos.exists() and pagado(expediente) <= 0):
        return False, "El expediente cancelado se cierra cuando el requerimiento queda sin recurso por devolver."
    if clave in cfg["concluir_desde"]:
        pendientes = verificacion.ministraciones_pendientes(expediente)
        if pendientes:
            return False, f"Falta pagar la ministración {pendientes[0]}."
        v = verificacion.vigente(expediente)
        if v is not None and v.resultado == "incumplimiento" and not (v.datos or {}).get("aprobada_por_comite"):
            return False, "La verificación registró un incumplimiento: lo atiende el seguimiento de incumplimientos."
        if clave == "verificada" and v is None:
            return False, "Falta la verificación."
        if not _hay_transicion(expediente, "concluida"):
            return False, f"Desde «{expediente.estado}» no hay cierre para este programa."
    return True, ""


@registra_usuario
def cerrar_expediente(usuario, expediente, momento=None):
    """El área responsable cierra el expediente: pasa por «concluida» si hace falta, queda ``ejercicio_cerrado`` con su acuse y la
    copia de los resultados finales."""
    exigir_unidad(usuario, TipoUnidad.DIRECCION)
    exigir_programa(usuario, expediente)
    cfg = datos_cierre()["cierre_expediente"]
    ahora = momento or timezone.now()
    with transaction.atomic():
        expediente.refresh_from_db()
        if CierreExpediente.objects.filter(expediente=expediente).exists():
            raise ValidationError("El expediente ya está cerrado.")
        puede, motivo = puede_cerrar(expediente)
        if not puede:
            raise ValidationError(motivo)
        clave = expediente.estado.clave
        if clave in cfg["concluir_desde"]:
            expediente.cambiar_estado("concluida", usuario, tipo_evento="actividades_concluidas",
                                      descripcion="Actividades concluidas: las ministraciones están pagadas y los resultados cuadran.")
            clave = "concluida"
        tipo = cfg["desde"][clave]
        fila = resultado_expediente(expediente)
        resumen = {"aprobado": str(fila["aprobado"]), "ajustado": str(fila["ajustado"]), "verificado": fila["verificado"]["texto"],
                   "pagado": str(fila["pagado"]), "reintegrado": str(fila["reintegrado"]), "liberado": str(fila["liberado"])}
        texto = cfg["tipos"][tipo]
        acuse = emitir_acuse(
            expediente, "cierre_expediente", f"Cierre del expediente · {expediente.folio}", usuario,
            [("Expediente", expediente.folio), ("Cierre", texto), ("Aprobado", formato_moneda(fila["aprobado"])),
             ("Verificado", fila["verificado"]["texto"]), ("Pagado", formato_moneda(fila["pagado"])),
             ("Reintegrado", formato_moneda(fila["reintegrado"])), ("Recurso liberado", formato_moneda(fila["liberado"])),
             ("Cierra", usuario.unidad.nombre), ("Fecha y hora", _fmt(ahora))],
            destinatario=expediente.beneficiaria.nombre, nota=cfg["fundamento"])
        expediente.cambiar_estado("ejercicio_cerrado", usuario, motivo=texto + ".", tipo_evento="cierre_expediente", acuse=acuse,
                                  descripcion=f"{texto}. Aprobado {formato_moneda(fila['aprobado'])}, pagado "
                                              f"{formato_moneda(fila['pagado'])}, reintegrado {formato_moneda(fila['reintegrado'])}.")
        CierreExpediente.objects.create(expediente=expediente, tipo=tipo, resumen=resumen, motivo=texto, cerrado_por=usuario,
                                        cerrado_en=ahora, acuse=acuse)
    return expediente


@registra_usuario
def cerrar_listos(usuario, ejercicio, momento=None):
    """Cierra todos los expedientes del ejercicio que ya cuadran; regresa (cerrados, omitidos con su motivo)."""
    exigir_unidad(usuario, TipoUnidad.DIRECCION)
    if not es_area_responsable(usuario, ejercicio):
        raise PermissionDenied("Su Dirección no es Instancia Ejecutora de este programa.")
    cerrados, omitidos = [], []
    for e in expedientes_de(ejercicio).exclude(estado__clave="ejercicio_cerrado"):
        if not puede_cerrar(e)[0]:
            continue
        try:
            cerrar_expediente(usuario, e, momento)
            cerrados.append(e)
        except (ValidationError, PermissionDenied) as err:
            omitidos.append((e, "; ".join(getattr(err, "messages", [str(err)]))))
    return cerrados, omitidos


# ----------------------------------------------------------------------------- padrón
def situacion_en_padron(expediente):
    """(clave, texto): vigente, suspendida, baja o cancelada."""
    clave = expediente.estado.clave
    cierre = getattr(expediente, "cierre", None)
    if clave in SIN_RESOLVER or (cierre is not None and cierre.tipo in ("reintegrada", "sin_recurso")):
        return "cancelada", "Baja por cancelación del apoyo"
    if clave in ("recurso_liberado", "baja"):
        return "baja", ("Baja por contrato sin firma en plazo" if clave == "recurso_liberado"
                        else "Baja de la Lista de Personas Beneficiarias (desistimiento, fallecimiento o caso fortuito)")
    if clave == "suspendida":
        return "suspendida", "Apoyo suspendido temporalmente"
    return "vigente", "Vigente"


def config_padron(ejercicio):
    cfg = datos_cierre()["padron"]
    programa = cfg["programas"].get(ejercicio.programa.clave) or next(iter(cfg["programas"].values()))
    return {**programa, "catalogo": cfg["columnas"], "fundamento_general": cfg["fundamento_general"],
            "no_se_publica": cfg["no_se_publica"]}


def _fila_padron(e, columnas):
    sit = situacion_en_padron(e)
    valores = {"folio": e.folio, "persona": e.beneficiaria.nombre, "nucleo": e.solicitante.nombre, "predio": e.predio.nombre,
               "municipio": e.predio.municipio.nombre, "modalidad": e.modalidad.nombre if e.modalidad_id else "—",
               "situacion": sit[1], "alta": timezone.localtime(e.firma_contrato.firmado_en).date()}
    if "monto" in columnas:
        valores["monto"] = aprobado(e)
    fila = {c: valores[c] for c in columnas}
    fila["situacion_clave"] = sit[0]
    fila["celdas"] = [formato_moneda(v) if c == "monto" else (f"{v:%d/%m/%Y}" if c == "alta" else v) for c, v in fila.items()
                      if c in columnas]
    return fila


def movimientos(ejercicio):
    """Altas, bajas y sustituciones del padrón: ``[{"fecha", "tipo", "folio", "detalle"}]`` por fecha."""
    from dictamen.models import Acuerdo

    exps = list(expedientes_de(ejercicio))
    por_pk = {e.pk: e for e in exps}
    filas = [{"fecha": timezone.localtime(e.firma_contrato.firmado_en).date(), "tipo": "Alta", "folio": e.folio,
              "detalle": "Incorporación al padrón con el contrato firmado."} for e in exps]
    eventos = list(Evento.objects.filter(expediente__in=exps, tipo__in=("sustitucion_beneficiaria", "baja_por_acuerdo", "cancelacion")))
    acuerdos = Acuerdo.objects.in_bulk([ev.datos.get("acuerdo") for ev in eventos if ev.datos.get("acuerdo")])
    for ev in eventos:
        a = acuerdos.get(ev.datos.get("acuerdo"))
        cita = f" (acuerdo {a.numero})" if a else ""
        exp = por_pk[ev.expediente_id]
        fecha = timezone.localtime(ev.fecha_hora).date()
        if ev.tipo == "sustitucion_beneficiaria":
            filas.append({"fecha": fecha, "tipo": "Sustitución", "folio": exp.folio,
                          "detalle": f"Sustitución de la persona Guardabosque del núcleo {exp.solicitante.nombre}{cita}."})
        else:
            filas.append({"fecha": fecha, "tipo": "Baja", "folio": exp.folio, "detalle": f"Baja del padrón por acuerdo del Comité{cita}."})
    return sorted(filas, key=lambda f: (f["fecha"], f["folio"], f["tipo"]))


def padron(ejercicio):
    """El padrón tal como está hoy: filas, columnas, movimientos (si las reglas los piden) y el último movimiento."""
    cfg = config_padron(ejercicio)
    columnas = cfg["columnas"]
    exps = list(expedientes_de(ejercicio))
    filas = [_fila_padron(e, columnas) for e in exps]
    ultimo = (Evento.objects.filter(expediente__in=exps).filter(Q(estado_destino__isnull=False) | Q(tipo="sustitucion_beneficiaria"))
              .order_by("-fecha_hora").values_list("fecha_hora", flat=True).first())
    return {"filas": filas, "columnas": [(c, cfg["catalogo"][c]) for c in columnas],
            "movimientos": movimientos(ejercicio) if cfg.get("movimientos") else [], "ultimo_movimiento": ultimo,
            "config": cfg, "vigentes": sum(1 for f in filas if f["situacion_clave"] in ("vigente", "suspendida"))}


def _celda(valor):
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return f"{valor:.2f}" if isinstance(valor, Decimal) else valor


def padron_csv(ejercicio):
    """El padrón en CSV (UTF-8 con marca de orden de bytes para Excel); lleva solo las columnas publicables."""
    p = padron(ejercicio)
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow([nombre for _, nombre in p["columnas"]])
    for f in p["filas"]:
        escritor.writerow([_celda(f[c]) for c, _ in p["columnas"]])
    if p["movimientos"]:
        escritor.writerow([])
        escritor.writerow(["Movimientos", "Fecha", "Folio", "Detalle"])
        for m in p["movimientos"]:
            escritor.writerow([m["tipo"], m["fecha"].isoformat(), m["folio"], m["detalle"]])
    return "﻿" + salida.getvalue()


def padron_publicado(ejercicio):
    return PadronPublicacion.objects.filter(ejercicio=ejercicio).select_related("acuse").first()


def padrones_publicos():
    return PadronPublicacion.objects.select_related("ejercicio__programa").order_by("ejercicio__programa__nombre", "-ejercicio__anio")


@registra_usuario
def publicar_padron(usuario, ejercicio, momento=None):
    """El área responsable publica el padrón: desde entonces la página pública lo muestra y se actualiza sola."""
    exigir_unidad(usuario, TipoUnidad.DIRECCION)
    if not es_area_responsable(usuario, ejercicio):
        raise PermissionDenied("Su Dirección no es Instancia Ejecutora de este programa.")
    if padron_publicado(ejercicio) is not None:
        raise ValidationError("El padrón de este programa y ejercicio ya está publicado; la página se actualiza sola.")
    if not expedientes_de(ejercicio).exists():
        raise ValidationError("Todavía no hay personas beneficiarias con contrato firmado.")
    cfg = config_padron(ejercicio)
    ahora = momento or timezone.now()
    fundamento = f"{ejercicio.programa.clave} {cfg['numeral']} (línea {cfg['linea']})"
    columnas = ", ".join(cfg["catalogo"][c] for c in cfg["columnas"])
    with transaction.atomic():
        acuse = emitir_acuse(
            None, "padron_publicado", f"Publicación del padrón · {ejercicio.programa.nombre} {ejercicio.anio}", usuario,
            [("Programa y ejercicio", f"{ejercicio.programa.nombre} {ejercicio.anio}"), ("Columnas publicadas", columnas),
             ("No se publica", ", ".join(cfg["no_se_publica"])), ("Fundamento", fundamento),
             ("Publica", usuario.unidad.nombre), ("Fecha y hora", _fmt(ahora))],
            referencia=f"Padrón {ejercicio.programa.clave} {ejercicio.anio}", nota=cfg["fundamento_general"]["texto"])
        return PadronPublicacion.objects.create(ejercicio=ejercicio, publicada_por=usuario, publicada_en=ahora, acuse=acuse,
                                                fundamento=fundamento)


# ----------------------------------------------------------------------------- informe anual al Comité
def config_informe(ejercicio):
    cfg = datos_cierre()["informe"]
    return {**cfg["programas"].get(ejercicio.programa.clave, {}), "destinatario": cfg["destinatario"], "plazo": cfg["plazo"]}


def nombre_comite(ejercicio):
    instancias = (ejercicio.datos or {}).get("instancias") or {}
    for clave in ("comite", "comite_tecnico"):
        valor = instancias.get(clave)
        if isinstance(valor, dict) and valor.get("nombre"):
            return valor["nombre"].split(" (Fideicomiso")[0]
    return "Comité del programa"


def informe_de(ejercicio):
    return InformeAnual.objects.filter(ejercicio=ejercicio).select_related("acuse", "sesion", "acuse_recepcion").first()


def informes_por_recibir():
    return InformeAnual.objects.filter(recibido_en__isnull=True).select_related("ejercicio__programa", "acuse")


def _resumen_informe(filas, total):
    claves = ("aprobado", "ajustado", "pagado", "reintegrado", "liberado", "reasignado", "por_reasignar")
    return {"totales": {k: str(total[k]) for k in claves}, "expedientes": total["expedientes"], "cerrados": total["cerrados"],
            "con_diferencias": total["con_diferencias"],
            "diferencias": [{"folio": f["folio"], "nombre": d["nombre"], "detalle": d["detalle"]} for f in filas for d in f["diferencias"]]}


@registra_usuario
def enviar_informe(usuario, ejercicio, momento=None):
    """El área responsable envía el informe anual al Comité: genera el PDF con los resultados finales y las diferencias y registra la
    fecha y la hora del envío con su acuse."""
    exigir_unidad(usuario, TipoUnidad.DIRECCION)
    if not es_area_responsable(usuario, ejercicio):
        raise PermissionDenied("Su Dirección no es Instancia Ejecutora de este programa.")
    if informe_de(ejercicio) is not None:
        raise ValidationError("El informe anual de este programa y ejercicio ya se envió al Comité.")
    filas, total = resultados_ejercicio(ejercicio)
    if not filas:
        raise ValidationError("Todavía no hay resultados finales que informar: ninguna persona beneficiaria con contrato firmado.")
    ahora = momento or timezone.now()
    cfg = config_informe(ejercicio)
    comite = nombre_comite(ejercicio)
    html = render_to_string("seguimiento/cierre/informe_pdf.html", {
        "ejercicio": ejercicio, "filas": filas, "total": total, "cfg": cfg, "comite": comite, "fecha": timezone.localtime(ahora),
        "usuario": usuario, "padron": padron_publicado(ejercicio), "diferencias": [(f, d) for f in filas for d in f["diferencias"]]})
    contenido = acuses._pdf(html)
    with transaction.atomic():
        acuse = emitir_acuse(
            None, "informe_anual", f"Envío del informe anual al Comité · {ejercicio.programa.nombre} {ejercicio.anio}", usuario,
            [("Programa y ejercicio", f"{ejercicio.programa.nombre} {ejercicio.anio}"), ("Destinatario", comite),
             ("Personas beneficiarias", total["expedientes"]), ("Expedientes cerrados", total["cerrados"]),
             ("Aprobado", formato_moneda(total["aprobado"])), ("Pagado", formato_moneda(total["pagado"])),
             ("Reintegrado", formato_moneda(total["reintegrado"])), ("Expedientes con diferencias", total["con_diferencias"]),
             ("Fundamento", f"{ejercicio.programa.clave} {cfg.get('numeral', '')} (línea {cfg.get('linea', '')})"),
             ("Envía", usuario.unidad.nombre), ("Fecha y hora del envío", _fmt(ahora))],
            destinatario=comite, referencia=f"Informe anual {ejercicio.programa.clave} {ejercicio.anio}", nota=cfg.get("texto", ""))
        informe = InformeAnual(ejercicio=ejercicio, resumen=_resumen_informe(filas, total), enviado_por=usuario, enviado_en=ahora,
                               acuse=acuse, huella=hashlib.sha256(contenido).hexdigest())
        informe.archivo.save(f"informe_anual_{ejercicio.programa.clave}_{ejercicio.anio}.pdf", ContentFile(contenido), save=False)
        informe.save()
    return informe


def sesiones_para_informe(informe):
    return SesionComite.objects.filter(ejercicio__programa=informe.ejercicio.programa).order_by("-fecha_hora")


@registra_usuario
def registrar_recepcion(usuario, informe, sesion=None, observaciones="", momento=None):
    """La Secretaría Técnica registra que recibió el informe y, si lo indica, la sesión del Comité en que se presenta."""
    exigir_unidad(usuario, TipoUnidad.SECRETARIA_COMITE)
    if informe.recibido_en is not None:
        raise ValidationError("La recepción del informe ya está registrada.")
    if sesion is not None and sesion.ejercicio.programa_id != informe.ejercicio.programa_id:
        raise ValidationError("La sesión debe ser del Comité del mismo programa.")
    ahora = momento or timezone.now()
    ej = informe.ejercicio
    with transaction.atomic():
        acuse = emitir_acuse(
            None, "informe_recibido", f"Recepción del informe anual · {ej.programa.nombre} {ej.anio}", usuario,
            [("Programa y ejercicio", f"{ej.programa.nombre} {ej.anio}"), ("Informe enviado", _fmt(informe.enviado_en)),
             ("Acuse del envío", informe.acuse.folio if informe.acuse_id else "—"),
             ("Sesión del Comité", f"{sesion.numero} ({timezone.localtime(sesion.fecha_hora):%d/%m/%Y})" if sesion else "Sin sesión indicada"),
             ("Recibe", usuario.unidad.nombre), ("Fecha y hora de la recepción", _fmt(ahora))],
            referencia=f"Informe anual {ej.programa.clave} {ej.anio}", destinatario=nombre_comite(ej), nota=observaciones or "")
        informe.recibido_por, informe.recibido_en, informe.sesion = usuario, ahora, sesion
        informe.acuse_recepcion, informe.observaciones = acuse, (observaciones or "").strip()
        informe.save()
        if sesion is not None and sesion.estado != EstadoSesion.CELEBRADA \
                and not sesion.documentos.filter(nombre=f"Informe anual {ej.programa.clave} {ej.anio}").exists():
            with informe.archivo.open("rb") as f:
                DocumentoSesion.objects.create(sesion=sesion, nombre=f"Informe anual {ej.programa.clave} {ej.anio}", registrado_por=usuario,
                                               archivo=ContentFile(f.read(), name=f"informe_anual_{ej.programa.clave}_{ej.anio}.pdf"))
    return informe


# ----------------------------------------------------------------------------- estado del cierre del ejercicio
def estado_cierre(ejercicio, total=None):
    """Lo que falta para cerrar el ejercicio: expedientes, padrón, informe y su recepción."""
    if total is None:
        _, total = resultados_ejercicio(ejercicio)
    informe = informe_de(ejercicio)
    pasos = [("expedientes", f"Expedientes cerrados: {total['cerrados']} de {total['expedientes']}",
              total["cerrados"] == total["expedientes"] > 0),
             ("padron", "Padrón publicado", padron_publicado(ejercicio) is not None),
             ("informe", "Informe anual enviado al Comité", informe is not None),
             ("recepcion", "Recepción registrada por la Secretaría Técnica", informe is not None and informe.recibido_en is not None)]
    return {"pasos": pasos, "cerrado": all(p[2] for p in pasos)}


# ----------------------------------------------------------------------------- exportación
def resultados_csv(ejercicio):
    filas, total = resultados_ejercicio(ejercicio)
    salida = io.StringIO()
    e = csv.writer(salida)
    e.writerow(["Folio", "Persona beneficiaria", "Municipio", "Estado", "Aprobado", "Aprobado ajustado a lo verificado", "Verificado",
                "Pagado", "Reintegrado", "Liberado", "Cierre", "Diferencias"])
    for f in filas:
        e.writerow([f["folio"], f["persona"], f["municipio"], f["estado"].nombre, f"{f['aprobado']:.2f}", f"{f['ajustado']:.2f}",
                    f["verificado"]["texto"], f"{f['pagado']:.2f}", f"{f['reintegrado']:.2f}", f"{f['liberado']:.2f}",
                    f["cierre"].motivo if f["cierre"] else "", " | ".join(f"{d['nombre']}: {d['detalle']}" for d in f["diferencias"])])
    e.writerow(["TOTAL", "", "", "", f"{total['aprobado']:.2f}", f"{total['ajustado']:.2f}", "", f"{total['pagado']:.2f}",
                f"{total['reintegrado']:.2f}", f"{total['liberado']:.2f}", f"{total['cerrados']} de {total['expedientes']} cerrados",
                f"{total['con_diferencias']} con diferencias"])
    return "﻿" + salida.getvalue()
