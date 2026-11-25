"""HU-3.4 · Entrega de planta (solo PS y RHF).

- ``emitir_vale``: la Delegación emite el Vale de Planta al expediente con derecho a planta: especie(s) y cantidad
  (el sistema propone la planta por hectárea de las reglas por la superficie aprobada; quien emite puede ajustarla dejando
  motivo), vivero que entrega, fecha y hora de entrega con su acuse y el hito ``entrega_vale``. Antes de la firma del
  contrato exige la carta compromiso (PS 8.1.6 inciso f, línea 5908; RHF 8.1.6 inciso g, línea 3248). RHF modalidad uno no
  recibe planta.
- **Vigencia** de las reglas (``plazos.vencimiento(exp, "recoger_planta")``): PS, 30 días (naturales, R-13); RHF, 15 días
  hábiles. Un vale vencido no es válido: el vivero no puede registrar salida con él.
- **Reposición** como dato por programa (``datos/contrato.json`` → ``vale_de_planta.<CLAVE>.reposicion``): RHF sí (8.1.7
  inciso e, líneas 3280 a 3283: se expide uno nuevo si hay planta disponible; cubre solo lo no entregado); PS no la prevé
  (8.1.7 inciso e, líneas 5931 y 5932, R-13).
- ``registrar_salida``: el personal del vivero valida el vale y registra cada salida con especie, cantidad, fecha y hora y
  acuse; hay salidas parciales y nunca más de lo autorizado por especie. Al completarse el vale el expediente pasa a
  ``planta_entregada`` (si el contrato ya estaba firmado).
"""
import hashlib
import math
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from dictamen.comun import exigir_acceso, exigir_unidad
from dictamen.seguimiento import exigir_vigente
from nucleo import montos, plazos
from nucleo.acuses import _pdf, emitir_acuse
from nucleo.models import Consecutivo, Evento, TipoUnidad, Unidad

from .firma import datos_contrato
from .models import Especie, RenglonVale, SalidaPlanta, ValePlanta, Vivero
from nucleo.trazabilidad import registra_usuario

ESTADOS_ANTICIPADOS = ("notificada", "contrato_elaborado", "contrato_en_delegacion")
ESTADOS_CON_CONTRATO = ("contratada", "vale_entregado")
EXTENSIONES_CARTA = (".pdf", ".jpg", ".jpeg", ".png")


# ----------------------------------------------------------------------------- datos por programa
def config_vale(expediente):
    """Reglas del Vale del programa (``datos/contrato.json``) o None si el programa no entrega planta con Vale."""
    cfg = datos_contrato()["vale_de_planta"].get(expediente.programa.clave)
    return cfg if isinstance(cfg, dict) else None


def aplica(expediente):
    """(True, "") si el expediente tiene derecho a planta; si no, (False, razón citando la regla)."""
    cfg = config_vale(expediente)
    if cfg is None:
        return False, f"{expediente.programa.nombre} no entrega planta con Vale (solo Plantaciones Sustentables y RHF)."
    if expediente.modalidad and expediente.modalidad.clave in cfg.get("sin_planta", []):
        return False, f"{cfg['sin_planta_texto']} No se emite Vale de Planta."
    return True, ""


def propuesta(expediente):
    """Planta por hectárea de las reglas × la superficie aprobada: ``{"piezas_por_ha", "texto", "total"}``."""
    cfg = config_vale(expediente) or {}
    dato = (cfg.get("por_hectarea") or {}).get(expediente.modalidad.clave if expediente.modalidad else "", {})
    piezas = dato.get("piezas")
    superficie = montos.superficie_aprobada(expediente)
    total = int(math.ceil(Decimal(piezas) * superficie)) if piezas else None
    return {"piezas_por_ha": piezas, "texto": dato.get("texto", ""), "total": total, "superficie_ha": superficie}


def _vales(expediente):
    return list(expediente.vales.prefetch_related("renglones__salidas", "reposiciones").order_by("entregado_en", "id"))


def vale_por_reponer(expediente, hoy=None):
    """El vale vencido (no surtido ni repuesto) del expediente, si lo hay."""
    for v in reversed(_vales(expediente)):
        if v.situacion(hoy) == "vencido":
            return v
    return None


def situacion_para_emitir(expediente, hoy=None):
    """``{"puede", "motivo", "tipo", "repone"}`` (tipo: «primero», «anticipado» o «reposicion») para la pantalla y el servicio."""
    ok, razon = aplica(expediente)
    if not ok:
        return {"puede": False, "motivo": razon, "tipo": "", "repone": None}
    estado = expediente.estado.clave
    if estado not in ESTADOS_ANTICIPADOS + ESTADOS_CON_CONTRATO:
        return {"puede": False, "tipo": "", "repone": None, "motivo": (
            f"El expediente está «{expediente.estado}»: el Vale se entrega a una solicitud con el resultado notificado "
            "(antes del contrato, con carta compromiso) o con el contrato firmado.")}
    vales = _vales(expediente)
    for v in vales:
        if v.surtido:
            return {"puede": False, "tipo": "", "repone": None,
                    "motivo": f"El vale {v.folio} ya se surtió completo: no hay más planta que entregar."}
        if v.vigente(hoy):
            return {"puede": False, "tipo": "", "repone": None,
                    "motivo": f"Ya tiene el vale {v.folio}, vigente hasta el {v.vence_el:%d/%m/%Y}." if v.vence_el
                    else f"Ya tiene el vale {v.folio}, vigente."}
    repone = vale_por_reponer(expediente, hoy)
    if repone is not None:
        cfg = config_vale(expediente)
        if not cfg.get("reposicion"):
            return {"puede": False, "tipo": "reposicion", "repone": repone,
                    "motivo": f"El vale {repone.folio} venció y no es válido. {cfg['reposicion_texto']}"}
        return {"puede": True, "motivo": "", "tipo": "reposicion", "repone": repone}
    anticipado = estado in ESTADOS_ANTICIPADOS
    return {"puede": True, "motivo": "", "tipo": "anticipado" if anticipado else "primero", "repone": None}


# ----------------------------------------------------------------------------- consultas
def vales_visibles(usuario):
    qs = ValePlanta.objects.select_related("expediente__predio__municipio", "expediente__ejercicio__programa",
                                           "expediente__solicitante", "vivero", "acuse").prefetch_related(
        "renglones__especie", "renglones__salidas", "reposiciones")
    if not usuario.is_authenticated:
        return qs.none()
    if usuario.is_superuser:
        return qs
    unidad = usuario.unidad
    if unidad is None:
        return qs.none()
    if unidad.tipo == TipoUnidad.DELEGACION:
        return qs.filter(expediente__delegacion=unidad)
    if unidad.tipo == TipoUnidad.DIRECCION:
        return qs.filter(expediente__ejercicio__programa__in=unidad.programas.all())
    if unidad.tipo == TipoUnidad.VIVERO:
        return qs.filter(vivero__unidad=unidad)
    if unidad.tipo == TipoUnidad.JURIDICA:
        return qs
    return qs.none()


def por_entregar_vale(usuario):
    """Expedientes de la Delegación con contrato firmado y derecho a planta que todavía no tienen su vale."""
    from nucleo.models import expedientes_visibles

    return [e for e in expedientes_visibles(usuario).filter(
        estado__clave="contratada", ejercicio__programa__clave__in=list(_programas_con_vale())).order_by("fecha_recepcion")
            if aplica(e)[0] and not e.vales.exists()]


def por_reponer(usuario):
    """Vales vencidos (no surtidos ni repuestos) de la Delegación, que pueden reponerse si el programa lo prevé."""
    return [v for v in vales_visibles(usuario) if v.situacion() == "vencido"]


def por_surtir(usuario):
    """Vales vigentes del vivero (o de lo que ve la unidad) con planta pendiente."""
    return [v for v in vales_visibles(usuario) if v.vigente() and v.total_pendiente > 0]


def _programas_con_vale():
    return [k for k, v in datos_contrato()["vale_de_planta"].items() if isinstance(v, dict)]


# ----------------------------------------------------------------------------- emisión del vale
def _validar_carta(carta):
    if carta is None or not getattr(carta, "name", ""):
        raise ValidationError("Antes de la firma del contrato el Vale exige la carta compromiso de la persona "
                              "beneficiaria (archivo): lo pide la regla voluntaria y bajo su responsabilidad.")
    if not carta.name.lower().endswith(EXTENSIONES_CARTA):
        raise ValidationError("La carta compromiso debe ser PDF, JPG o PNG.")


@registra_usuario
def emitir_vale(usuario, expediente, vivero, renglones, carta=None, motivo_ajuste="", planta_disponible=True,
                momento=None):
    """La Delegación emite el Vale de Planta. ``renglones``: lista de ``(especie, cantidad)``."""
    exigir_unidad(usuario, TipoUnidad.DELEGACION)
    exigir_acceso(usuario, expediente)
    expediente.refresh_from_db()
    exigir_vigente(expediente, "ya no se le entrega Vale de Planta")
    ahora = momento or timezone.now()
    situacion = situacion_para_emitir(expediente, timezone.localtime(ahora).date())
    if not situacion["puede"]:
        raise ValidationError(situacion["motivo"])
    cfg = config_vale(expediente)
    repone = situacion["repone"]
    if situacion["tipo"] == "reposicion" and not planta_disponible:
        raise ValidationError("La reposición del Vale está sujeta a que haya planta disponible en el vivero: confirme "
                              f"la disponibilidad. {cfg['reposicion_texto']}")
    if not isinstance(vivero, Vivero) or not vivero.activo:
        raise ValidationError("Elija el vivero que entrega la planta.")
    anticipado = expediente.estado.clave in ESTADOS_ANTICIPADOS
    if anticipado and not (repone and repone.carta_compromiso):
        _validar_carta(carta)
    # renglones por especie
    limpios, vistas = [], set()
    for especie, cantidad in renglones or ():
        if not isinstance(especie, Especie) or not especie.activa:
            raise ValidationError("Elija una especie del catálogo.")
        if especie.pk in vistas:
            raise ValidationError(f"La especie «{especie.nombre}» está repetida en el vale.")
        vistas.add(especie.pk)
        try:
            cantidad = int(cantidad)
        except (TypeError, ValueError):
            raise ValidationError(f"La cantidad de «{especie.nombre}» debe ser un número entero.")
        if cantidad <= 0:
            raise ValidationError(f"La cantidad de «{especie.nombre}» debe ser mayor que cero.")
        limpios.append((especie, cantidad))
    if not limpios:
        raise ValidationError("El vale necesita al menos una especie con su cantidad.")
    total = sum(c for _, c in limpios)
    if repone is not None:  # solo cubre lo no entregado del vale anterior
        pendientes = {r.especie_id: r.pendiente for r in repone.renglones.all()}
        for especie, cantidad in limpios:
            if especie.pk not in pendientes:
                raise ValidationError(f"«{especie.nombre}» no estaba en el vale {repone.folio}: la reposición solo cubre "
                                      "lo no entregado.")
            if cantidad > pendientes[especie.pk]:
                raise ValidationError(f"De «{especie.nombre}» solo faltan por entregar {pendientes[especie.pk]} piezas del "
                                      f"vale {repone.folio}: la reposición no puede pasar de eso.")
        sugerida = repone.total_pendiente
    else:
        sugerida = propuesta(expediente)["total"]
    if sugerida is not None and total != sugerida and not (motivo_ajuste or "").strip():
        raise ValidationError(f"La cantidad ({total}) difiere de la propuesta ({sugerida}): indique el motivo del ajuste.")
    vigencia = plazos.vencimiento(expediente, "recoger_planta", fecha_evento=ahora)
    anio = expediente.ejercicio.anio
    with transaction.atomic():
        folio = (f"VP-{expediente.programa.clave}-{anio}-"
                 f"{Consecutivo.siguiente(f'vale-{expediente.programa.clave}-{anio}'):04d}")
        vale = ValePlanta.objects.create(
            folio=folio, expediente=expediente, vivero=vivero, entregado_en=ahora, entregado_por=usuario,
            vence_el=vigencia.vencimiento if vigencia is not None and vigencia.tiene_fecha else None,
            vigencia_texto=vigencia.texto if vigencia is not None else "", anticipado=anticipado,
            propuesta_total=sugerida, motivo_ajuste=(motivo_ajuste or "").strip() if sugerida is not None and total != sugerida else "",
            repone=repone, planta_disponible=bool(planta_disponible))
        for especie, cantidad in limpios:
            RenglonVale.objects.create(vale=vale, especie=especie, cantidad=cantidad)
        vale = ValePlanta.objects.prefetch_related("renglones__especie").get(pk=vale.pk)
        if carta is not None and getattr(carta, "name", ""):
            carta.seek(0)
            vale.carta_compromiso.save(f"carta_compromiso.{carta.name.rsplit('.', 1)[-1].lower()}", ContentFile(carta.read()),
                                       save=False)
        elif repone is not None and repone.carta_compromiso:
            vale.carta_compromiso = repone.carta_compromiso.name
        pdf = _pdf(render_to_string("contrato/planta/vale_pdf.html", _contexto_pdf(vale, vigencia)))
        vale.huella = hashlib.sha256(pdf).hexdigest()
        vale.archivo.save(f"{folio}.pdf", ContentFile(pdf), save=False)
        vale.save()
        renglones_acuse = [
            ("Vale de Salida de Planta", folio), ("Solicitud", expediente.folio),
            ("Persona beneficiaria", expediente.solicitante.nombre), ("Predio", expediente.predio.nombre),
            ("Vivero que entrega", vivero.nombre),
            ("Planta autorizada", "; ".join(f"{e.nombre}: {c}" for e, c in limpios) + f" (total {total})"),
            ("Fecha y hora de entrega del vale", f"{timezone.localtime(ahora):%d/%m/%Y %H:%M:%S} h"),
            ("Vigencia", f"hasta el {vale.vence_el:%d/%m/%Y}" if vale.vence_el else "sin fecha en las reglas"),
            ("Plazo de las reglas", vigencia.texto if vigencia is not None else "—"),
            ("Antes de la firma del contrato", "Sí, con carta compromiso" if anticipado else "No"),
        ]
        if repone is not None:
            renglones_acuse.append(("Repone al vale", f"{repone.folio} (solo lo no entregado)"))
        if vale.motivo_ajuste:
            renglones_acuse.append(("Ajuste a la propuesta", f"{vale.motivo_ajuste} (propuesta: {sugerida})"))
        renglones_acuse.append(("Entrega", usuario.unidad.nombre))
        vale.acuse = emitir_acuse(expediente, "entrega_vale", f"Entrega del Vale de Planta {folio}", usuario,
                                  renglones_acuse, destinatario=expediente.solicitante.nombre)
        vale.save(update_fields=["acuse"])
        plazos.registrar_hito(expediente, "entrega_vale", usuario, ahora, referencia=folio, datos={"vale": vale.pk})
        descripcion = (f"Vale de Planta {folio} entregado ({total} piezas, {vivero.nombre})"
                       + (f", repone al {repone.folio}" if repone else "") + (" antes de la firma del contrato" if anticipado else ""))
        if expediente.estado.clave == "contratada":
            expediente.cambiar_estado("vale_entregado", usuario, tipo_evento="vale_entregado", acuse=vale.acuse,
                                      descripcion=descripcion, datos={"vale": vale.pk})
        else:
            Evento.registrar(expediente, usuario, "vale_repuesto" if repone else "vale_entregado", descripcion,
                             acuse=vale.acuse, datos={"vale": vale.pk})
    return vale


def _contexto_pdf(vale, vigencia):
    exp = vale.expediente
    return {"vale": vale, "exp": exp, "renglones": list(vale.renglones.all()), "vigencia": vigencia,
            "fecha": timezone.localtime(vale.entregado_en), "total": vale.total_autorizado,
            "plazo_texto": vale.vigencia_texto or "las Reglas de Operación no fijan plazo para este programa"}


# ----------------------------------------------------------------------------- salida del vivero
@registra_usuario
def validar_vale(usuario, vale, hoy=None):
    """Valida el vale antes de entregar planta. Devuelve su situación; lanza ``ValidationError`` si no es válido."""
    exigir_unidad(usuario, TipoUnidad.VIVERO)
    if vale.vivero.unidad_id != usuario.unidad_id:
        raise PermissionDenied(f"El vale {vale.folio} se surte en {vale.vivero.nombre}, no en su vivero.")
    vale = ValePlanta.objects.select_related("expediente__estado").get(pk=vale.pk)
    exigir_vigente(vale.expediente, f"el vale {vale.folio} ya no se surte")
    estado = vale.situacion(hoy)
    if estado == "surtido":
        raise ValidationError(f"El vale {vale.folio} ya se surtió completo: no queda planta por entregar.")
    if estado == "repuesto":
        nuevo = vale.reposiciones.first()
        raise ValidationError(f"El vale {vale.folio} fue repuesto por el {nuevo.folio}: ya no es válido.")
    if estado == "vencido":
        cfg = config_vale(vale.expediente) or {}
        raise ValidationError(
            f"El vale {vale.folio} venció el {vale.vence_el:%d/%m/%Y} y un vale vencido no es válido: no se entrega planta. "
            + ("La persona debe solicitar a la Delegación un nuevo Vale (se expide si hay planta disponible)."
               if cfg.get("reposicion") else cfg.get("reposicion_texto", "")))
    return estado


@registra_usuario
def registrar_salida(usuario, vale, especie, cantidad, salido_en=None, observaciones="", momento=None):
    """El personal del vivero registra una salida de planta contra un vale vigente (especie, cantidad, fecha y hora)."""
    exigir_unidad(usuario, TipoUnidad.VIVERO)
    ahora = momento or timezone.now()
    salido_en = salido_en or ahora
    vale = ValePlanta.objects.get(pk=vale.pk)
    validar_vale(usuario, vale, timezone.localtime(salido_en).date())
    if salido_en > ahora:
        raise ValidationError("La fecha y la hora de la salida no pueden ser futuras.")
    if salido_en < vale.entregado_en:
        raise ValidationError("La salida no puede ser anterior a la entrega del vale "
                              f"({timezone.localtime(vale.entregado_en):%d/%m/%Y %H:%M} h).")
    if not isinstance(especie, Especie):
        raise ValidationError("Indique la especie que sale.")
    renglon = vale.renglones.filter(especie=especie).first()
    if renglon is None:
        raise ValidationError(f"«{especie.nombre}» no está autorizada en el vale {vale.folio}.")
    try:
        cantidad = int(cantidad)
    except (TypeError, ValueError):
        raise ValidationError("La cantidad debe ser un número entero.")
    if cantidad <= 0:
        raise ValidationError("La cantidad debe ser mayor que cero.")
    if cantidad > renglon.pendiente:
        raise ValidationError(f"De «{especie.nombre}» solo quedan {renglon.pendiente} piezas por entregar en el vale "
                              f"{vale.folio} (autorizadas {renglon.cantidad}): no se entrega más de lo autorizado.")
    exp = vale.expediente
    with transaction.atomic():
        salida = SalidaPlanta.objects.create(renglon=renglon, vale=vale, cantidad=cantidad, salido_en=salido_en,
                                             registrada_por=usuario, registrada_en=ahora,
                                             observaciones=(observaciones or "").strip())
        vale = ValePlanta.objects.prefetch_related("renglones__salidas", "renglones__especie").get(pk=vale.pk)
        saldo = [(r.especie.nombre, r.pendiente) for r in vale.renglones.all()]
        completo = all(p == 0 for _, p in saldo)
        salida.acuse = emitir_acuse(
            exp, "salida_planta", f"Salida de planta del vale {vale.folio}", usuario,
            [("Vale de Salida de Planta", vale.folio), ("Solicitud", exp.folio), ("Persona beneficiaria", exp.solicitante.nombre),
             ("Vivero", vale.vivero.nombre), ("Especie", especie.nombre), ("Cantidad", f"{cantidad} piezas"),
             ("Fecha y hora de la salida", f"{timezone.localtime(salido_en):%d/%m/%Y %H:%M:%S} h"),
             ("Por entregar del vale", "; ".join(f"{n}: {p}" for n, p in saldo) + (" (vale completo)" if completo else "")),
             ("Registra", usuario.unidad.nombre)], destinatario=exp.solicitante.nombre)
        salida.save(update_fields=["acuse"])
        descripcion = f"Salida de planta del vale {vale.folio}: {especie.nombre} × {cantidad}"
        Evento.registrar(exp, usuario, "salida_planta", descripcion, acuse=salida.acuse, datos={"vale": vale.pk,
                                                                                               "salida": salida.pk})
        if completo:
            vale.completado_en = salido_en
            vale.save(update_fields=["completado_en"])
            if exp.estado.clave == "vale_entregado":
                exp.cambiar_estado("planta_entregada", usuario, tipo_evento="planta_entregada", acuse=salida.acuse,
                                   descripcion=f"Vale {vale.folio} surtido completo: planta entregada",
                                   datos={"vale": vale.pk})
            else:
                Evento.registrar(exp, usuario, "planta_entregada",
                                 f"Vale {vale.folio} surtido completo antes de la firma del contrato",
                                 acuse=salida.acuse, datos={"vale": vale.pk})
    return salida


# ----------------------------------------------------------------------------- enganche con la firma (HU-3.3)
def al_firmar(firma):
    """Si el Vale se entregó antes de la firma, el expediente pasa a «vale entregado» (por surtir) o, si el vivero ya lo
    surtió, a «planta entregada»."""
    exp = firma.expediente
    vales = [v for v in _vales(exp) if not v.repuesto]
    if not vales:
        return
    destino = "planta_entregada" if all(v.surtido for v in vales) else "vale_entregado"
    exp.refresh_from_db()
    exp.cambiar_estado(destino, firma.registrada_por, tipo_evento=destino,
                       descripcion="Contrato firmado con Vale de Planta entregado antes de la firma",
                       datos={"firma": firma.pk})


# ----------------------------------------------------------------------------- catálogos
def cargar_catalogo():
    """Especies y viveros de demostración (``datos/contrato.json`` → ``catalogos_planta``); idempotente."""
    cat = datos_contrato().get("catalogos_planta", {})
    for e in cat.get("especies", []):
        Especie.objects.get_or_create(nombre=e["nombre"], defaults={"nombre_cientifico": e.get("cientifico", "")})
    for v in cat.get("viveros", []):
        unidad = Unidad.objects.filter(clave=v["unidad"]).first() if v.get("unidad") else None
        Vivero.objects.get_or_create(clave=v["clave"], defaults={"nombre": v["nombre"], "unidad": unidad,
                                                                 "municipio": v.get("municipio", "")})
    return Especie.objects.count() + Vivero.objects.count()
