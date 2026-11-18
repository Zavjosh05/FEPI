"""HU-4.2 · Verificación en campo.

- ``config``: lo del programa en ``datos/ejecucion.json`` → ``verificacion.programas`` (quién registra, documentos válidos,
  superficie, sobrevivencia, ajuste mínimo, pago proporcional e incidencias, con su fundamento). PEG no tiene verificación.
- ``registrar_verificacion``: la Delegación del expediente (CC, PS, RHF, PSAHEM: hace la visita) o el área responsable (MFS:
  revisa el entregable; también puede registrarla en los demás) registra el resultado con su documento, la superficie verificada
  y su ajuste respecto de la aprobada, la sobrevivencia donde aplica y las incidencias, cada una con su tipo y el documento que
  la avala. El momento del registro es la **entrega del documento de verificación** al área responsable: con él se califica el
  plazo de las reglas (uso ``entrega_comprobacion``; R-04: plazo de entrega, no de visita). Fuera de plazo se registra igual y
  queda señalado. Deja acuse, bitácora, el hito ``verificacion_campo`` y el estado ``verificada``.
- Resultado: «incumplimiento» si el ajuste queda debajo del mínimo de las reglas (70 %), si la sobrevivencia no alcanza la
  mínima o si hay una incidencia de incumplimiento; «ajuste» si se verificó menos de lo aprobado; si no, «cumple». Una
  incidencia corre ``extensiones.AL_INCIDENCIA`` (gancho de HU-6.2: no se suspende ni se pide reintegro aquí).
- ``ajustar_monto`` (``extensiones.AJUSTES_MONTO``): donde las reglas dicen «o la parte proporcional del porcentaje realizado»
  (CC, PS, RHF), la ministración que depende de la verificación paga la superficie verificada (sin pasar de la aprobada) por el
  monto por hectárea, menos lo ya ministrado, sin bajar de cero; lo ministrado de más queda anotado para HU-6.2 (RHF 8.1.9 b
  fr. 15, línea 3382: la superficie no trabajada se cancela sin poder ser menor al pago de la primera ministración). PSAHEM no
  trae esa frase: paga el 30 % completo (duda para el cliente). MFS y PEG no pagan por superficie.
- ``fuente_verificacion``: soporte ``verificacion_campo`` de ``pagos.solicitudes.FUENTES``.
- ``devolver_comprobacion`` (el área responsable regresa la comprobación con motivo) y ``dar_por_concluida`` (verificada y sin
  ministraciones por pagar).
"""
import hashlib
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from dictamen.comun import exigir_acceso, exigir_programa
from nucleo import extensiones, montos, notificaciones, plazos
from nucleo.acuses import emitir_acuse
from nucleo.models import Evento, TipoUnidad

from .comprobaciones import _fmt, _leer_archivo, datos_ejecucion
from .models import Incidencia, ResultadoVerificacion, Verificacion

CENTAVO = Decimal("0.01")
# Estados en los que todavía no puede existir una verificación (no se consulta la base para ajustar el monto).
SIN_VERIFICACION = {"recibida", "faltantes", "enviada_direccion", "validada", "dictaminada", "aprobada", "lista_espera",
                    "no_factible", "desechada", "publicada", "notificada", "contrato_elaborado", "contrato_en_delegacion",
                    "contratada", "vale_entregado", "planta_entregada", "sin_firma_en_plazo", "recurso_liberado"}


# ----------------------------------------------------------------------------- datos
def _pct(valor):
    """«90», «78.5»: un porcentaje sin ceros de sobra."""
    return f"{Decimal(valor).normalize():f}"


def datos_verificacion():
    return datos_ejecucion()["verificacion"]


def config(expediente):
    """Configuración de la verificación del programa (None si no tiene: PEG)."""
    return datos_verificacion()["programas"].get(expediente.programa.clave)


def documentos(expediente):
    nombres = datos_verificacion()["tipos_documento"]
    return [(c, nombres[c]) for c in (config(expediente) or {}).get("documentos", [])]


def tipos_incidencia(expediente):
    nombres = datos_verificacion()["tipos_incidencia"]
    return [(c, nombres[c]) for c in (config(expediente) or {}).get("incidencias", [])]


def sobrevivencia_minima(expediente):
    cfg = config(expediente) or {}
    if not cfg.get("sobrevivencia"):
        return None
    minimas = cfg.get("sobrevivencia_minima") or {}
    return Decimal(str(minimas[expediente.modalidad.clave])) if expediente.modalidad_id and \
        expediente.modalidad.clave in minimas else None


def vigente(expediente):
    return expediente.verificaciones.order_by("-registrada_en", "-id").first()


def puede_registrar(usuario, expediente):
    """(True, "") o (False, motivo)."""
    cfg = config(expediente)
    if cfg is None:
        return False, f"{expediente.programa.nombre} no tiene verificación en campo: su pago depende de la evaluación de reportes."
    if expediente.estado.clave != "comprobacion_enviada":
        return False, "La verificación se registra cuando la persona ya entregó su comprobación (estado «comprobación enviada»)."
    tipo = usuario.tipo_unidad
    if tipo == TipoUnidad.DIRECCION and usuario.unidad.programas.filter(pk=expediente.programa.pk).exists():
        return True, ""
    if tipo == TipoUnidad.DELEGACION and cfg["registra"] == "delegacion" and usuario.unidad_id == expediente.delegacion_id:
        return True, ""
    quien = "la Delegación del expediente o el área responsable" if cfg["registra"] == "delegacion" else "el área responsable"
    return False, f"La verificación la registra {quien}."


# ----------------------------------------------------------------------------- pago ajustado a lo verificado
def _ministraciones_con_verificacion(expediente, monto):
    from pagos import solicitudes

    return [m.numero for m in monto.ministraciones
            if any(solicitudes.fuente_de(s["clave"]) == "verificacion_campo"
                   for s in solicitudes.soportes_requeridos(expediente, m.numero))]


def calcular_ajuste(expediente, monto, superficie_verificada):
    """``{"total_verificado", "ministracion", "importe", "excedente", "proporcional"}`` o None si no hay ajuste que hacer."""
    cfg = config(expediente) or {}
    if superficie_verificada is None or not monto.por_hectarea or not monto.ministraciones:
        return None
    numeros = _ministraciones_con_verificacion(expediente, monto)
    if not numeros:
        return None
    if not cfg.get("pago_proporcional"):
        return {"proporcional": False, "ministracion": numeros[-1], "total_verificado": None, "importe": None,
                "excedente": None}
    verificada = min(Decimal(superficie_verificada), monto.superficie_ha)
    total_verificado = (verificada * monto.monto_ha).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    numero = numeros[-1]
    otras = sum((m.importe for m in monto.ministraciones if m.numero != numero), Decimal("0"))
    importe = max(Decimal("0"), total_verificado - otras)
    return {"proporcional": True, "ministracion": numero, "total_verificado": total_verificado, "importe": importe,
            "excedente": max(Decimal("0"), otras - total_verificado)}


def ajustar_monto(expediente, monto):
    """``extensiones.AJUSTES_MONTO``: la ministración que depende de la verificación, por lo verificado."""
    if not monto.ministraciones or monto.tipo_monto != montos.POR_HECTAREA:
        return monto
    if not expediente.pk or config(expediente) is None or expediente.estado.clave in SIN_VERIFICACION:
        return monto  # sin consultar la base: antes de la ejecución no puede haber verificación (listas largas)
    v = vigente(expediente)
    if v is None or v.superficie_verificada_ha is None:
        return monto
    cfg = config(expediente)
    if not cfg.get("pago_proporcional"):
        if v.superficie_verificada_ha < monto.superficie_ha:
            monto.nota = (monto.nota + " " if monto.nota else "") + (
                f"Se verificaron {v.superficie_verificada_ha.normalize():f} ha de {monto.superficie_ha.normalize():f}: "
                f"{cfg.get('fundamento_pago', '')}")
        return monto
    calculo = calcular_ajuste(expediente, monto, v.superficie_verificada_ha)
    if calculo is None or not calculo["proporcional"]:
        return monto
    for m in monto.ministraciones:
        if m.numero == calculo["ministracion"] and m.importe != calculo["importe"]:
            m.importe = calculo["importe"]
            m.condicion = (f"Ajustada a lo verificado ({v.superficie_verificada_ha.normalize():f} ha de "
                           f"{monto.superficie_ha.normalize():f}, {_pct(v.ajuste_pct)} %). " + m.condicion)
    monto.ajuste = {**calculo, "superficie_verificada": v.superficie_verificada_ha, "verificacion": v.pk,
                    "fundamento": cfg.get("fundamento_pago", "")}
    if v.superficie_verificada_ha < monto.superficie_ha:
        monto.nota = (monto.nota + " " if monto.nota else "") + (
            f"Ministración {calculo['ministracion']} ajustada a lo verificado: ${calculo['total_verificado']:,.2f} por "
            f"{v.superficie_verificada_ha.normalize():f} ha menos lo ya ministrado ({cfg.get('fundamento_pago', '')}).")
    return monto


# ----------------------------------------------------------------------------- soporte del pago
def fuente_verificacion(expediente, numero):
    """Soporte «verificacion_campo» de ``pagos.solicitudes.FUENTES``."""
    v = vigente(expediente)
    if v is None:
        return (False, "Todavía no se registra la verificación en campo; hasta entonces la ministración no se puede "
                       "solicitar.", "", "")
    if v.resultado == ResultadoVerificacion.INCUMPLIMIENTO and (v.datos or {}).get("aprobada_por_comite"):
        return (True, f"{v.nombre_documento}: sobrevivencia menor a la mínima aprobada por el Comité por causas no imputables "
                      f"(acuerdo {v.datos['aprobada_por_comite']}).", v.acuse.folio if v.acuse else f"Verificación {v.pk}",
                reverse("ejecucion:verificacion_archivo", args=[v.pk]))
    if v.resultado == ResultadoVerificacion.INCUMPLIMIENTO:
        return (False, f"La verificación del {timezone.localtime(v.registrada_en):%d/%m/%Y} registró un incumplimiento: lo "
                       "atiende el área responsable con el seguimiento de incumplimientos.", v.acuse.folio if v.acuse else "",
                reverse("ejecucion:verificacion_archivo", args=[v.pk]))
    if v.ministracion_ajustada == numero and v.importe_ajustado is not None and v.importe_ajustado <= 0:
        return (False, "Con lo verificado no queda importe por pagar en esta ministración.", v.acuse.folio if v.acuse else "",
                reverse("ejecucion:verificacion_archivo", args=[v.pk]))
    texto = f"{v.nombre_documento}, entregado el {timezone.localtime(v.registrada_en):%d/%m/%Y %H:%M} h: {v.get_resultado_display().lower()}"
    if v.ajuste_pct is not None:
        texto += f" ({_pct(v.ajuste_pct)} % de la superficie)"
    return True, texto + ".", v.acuse.folio if v.acuse else f"Verificación {v.pk}", reverse(
        "ejecucion:verificacion_archivo", args=[v.pk])


# ----------------------------------------------------------------------------- registro
def registrar_verificacion(usuario, expediente, tipo_documento, archivo, fecha_visita=None, superficie_verificada=None,
                           sobrevivencia=None, observaciones="", incidencias=(), momento=None):
    """Registra el resultado de la verificación. ``incidencias``: ``[{"tipo", "descripcion", "archivo"}]``."""
    exigir_acceso(usuario, expediente)
    exigir_programa(usuario, expediente)
    expediente.refresh_from_db()
    puede, motivo = puede_registrar(usuario, expediente)
    if not puede:
        raise (ValidationError if expediente.estado.clave != "comprobacion_enviada" or config(expediente) is None
               else PermissionDenied)(motivo)
    cfg = config(expediente)
    docs = dict(documentos(expediente))
    if tipo_documento not in docs:
        raise ValidationError(f"Para {expediente.programa.nombre} el resultado se documenta con: {', '.join(docs.values())}.")
    contenido, nombre_archivo = _leer_archivo(archivo)
    if contenido is None:
        raise ValidationError("Falta el documento de la verificación.")
    ahora = momento or timezone.now()
    hoy = timezone.localtime(ahora).date()
    if fecha_visita and fecha_visita > hoy:
        raise ValidationError("La fecha de la visita no puede ser posterior al registro.")
    monto = montos.monto_si_aprobado(expediente)
    aprobada = monto.superficie_ha if monto is not None and monto.por_hectarea else None
    verificada = ajuste = None
    if cfg.get("superficie") and aprobada is not None:
        if superficie_verificada in (None, ""):
            raise ValidationError("Falta la superficie verificada.")
        verificada = Decimal(str(superficie_verificada))
        if verificada < 0:
            raise ValidationError("La superficie verificada no puede ser negativa.")
        if verificada > aprobada:
            raise ValidationError(f"La superficie verificada no puede ser mayor que la aprobada ({aprobada.normalize():f} ha).")
        ajuste = (verificada * 100 / aprobada).quantize(CENTAVO, rounding=ROUND_HALF_UP) if aprobada else Decimal("0")
    sobre = None
    if cfg.get("sobrevivencia") and sobrevivencia not in (None, ""):
        sobre = Decimal(str(sobrevivencia))
        if not Decimal("0") <= sobre <= Decimal("100"):
            raise ValidationError("La sobrevivencia va de 0 a 100 %.")
    minima_sobre = sobrevivencia_minima(expediente)
    if minima_sobre is not None and sobre is None:
        raise ValidationError(f"Falta la sobrevivencia: en esta modalidad la mínima es {_pct(minima_sobre)} %.")
    tipos_validos = dict(tipos_incidencia(expediente))
    leidas = []
    for inc in incidencias or ():
        if inc.get("tipo") not in tipos_validos:
            raise ValidationError(f"Tipo de incidencia no válido para {expediente.programa.nombre}: {inc.get('tipo')}.")
        if not (inc.get("descripcion") or "").strip():
            raise ValidationError("Cada incidencia necesita su descripción.")
        doc, nombre_doc = _leer_archivo(inc.get("archivo"))
        if doc is None:
            raise ValidationError(f"La incidencia «{tipos_validos[inc['tipo']]}» necesita el documento que la avala.")
        leidas.append((inc["tipo"], inc["descripcion"].strip(), doc, nombre_doc))
    motivos = []
    minimo = cfg.get("ajuste_minimo_pct")
    if ajuste is not None and minimo is not None and ajuste < Decimal(str(minimo)):
        motivos.append(f"el ajuste ({_pct(ajuste)} %) es menor al {minimo} % ({cfg.get('fundamento_ajuste')})")
    if minima_sobre is not None and sobre < minima_sobre:
        motivos.append(f"la sobrevivencia ({_pct(sobre)} %) es menor a la mínima ({_pct(minima_sobre)} %)")
    if any(t == "incumplimiento" for t, *_ in leidas):
        motivos.append("se documentó un incumplimiento")
    if motivos:
        resultado = ResultadoVerificacion.INCUMPLIMIENTO
    elif ajuste is not None and ajuste < 100:
        resultado = ResultadoVerificacion.AJUSTE
    else:
        resultado = ResultadoVerificacion.CUMPLE
    calculo = calcular_ajuste(expediente, montos.monto_aprobado(expediente, superficie=aprobada), verificada) \
        if monto is not None and verificada is not None else None
    v_plazo = plazos.vencimiento(expediente, "entrega_comprobacion")
    comprobacion = expediente.comprobaciones.filter(cambio_estado="comprobacion_enviada").order_by("-enviada_en").first() \
        or expediente.comprobaciones.order_by("-enviada_en").first()
    with transaction.atomic():
        v = Verificacion(
            expediente=expediente, comprobacion=comprobacion, tipo_documento=tipo_documento,
            nombre_documento=docs[tipo_documento][:200], fecha_visita=fecha_visita, superficie_aprobada_ha=aprobada,
            superficie_verificada_ha=verificada, ajuste_pct=ajuste, sobrevivencia_pct=sobre, resultado=resultado,
            observaciones=(observaciones or "").strip(), registrada_por=usuario, unidad=usuario.unidad, registrada_en=ahora,
            huella=hashlib.sha256(contenido).hexdigest(), pago_proporcional=bool(cfg.get("pago_proporcional")),
            datos={"motivos_incumplimiento": motivos})
        if v_plazo is not None:
            v.plazo_texto = f"{v_plazo.nombre}: {v_plazo.texto}"[:300]
            if v_plazo.tiene_fecha:
                v.vence, v.en_plazo = v_plazo.vencimiento, hoy <= v_plazo.vencimiento
        if calculo and calculo["proporcional"]:
            v.total_verificado, v.importe_ajustado = calculo["total_verificado"], calculo["importe"]
            v.ministracion_ajustada, v.excedente_ministrado = calculo["ministracion"], calculo["excedente"]
        v.archivo.save(f"{tipo_documento}_{nombre_archivo}", ContentFile(contenido), save=False)
        v.save()
        creadas = []
        for tipo, descripcion, doc, nombre_doc in leidas:
            i = Incidencia(verificacion=v, expediente=expediente, tipo=tipo, descripcion=descripcion, registrada_en=ahora,
                           huella=hashlib.sha256(doc).hexdigest())
            i.archivo.save(f"{tipo}_{nombre_doc}", ContentFile(doc), save=True)
            creadas.append(i)
        v.acuse = _acuse(v, expediente, cfg, creadas, usuario, motivos)
        v.save(update_fields=["acuse"])
        plazos.registrar_hito(expediente, "verificacion_campo", usuario, ahora, referencia=v.acuse.folio,
                              datos={"verificacion": v.pk, "resultado": resultado})
        Evento.registrar(expediente, usuario, "verificacion_campo",
                         f"Verificación registrada: {v.get_resultado_display().lower()}"
                         + (f", {verificada.normalize():f} ha de {aprobada.normalize():f} ({_pct(ajuste)} %)" if ajuste is not None else "")
                         + f"; {len(creadas)} incidencia(s); entrega del documento {v.situacion_plazo}.",
                         acuse=v.acuse, datos={"verificacion": v.pk})
        expediente.cambiar_estado("verificada", usuario, tipo_evento="verificacion_estado", acuse=v.acuse,
                                  descripcion=f"Resultado de la verificación entregado el {_fmt(ahora)} ({v.acuse.folio}).",
                                  datos={"verificacion": v.pk})
        for incidencia in creadas:
            for funcion in extensiones.AL_INCIDENCIA:
                funcion(incidencia)
    return v


def _acuse(v, expediente, cfg, incidencias, usuario, motivos):
    renglones = [
        ("Expediente", f"{expediente.folio} · {expediente.programa.nombre}"), ("Persona beneficiaria", expediente.beneficiaria.nombre),
        ("Documento", f"{v.nombre_documento} (SHA-256 {v.huella[:16]}…)"),
        ("Fecha y hora de entrega", _fmt(v.registrada_en)), ("Entrega", f"{usuario.get_full_name() or usuario.username}, "
                                                                        f"{usuario.unidad.nombre}"),
    ]
    if v.fecha_visita:
        renglones.append(("Fecha de la visita", f"{v.fecha_visita:%d/%m/%Y}"))
    if v.superficie_verificada_ha is not None:
        renglones += [("Superficie aprobada", f"{v.superficie_aprobada_ha.normalize():f} ha"),
                      ("Superficie verificada", f"{v.superficie_verificada_ha.normalize():f} ha"),
                      ("Ajuste respecto de la aprobada", f"{_pct(v.ajuste_pct)} %")]
    if v.sobrevivencia_pct is not None:
        renglones.append(("Sobrevivencia", f"{_pct(v.sobrevivencia_pct)} %"))
    renglones.append(("Resultado", v.get_resultado_display() + (f": {'; '.join(motivos)}" if motivos else "")))
    renglones.append(("Plazo de entrega", v.plazo_texto + (f" · {v.situacion_plazo.upper()}" if v.en_plazo is not None else "")))
    if v.importe_ajustado is not None:
        renglones.append((f"Ministración {v.ministracion_ajustada}",
                          f"${v.importe_ajustado:,.2f} (lo verificado, ${v.total_verificado:,.2f}, menos lo ya ministrado)"))
    renglones.append(("Fundamento", cfg.get("fundamento", "")))
    detalle = [{"clave": i.nombre_tipo, "texto": f"{i.descripcion} (documento: {i.nombre_archivo})", "estado": "Con documento"}
               for i in incidencias]
    nota = "Fuera de plazo: se registra igual y queda señalado." if v.en_plazo is False else \
        "El plazo de las reglas mide la entrega de este documento, no la visita (R-04)."
    return emitir_acuse(expediente, "verificacion_campo", f"Resultado de la verificación en campo de {expediente.folio}",
                        usuario, renglones, destinatario="Área responsable del programa", detalle=detalle, nota=nota,
                        encabezado_detalle=["Incidencia", "Descripción y documento", "Estado"])


# ----------------------------------------------------------------------------- devolución y conclusión
def devolver_comprobacion(usuario, expediente, motivo):
    """El área responsable regresa la comprobación con observaciones; la Delegación lo notifica a la persona."""
    if usuario.tipo_unidad != TipoUnidad.DIRECCION:
        raise PermissionDenied("Devuelve la comprobación el área responsable del programa.")
    exigir_programa(usuario, expediente)
    if not (motivo or "").strip():
        raise ValidationError("Escriba el motivo de la devolución.")
    with transaction.atomic():
        expediente.cambiar_estado("en_ejecucion", usuario, motivo=motivo, tipo_evento="comprobacion_devuelta",
                                  descripcion=f"Comprobación devuelta con observaciones: {motivo.strip()}")
        notificaciones.emitir_notificacion(expediente, "otro", "Comprobación devuelta con observaciones", usuario,
                                           observaciones=motivo.strip(), destinatario=expediente.beneficiaria,
                                           renglones=[("Observaciones", motivo.strip())])
    return expediente


def ministraciones_pendientes(expediente):
    monto = montos.monto_si_aprobado(expediente)
    if monto is None:
        return []
    pagadas = set(expediente.solicitudes_pago.filter(estado="pagada").values_list("ministracion", flat=True))
    return [m.numero for m in monto.ministraciones if m.numero not in pagadas and m.importe > 0]


def dar_por_concluida(usuario, expediente):
    """Verificado el cumplimiento y sin ministraciones por pagar, el área responsable da por concluidas las actividades."""
    if usuario.tipo_unidad != TipoUnidad.DIRECCION:
        raise PermissionDenied("Da por concluidas las actividades el área responsable del programa.")
    exigir_programa(usuario, expediente)
    expediente.refresh_from_db()
    v = vigente(expediente)
    if expediente.estado.clave != "verificada" or v is None:
        raise ValidationError("Se concluye con la verificación registrada (estado «verificada»).")
    if v.resultado == ResultadoVerificacion.INCUMPLIMIENTO:
        raise ValidationError("La verificación registró un incumplimiento: lo atiende el seguimiento de incumplimientos.")
    pendientes = ministraciones_pendientes(expediente)
    if pendientes:
        raise ValidationError(f"Falta pagar la ministración {pendientes[0]}: solicítela antes de concluir.")
    expediente.cambiar_estado("concluida", usuario, tipo_evento="actividades_concluidas",
                              descripcion=f"Actividades concluidas con la verificación {v.acuse.folio if v.acuse else ''}.")
    return expediente
