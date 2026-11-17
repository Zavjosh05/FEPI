"""HU-5.1 · Solicitud de pago.

- ``emitir_oficio``: la Delegación emite el oficio de solicitud de pago en cuanto el contrato está firmado (acuse y PDF
  con plantilla propia marcada «BORRADOR»: las ROP no traen el formato, R-07).
- ``adjuntar_comprobante``: el comprobante de la cuenta bancaria, donde las reglas lo piden (CC, PS y RHF).
- ``preparar_solicitud`` y ``enviar_solicitud``: el área responsable arma y envía a Administración y Finanzas la solicitud de
  cada ministración con sus soportes (datos por programa y número de ministración en ``datos/pagos.json``). **El servicio**
  impide enviarla si falta un soporte y dice cuál. El importe es el de ``nucleo.montos.monto_aprobado``. El envío deja fecha,
  hora, acuse y el estado ``ministracion_solicitada``; en PSAHEM, además, el hito ``solicitud_pago_fiduciaria`` con el que
  corren los 5 días hábiles de la Secretaría Técnica (ROP PSAHEM 10.1 fr. X, líneas 2290 a 2292).
- Los soportes se comprueban con ``FUENTES``. Ganchos que llenan las historias de M4: ``verificacion_campo`` (HU-4.2,
  verificación en campo), ``entregable`` (HU-4.1, envío de comprobaciones: la Bitácora o la autorización en MFS-ETF, la
  solicitud o el Plan de auditoría en MFS-FSC) y ``evaluacion_reportes`` (HU-4.3; hoy cuenta los periodos que el CASPEG
  validó para el expediente). Al reemplazar la función, la ministración deja de estar bloqueada.
- Los soportes de las ministraciones siguientes pueden depender del régimen de pago (``siguientes_por_regimen``: MFS).
"""
import hashlib
from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from dictamen.comun import exigir_acceso, exigir_programa, exigir_unidad
from nucleo import montos, plazos
from nucleo.acuses import _pdf, emitir_acuse
from nucleo.catalogos import leer_json
from nucleo.models import Consecutivo, Evento, TipoUnidad, Unidad, expedientes_visibles

from .models import ComprobanteCuenta, EstadoSolicitud, OficioPago, SolicitudPago

ESTADOS_PARA_SOLICITAR = ("contratada", "planta_entregada", "pagada", "cheque_entregado")
EN_CURSO = (EstadoSolicitud.ENVIADA, EstadoSolicitud.ACEPTADA, EstadoSolicitud.REMITIDA, EstadoSolicitud.PAGADA)
EXTENSIONES = (".pdf", ".jpg", ".jpeg", ".png")


# ----------------------------------------------------------------------------- datos por programa
@lru_cache(maxsize=2)
def _datos(ruta):
    return leer_json(ruta)


def datos_pagos():
    return _datos(str(settings.DATOS_DIR / "pagos.json"))


def config(expediente):
    """Configuración de pago del programa: ``por_omision`` con lo propio del programa encima."""
    d = datos_pagos()
    cfg = dict(d["por_omision"])
    cfg.update(d["programas"].get(expediente.programa.clave, {}))
    return cfg


def tipo_pago(expediente):
    return config(expediente)["tipo_pago"]


def nombre_tipo_pago(clave):
    return datos_pagos()["tipos_pago"].get(clave, clave)


def soportes_requeridos(expediente, numero):
    """Soportes que pide el programa para esa ministración: ``[{"clave", "nombre", "fundamento"}]``."""
    cfg = config(expediente)["soportes"]
    pedidos = cfg.get(str(numero))
    if pedidos is None and cfg.get("siguientes_por_regimen"):
        regimen = montos.regimen_de_pago(expediente, montos.superficie_aprobada(expediente))
        pedidos = cfg["siguientes_por_regimen"].get(regimen)
    pedidos = pedidos or cfg["siguientes"]
    catalogo = datos_pagos()["soportes"]
    return [{"clave": s["clave"], "nombre": catalogo[s["clave"]]["nombre"], "fundamento": s.get("fundamento", "")}
            for s in pedidos]


# ----------------------------------------------------------------------------- fuentes de los soportes
def _contrato_firmado(exp, numero):
    firma = getattr(exp, "firma_contrato", None)
    if firma is None:
        return False, "Falta el contrato firmado (HU-3.3).", "", ""
    return (True, f"Firmado el {timezone.localtime(firma.firmado_en):%d/%m/%Y %H:%M} h.", firma.contrato.folio,
            reverse("contrato:firma_archivo", args=[exp.folio, "contrato"]))


def _oficio_delegacion(exp, numero):
    oficio = getattr(exp, "oficio_pago", None)
    if oficio is None:
        return False, "La Delegación aún no emite su oficio de solicitud de pago.", "", ""
    return (True, f"Emitido el {timezone.localtime(oficio.emitido_en):%d/%m/%Y %H:%M} h.", oficio.folio,
            reverse("pagos:oficio_pdf", args=[exp.folio]))


def _comprobante_cuenta(exp, numero):
    c = exp.comprobantes_cuenta.first()
    if c is None:
        return False, "Falta el comprobante de la cuenta bancaria.", "", ""
    return (True, f"Recibido el {timezone.localtime(c.subido_en):%d/%m/%Y}.", f"Comprobante {c.pk}",
            reverse("pagos:comprobante", args=[exp.folio, c.pk]))


def _instruccion_comite(exp, numero):
    from dictamen.models import Acuerdo

    a = Acuerdo.objects.filter(tipo="instruccion_pago", expedientes=exp, ministracion=numero).order_by("registrado").first()
    if a is None:
        return False, f"El Comité Técnico aún no instruye el pago de la ministración {numero} a la Fiduciaria (HU-2.4).", "", ""
    return True, f"Acuerdo {a.numero}.", a.numero, ""


def _dictamen(exp, numero):
    from dictamen.comun import resultado_combinado

    resultado, texto = resultado_combinado(exp)
    return resultado == "factible", texto + ".", "", ""


def _verificacion_campo(exp, numero):
    return (False, "Todavía no se registra la verificación en campo (HU-4.2); hasta entonces la ministración no se puede "
                   "solicitar.", "", "")


def _entregable(exp, numero):
    """MFS: Bitácora o autorización (ETF), solicitud o Plan de auditoría (FSC). Gancho de HU-4.1."""
    return (False, "Todavía no se registra la entrega del documento que condiciona esta ministración (HU-4.1, envío de "
                   "comprobaciones); hasta entonces no se puede solicitar.", "", "")


def _evaluacion_reportes(exp, numero):
    """PEG: periodos de reportes que el CASPEG validó para el expediente (acuerdos de HU-2.4); la ministración N pide N.
    HU-4.3 la reemplaza por la evaluación por Guardabosque y por periodo."""
    from dictamen.models import Acuerdo

    periodos = sorted(set(Acuerdo.objects.filter(tipo="validacion_reportes", expedientes=exp).exclude(periodo="")
                          .values_list("periodo", flat=True)))
    if len(periodos) < numero:
        return (False, f"El CASPEG ha validado {len(periodos)} periodo(s) de reportes de este Guardabosque y la ministración "
                       f"{numero} pide {numero} (la evaluación por periodo es HU-4.3).", "", "")
    return True, f"Periodos validados por el CASPEG: {', '.join(periodos)}.", ", ".join(periodos[:numero]), ""


FUENTES = {
    "contrato_firmado": _contrato_firmado, "oficio_delegacion": _oficio_delegacion,
    "comprobante_cuenta": _comprobante_cuenta, "instruccion_comite": _instruccion_comite, "dictamen": _dictamen,
    "verificacion_campo": _verificacion_campo, "entregable": _entregable, "evaluacion_reportes": _evaluacion_reportes,
}  # «entregable» lo reemplaza HU-4.1 (ejecucion/registro.py); HU-4.2 y HU-4.3 reemplazan «verificacion_campo» y «evaluacion_reportes»


def fuente_de(clave):
    """Fuente que comprueba un soporte (``soportes.<clave>.fuente`` de ``datos/pagos.json``; por omisión, la clave)."""
    return datos_pagos()["soportes"].get(clave, {}).get("fuente", clave)


# P-30: la unidad que debe resolver cada soporte que falta
RESPONSABLE = {
    "contrato_firmado": "la Delegación (registra la firma)", "oficio_delegacion": "la Delegación (emite el oficio)",
    "comprobante_cuenta": "la Delegación (recaba el comprobante)", "instruccion_comite": "la Secretaría Técnica del Comité",
    "dictamen": "la Dirección y la Unidad Jurídica", "verificacion_campo": "la Delegación y la Dirección (HU-4.2)",
    "entregable": "la Delegación, que recibe la comprobación (HU-4.1)",
    "evaluacion_reportes": "la Dirección de Protección Forestal y el CASPEG (HU-4.3)",
}


def soportes(expediente, numero):
    """Estado de cada soporte de la ministración: ``[{"clave", "nombre", "fundamento", "cumple", "detalle",
    "referencia", "url"}]``."""
    resultado = []
    for s in soportes_requeridos(expediente, numero):
        cumple, detalle, referencia, url = FUENTES[fuente_de(s["clave"])](expediente, numero)
        resultado.append({**s, "cumple": bool(cumple), "detalle": detalle, "referencia": referencia, "url": url,
                          "responsable": RESPONSABLE.get(s["clave"]) or RESPONSABLE.get(fuente_de(s["clave"]), "el área responsable")})
    return resultado


def faltantes(lista):
    return [s for s in lista if not s["cumple"]]


# ----------------------------------------------------------------------------- consultas
def _unidad(tipo, programa=None):
    qs = Unidad.objects.filter(tipo=tipo)
    if programa is not None and tipo == TipoUnidad.DIRECCION:
        qs = qs.filter(programas=programa)
    return qs.order_by("id").first()


def ministraciones(expediente):
    """Una fila por ministración del monto aprobado: la solicitud (si hay), si se puede solicitar y por qué no, y los soportes."""
    monto = montos.monto_si_aprobado(expediente)
    if monto is None:
        return []
    existentes = {s.ministracion: s for s in expediente.solicitudes_pago.all()}
    filas = []
    for m in monto.ministraciones:
        sol = existentes.get(m.numero)
        puede, motivo = puede_solicitar(expediente, m.numero)
        enviada = sol is not None and sol.estado not in (EstadoSolicitud.BORRADOR, EstadoSolicitud.DEVUELTA)
        lista = sol.soportes if enviada and sol.soportes else soportes(expediente, m.numero)
        filas.append({"numero": m.numero, "porcentaje": m.porcentaje, "importe": m.importe, "condicion": m.condicion,
                      "solicitud": sol, "puede": puede, "motivo": motivo, "soportes": lista,
                      "faltan": faltantes(lista) if not enviada else [], "enviada": enviada})
    return filas


def puede_solicitar(expediente, numero):
    """(True, "") o (False, motivo): lo que no depende de los soportes (contrato, estado, ministración anterior)."""
    monto = montos.monto_si_aprobado(expediente)
    if monto is None:
        return False, "La solicitud todavía no es de una persona beneficiaria."
    ministracion = next((m for m in monto.ministraciones if m.numero == numero), None)
    if ministracion is None:
        return False, f"La solicitud no tiene la ministración {numero}."
    if getattr(expediente, "firma_contrato", None) is None:
        return False, "Sin contrato firmado no se puede solicitar el pago (HU-3.3)."
    existente = expediente.solicitudes_pago.filter(ministracion=numero).first()
    if existente is not None and existente.estado in EN_CURSO:
        return False, f"La ministración {numero} ya está solicitada: {existente.get_estado_display().lower()}."
    for previa in range(1, numero):
        sol = expediente.solicitudes_pago.filter(ministracion=previa).first()
        if sol is None or sol.estado != EstadoSolicitud.PAGADA:
            return False, f"Primero debe pagarse la ministración {previa}."
    if expediente.estado.clave not in ESTADOS_PARA_SOLICITAR:
        return False, f"El expediente está «{expediente.estado}»: no se puede solicitar una ministración en este estado."
    return True, ""


def siguiente_por_solicitar(expediente):
    """La fila de la primera ministración que el área responsable aún puede solicitar (o None)."""
    for fila in ministraciones(expediente):
        if fila["solicitud"] is None or fila["solicitud"].estado in (EstadoSolicitud.BORRADOR, EstadoSolicitud.DEVUELTA):
            return fila
    return None


def por_solicitar(usuario):
    """Para la Dirección: expedientes con una ministración por solicitar o por corregir."""
    filas = []
    qs = expedientes_visibles(usuario).filter(estado__clave__in=ESTADOS_PARA_SOLICITAR, firma_contrato__isnull=False)
    for exp in qs.order_by("fecha_recepcion"):
        fila = siguiente_por_solicitar(exp)
        if fila is not None and fila["puede"]:
            filas.append({"exp": exp, "fila": fila})
    return filas


def sin_oficio(usuario):
    """Para la Delegación: contratos firmados cuyo oficio de solicitud de pago aún no se emite."""
    return (expedientes_visibles(usuario).filter(firma_contrato__isnull=False, oficio_pago__isnull=True)
            .exclude(estado__clave__in=("sin_firma_en_plazo", "recurso_liberado")).order_by("fecha_recepcion"))


def solicitudes_visibles(usuario):
    return SolicitudPago.objects.filter(expediente__in=expedientes_visibles(usuario)).select_related(
        "expediente__predio__municipio", "expediente__ejercicio__programa", "expediente__solicitante",
        "acuse_envio")


def plazo_remision(solicitud):
    """PSAHEM: ``Vencimiento`` de los 5 días hábiles de la Secretaría Técnica para solicitar el pago a la Fiduciaria,
    contados desde que recibe la solicitud del área (ROP PSAHEM 10.1 fr. X, líneas 2290 a 2292); None si el programa no
    tiene ese plazo o la solicitud no se ha enviado."""
    if solicitud.enviada_en is None:
        return None
    return plazos.vencimiento(solicitud.expediente, "instruccion_pago_fiduciaria", fecha_evento=solicitud.enviada_en)


# ----------------------------------------------------------------------------- oficio de la Delegación
def emitir_oficio(usuario, expediente, momento=None):
    """La Delegación del expediente emite el oficio de solicitud de pago (una vez, con el contrato firmado)."""
    exigir_unidad(usuario, TipoUnidad.DELEGACION)
    exigir_acceso(usuario, expediente)
    expediente.refresh_from_db()
    firma = getattr(expediente, "firma_contrato", None)
    if firma is None:
        raise ValidationError("El oficio de solicitud de pago se emite en cuanto el contrato está firmado: este contrato "
                              "todavía no se firma.")
    if expediente.estado.clave in ("sin_firma_en_plazo", "recurso_liberado"):
        raise ValidationError("Este contrato ya no tiene recurso por pagar.")
    if hasattr(expediente, "oficio_pago"):
        raise ValidationError(f"La Delegación ya emitió el oficio {expediente.oficio_pago.folio}.")
    ahora = momento or timezone.now()
    monto = montos.monto_si_aprobado(expediente)
    clave, anio = expediente.programa.clave, expediente.ejercicio.anio
    with transaction.atomic():
        folio = f"OFP-{clave}-{anio}-{Consecutivo.siguiente(f'oficio-pago-{clave}-{anio}'):04d}"
        direccion = _unidad(TipoUnidad.DIRECCION, expediente.programa)
        html = render_to_string("pagos/solicitudes/oficio_pdf.html", {
            "folio": folio, "fecha": timezone.localtime(ahora), "expediente": expediente, "firma": firma,
            "monto": monto, "direccion": direccion, "delegacion": usuario.unidad,
            "tipo_pago": nombre_tipo_pago(tipo_pago(expediente))})
        pdf = _pdf(html)
        oficio = OficioPago(expediente=expediente, folio=folio, emitido_por=usuario, emitido_en=ahora,
                            huella=hashlib.sha256(pdf).hexdigest())
        oficio.archivo.save(f"{folio}.pdf", ContentFile(pdf), save=False)
        oficio.save()
        oficio.acuse = emitir_acuse(
            expediente, "oficio_solicitud_pago", f"Oficio de solicitud de pago {folio}", usuario,
            [("Oficio", folio), ("Solicitud", expediente.folio), ("Persona beneficiaria", expediente.solicitante.nombre),
             ("Contrato firmado", f"{firma.contrato.folio}, el {timezone.localtime(firma.firmado_en):%d/%m/%Y %H:%M} h"),
             ("Monto aprobado", f"${monto.total:,.2f}" if monto else "—"),
             ("Dirigido a", direccion.nombre if direccion else "Área responsable del programa"),
             ("Fecha y hora", f"{timezone.localtime(ahora):%d/%m/%Y %H:%M:%S} h"), ("Emite", usuario.unidad.nombre),
             ("Formato", "BORRADOR: las ROP no traen el formato del oficio (R-07); se usa la plantilla propia del sistema.")],
            destinatario=direccion.nombre if direccion else "", nota="Borrador de formato por validar con el cliente (R-07).")
        oficio.save(update_fields=["acuse"])
        Evento.registrar(expediente, usuario, "oficio_solicitud_pago",
                         f"Oficio de solicitud de pago {folio} emitido por {usuario.unidad.nombre}.", acuse=oficio.acuse,
                         datos={"oficio": oficio.pk})
    return oficio


# ----------------------------------------------------------------------------- comprobante de la cuenta
def adjuntar_comprobante(usuario, expediente, archivo, descripcion="", momento=None):
    """La Delegación (que recibe el documento al firmar) o el área responsable guarda el comprobante de la cuenta bancaria."""
    exigir_unidad(usuario, TipoUnidad.DELEGACION, TipoUnidad.DIRECCION)
    exigir_programa(usuario, expediente)
    exigir_acceso(usuario, expediente)
    if not any(s["clave"] == "comprobante_cuenta" for s in soportes_requeridos(expediente, 1)):
        raise ValidationError(f"{expediente.programa.nombre} no pide comprobante de cuenta bancaria: "
                              f"{config(expediente).get('nota') or 'las reglas no lo piden.'}")
    if archivo is None or not getattr(archivo, "name", ""):
        raise ValidationError("Falta el archivo del comprobante.")
    if not archivo.name.lower().endswith(EXTENSIONES):
        raise ValidationError("El comprobante debe ser PDF, JPG o PNG.")
    archivo.seek(0)
    contenido = archivo.read()
    if not contenido:
        raise ValidationError("El archivo del comprobante está vacío.")
    nombre = archivo.name.rsplit("/", 1)[-1]
    with transaction.atomic():
        c = ComprobanteCuenta(expediente=expediente, descripcion=(descripcion or "").strip(), subido_por=usuario,
                              subido_en=momento or timezone.now(), huella=hashlib.sha256(contenido).hexdigest())
        c.archivo.save(f"comprobante_cuenta_{nombre}", ContentFile(contenido), save=True)
        Evento.registrar(expediente, usuario, "comprobante_cuenta", "Comprobante de la cuenta bancaria recibido.",
                         datos={"comprobante": c.pk})
    return c


# ----------------------------------------------------------------------------- solicitud de la ministración
def _preparar(usuario, expediente, numero, momento=None):
    exigir_unidad(usuario, TipoUnidad.DIRECCION)
    exigir_programa(usuario, expediente)
    exigir_acceso(usuario, expediente)
    expediente.refresh_from_db()
    puede, motivo = puede_solicitar(expediente, numero)
    if not puede:
        raise ValidationError(motivo)
    m = next(x for x in montos.monto_aprobado(expediente).ministraciones if x.numero == numero)
    sol = expediente.solicitudes_pago.filter(ministracion=numero).first()
    if sol is None:
        sol = SolicitudPago.objects.create(
            expediente=expediente, ministracion=numero, porcentaje=m.porcentaje, importe=m.importe,
            tipo_pago=tipo_pago(expediente), preparada_por=usuario, preparada_en=momento or timezone.now())
    else:  # devuelta o por enviar: el importe y el porcentaje se refrescan con el monto aprobado
        sol.porcentaje, sol.importe, sol.tipo_pago = m.porcentaje, m.importe, tipo_pago(expediente)
        sol.save(update_fields=["porcentaje", "importe", "tipo_pago"])
    return sol, m


def preparar_solicitud(usuario, expediente, numero, momento=None):
    """El área responsable abre la solicitud de la ministración (queda «por enviar» con la lista de soportes)."""
    with transaction.atomic():
        sol, _ = _preparar(usuario, expediente, numero, momento)
    return sol


def enviar_solicitud(usuario, expediente, numero, observaciones="", momento=None):
    """Envía la solicitud a Administración y Finanzas con fecha, hora y acuse. No se envía si falta un soporte."""
    with transaction.atomic():
        sol, m = _preparar(usuario, expediente, numero, momento)  # queda «por enviar» aunque falte un soporte
    with transaction.atomic():
        lista = soportes(expediente, numero)
        faltan = faltantes(lista)
        if faltan:
            raise ValidationError("No se puede enviar la solicitud: falta " + "; ".join(
                f"{s['nombre']} ({s['detalle'].rstrip('.')}; lo resuelve {s['responsable']})" for s in faltan) + ".")
        ahora = momento or timezone.now()
        af = _unidad(TipoUnidad.ADMIN_FINANZAS)
        psa = plazos.config_uso(expediente.programa.clave, "instruccion_pago_fiduciaria") is not None
        sol.soportes, sol.estado = [{k: v for k, v in s.items() if k != "url"} for s in lista], EstadoSolicitud.ENVIADA
        sol.enviada_por, sol.enviada_en, sol.envios = usuario, ahora, sol.envios + 1
        sol.observaciones = (observaciones or "").strip()
        sol.save()
        renglones = [
            ("Solicitud de pago", sol.folio), ("Expediente", expediente.folio),
            ("Persona beneficiaria", expediente.solicitante.nombre),
            ("Ministración", f"{numero} ({m.porcentaje:g} %)"), ("Importe", f"${m.importe:,.2f}"),
            ("Forma de pago", nombre_tipo_pago(sol.tipo_pago)),
            ("Fecha y hora del envío", f"{timezone.localtime(ahora):%d/%m/%Y %H:%M:%S} h"),
            ("Envía", usuario.unidad.nombre),
            ("Dirigida a", (af.nombre if af else "Administración y Finanzas")
             + (" y a la Secretaría Técnica del Comité Técnico del FIPASAHEM" if psa else "")),
        ]
        if sol.envios > 1:
            renglones.append(("Envío", f"{sol.envios}.º (corrige la solicitud devuelta)"))
        if sol.observaciones:
            renglones.append(("Observaciones", sol.observaciones))
        detalle = [{"clave": s["referencia"] or "—", "texto": f"{s['nombre']}: {s['detalle']}", "estado": "Adjunto"}
                   for s in lista]
        sol.acuse_envio = emitir_acuse(
            expediente, "solicitud_pago", f"Solicitud de pago {sol.folio}", usuario, renglones,
            destinatario=af.nombre if af else "Administración y Finanzas", detalle=detalle,
            encabezado_detalle=["Referencia", "Soporte", "Estado"])
        sol.save(update_fields=["acuse_envio"])
        if psa:
            plazos.registrar_hito(expediente, "solicitud_pago_fiduciaria", usuario, ahora, referencia=sol.folio,
                                  datos={"solicitud": sol.pk, "ministracion": numero})
        expediente.cambiar_estado(
            "ministracion_solicitada", usuario, tipo_evento="solicitud_pago", acuse=sol.acuse_envio,
            descripcion=f"Ministración {numero} solicitada a Administración y Finanzas ({sol.folio}) el "
                        f"{timezone.localtime(ahora):%d/%m/%Y %H:%M} h, con {len(lista)} soportes.",
            datos={"solicitud": sol.pk, "ministracion": numero})
    return sol
