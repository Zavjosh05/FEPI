"""Reglas del módulo M1. Las vistas y las pruebas usan estas funciones; nada de requisitos ni plazos
escritos aquí: todo sale del Ejercicio (cargado de reglas/<CLAVE>.json)."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from nucleo import dias_habiles, notificaciones, plazos, reglas
from nucleo.acuses import emitir_acuse
from nucleo.catalogos import datos_sistema
from nucleo.models import (
    Documento, Estado, Evento, Expediente, MedioNotificacion, Municipio, Persona, Predio, TipoDocumento,
    TipoNotificacion, TipoUnidad, puede_ver_expediente,
)

from . import geometria
from .models import (
    EstadoRevision, OrigenPoligono, Poligono, ResultadoValidacion, RevisionRequisito, TipoCambio, Validacion,
)

ESTADOS_EDITABLES_DELEGACION = {"recibida", "faltantes"}
ESTADOS_POLIGONO = {"recibida", "enviada_direccion", "faltantes", "validada"}
UMBRAL_CAMBIO_LUGAR_PCT = Decimal("50")  # traslape (intersección / unión) menor = cambio de lugar


def _clave_plazo(nombre):
    return datos_sistema()["plazos_del_sistema"][nombre]


def _exigir_unidad(usuario, tipo):
    if usuario.tipo_unidad != tipo:
        raise PermissionDenied(f"Esta acción le corresponde a: {TipoUnidad(tipo).label}.")


def _exigir_acceso(usuario, expediente):
    if not puede_ver_expediente(usuario, expediente):
        raise PermissionDenied("El expediente no pertenece a su unidad.")


def fmt_fecha_hora(valor):
    return timezone.localtime(valor).strftime("%d/%m/%Y %H:%M:%S h")


# ----------------------------------------------------------------------------- requisitos aplicables
def requisitos_aplicables(ejercicio, tipo_persona, modalidad=None):
    """Requisitos del programa-ejercicio para el tipo de persona y la modalidad (vacío = todos). Si la persona
    beneficiaria no es quien solicita (PEG: el Guardabosque), se suman los requisitos de su tipo (8.1.1.2 b)."""
    qs = ejercicio.requisitos.all()
    filtro = Q(tipos_persona=tipo_persona) | Q(tipos_persona__isnull=True)
    beneficiaria = reglas.persona_beneficiaria_distinta(ejercicio)
    if beneficiaria:
        filtro |= Q(tipos_persona__clave=beneficiaria["tipo_persona"])
    qs = qs.filter(filtro)
    if modalidad is not None:
        qs = qs.filter(Q(modalidades=modalidad) | Q(modalidades__isnull=True))
    else:
        qs = qs.filter(modalidades__isnull=True)
    return qs.distinct().order_by("orden")


def delegacion_que_corresponde(municipio):
    return municipio.delegacion


# ----------------------------------------------------------------------------- HU-1.1 registro
@dataclass
class DatosSolicitud:
    ejercicio: object
    municipio: Municipio
    nombre_predio: str
    tipo_persona: object
    solicitante_nombre: str
    solicitante_tipo: str
    modalidad: object = None
    localidad: str = ""
    superficie_solicitada_ha: Decimal = None
    curp: str = ""
    rfc: str = ""
    telefono: str = ""
    correo: str = ""
    representante: str = ""
    con_representante_legal: bool = False
    es_refrendo: bool = False
    predio_existente: object = None
    observaciones: str = ""
    beneficiaria_nombre: str = ""  # PEG: el Guardabosque que designa la Asamblea del núcleo agrario
    beneficiaria_curp: str = ""
    beneficiaria_telefono: str = ""
    extra: dict = field(default_factory=dict)


def registrar_solicitud(usuario, datos: DatosSolicitud):
    """Registra la solicitud a nombre del predio en la Delegación del usuario y emite el acuse."""
    _exigir_unidad(usuario, TipoUnidad.DELEGACION)
    delegacion = usuario.unidad
    if not datos.ejercicio.tiene_reglas:
        raise ValidationError(f"{datos.ejercicio} aún no tiene reglas cargadas; no se pueden recibir solicitudes.")
    corresponde = delegacion_que_corresponde(datos.municipio)
    if corresponde != delegacion:
        destino = corresponde.nombre if corresponde else "ninguna Delegación (municipio sin asignar)"
        raise ValidationError(
            f"El predio está en {datos.municipio.nombre}, municipio que atiende {destino}. "
            f"La solicitud debe presentarse en esa Delegación, no en {delegacion.nombre} "
            "(ROP, numeral 8.1.3 Modalidades de registro)."
        )
    if datos.modalidad is not None and datos.modalidad.ejercicio_id != datos.ejercicio.pk:
        raise ValidationError("La modalidad no pertenece al programa elegido.")
    if datos.modalidad is not None and not datos.modalidad.seleccionable:
        raise ValidationError(f"«{datos.modalidad.nombre}» no se elige al registrar la solicitud "
                              "(es un régimen de pago, el refrendo u otro caso que el sistema maneja aparte).")
    if not reglas.tipos_persona_seleccionables(datos.ejercicio).filter(pk=datos.tipo_persona.pk).exists():
        raise ValidationError(f"«{datos.tipo_persona.nombre}» no presenta la solicitud en este programa.")
    conf_beneficiaria = reglas.persona_beneficiaria_distinta(datos.ejercicio)
    if conf_beneficiaria and conf_beneficiaria.get("obligatoria") and not datos.beneficiaria_nombre.strip():
        raise ValidationError(f"Falta la persona beneficiaria: {conf_beneficiaria['etiqueta']}.")
    with transaction.atomic():
        if datos.predio_existente:
            predio = datos.predio_existente
            if predio.municipio_id != datos.municipio.pk:
                raise ValidationError("El predio ya registrado está en otro municipio.")
            solicitante = predio.titular
        else:
            solicitante = Persona.objects.create(
                tipo=datos.solicitante_tipo, nombre=datos.solicitante_nombre, curp=datos.curp, rfc=datos.rfc,
                telefono=datos.telefono, correo=datos.correo, representante=datos.representante,
            )
            predio = Predio.objects.create(
                nombre=datos.nombre_predio, municipio=datos.municipio, localidad=datos.localidad,
                titular=solicitante, superficie_declarada_ha=datos.superficie_solicitada_ha,
            )
        beneficiaria = None
        if conf_beneficiaria and datos.beneficiaria_nombre.strip():
            beneficiaria = Persona.objects.create(
                tipo=conf_beneficiaria.get("tipo_general", "fisica"), nombre=datos.beneficiaria_nombre.strip(),
                curp=datos.beneficiaria_curp.strip().upper(), telefono=datos.beneficiaria_telefono)
        expediente = Expediente.objects.create(
            ejercicio=datos.ejercicio, predio=predio, solicitante=solicitante, tipo_persona=datos.tipo_persona,
            persona_beneficiaria=beneficiaria,
            modalidad=datos.modalidad, es_refrendo=datos.es_refrendo,
            con_representante_legal=datos.con_representante_legal,
            superficie_solicitada_ha=datos.superficie_solicitada_ha, delegacion=delegacion,
            estado=Estado.objects.get(clave="recibida"), fecha_recepcion=timezone.now(), registrado_por=usuario,
            observaciones=datos.observaciones,
        )
        for req in requisitos_aplicables(datos.ejercicio, datos.tipo_persona, datos.modalidad):
            RevisionRequisito.objects.create(expediente=expediente, requisito=req)
        venc = plazos.vencimiento(expediente, "faltantes_ventanilla")
        limite = venc.vencimiento if venc else None
        renglones = [
            ("Delegación que recibe", delegacion.nombre),
            ("Fecha y hora de recepción", fmt_fecha_hora(expediente.fecha_recepcion)),
            ("Tipo de persona", datos.tipo_persona.nombre),
            *([(conf_beneficiaria["etiqueta"],
                beneficiaria.nombre + (f" (CURP {beneficiaria.curp})" if beneficiaria.curp else ""))]
              if beneficiaria else []),
            ("Modalidad", datos.modalidad.nombre if datos.modalidad else "—"),
            ("Refrendo", "Sí" if datos.es_refrendo else "No"),
            ("Superficie solicitada", f"{datos.superficie_solicitada_ha} ha" if datos.superficie_solicitada_ha else "—"),
            ("Requisitos por revisar", str(expediente.revisiones.count())),
        ]
        nota = ""
        if limite:
            nota = (f"Si falta documentación, la persona solicitante cuenta con {venc.texto_plazo} a partir de la "
                    f"recepción para presentarla (hasta el {limite:%d/%m/%Y}), sin exceder la fecha límite de la "
                    f"Convocatoria; de lo contrario la solicitud se tendrá por desechada ({venc.fundamento}).")
            if venc.evento_despues_del_tope:
                nota += (f" Aviso: la solicitud se recibió después de la fecha límite de recepción de la "
                         f"Convocatoria ({venc.tope:%d/%m/%Y}).")
        acuse = emitir_acuse(expediente, "recepcion", "Acuse de recepción de la solicitud", usuario, renglones,
                             destinatario=solicitante.nombre, nota=nota)
        Evento.registrar(expediente, usuario, "registro",
                         f"Solicitud registrada a nombre del predio {predio.folio} en {delegacion.nombre}.",
                         estado_destino=expediente.estado, acuse=acuse)
    return expediente


# ----------------------------------------------------------------------------- HU-1.2 revisión y envío
def vigencia_refrendo(expediente):
    """(cantidad, unidad, fundamento) de la vigencia de la documentación en refrendo, desde las reglas."""
    plazo = expediente.ejercicio.plazo(_clave_plazo("vigencia_refrendo"))
    if plazo is None or plazo.cantidad is None:
        return None
    return plazo


def fecha_minima_vigente(expediente):
    plazo = vigencia_refrendo(expediente)
    if plazo is None:
        return None
    recepcion = timezone.localtime(expediente.fecha_recepcion).date()
    meses = plazo.cantidad * (12 if plazo.unidad == "anios" else 1)
    return dias_habiles.sumar_meses(recepcion, -meses)


def documentacion_vigente(expediente, fecha_documento):
    """En un refrendo, la documentación que obra en PROBOSQUE vale si no tiene más de N años (reglas)."""
    minima = fecha_minima_vigente(expediente)
    return minima is not None and fecha_documento is not None and fecha_documento >= minima


def puede_usar_archivo_probosque(revision):
    exp = revision.expediente
    return exp.es_refrendo and revision.requisito.aplica_en_refrendo is False


def revisar_requisito(usuario, revision, estado, archivo=None, en_archivo_probosque=False, fecha_documento=None,
                      observaciones=""):
    """La Delegación marca el requisito como entregado (con su archivo), faltante o no aplica."""
    exp = revision.expediente
    _exigir_unidad(usuario, TipoUnidad.DELEGACION)
    _exigir_acceso(usuario, exp)
    if exp.estado.clave not in ESTADOS_EDITABLES_DELEGACION:
        raise ValidationError(f"El expediente está «{exp.estado}»; ya no se pueden cambiar los requisitos.")
    if estado not in EstadoRevision.values or estado == EstadoRevision.PENDIENTE:
        raise ValidationError("Elija entregado, faltante o no aplica.")
    if estado == EstadoRevision.NO_APLICA and not revision.requisito.es_condicional:
        raise ValidationError("Este requisito se pide siempre; no puede marcarse «no aplica».")
    with transaction.atomic():
        revision.en_archivo_probosque = False
        revision.fecha_documento = None
        if estado == EstadoRevision.ENTREGADO:
            if en_archivo_probosque:
                if not puede_usar_archivo_probosque(revision):
                    raise ValidationError("Solo en un refrendo, y para los requisitos que las reglas no piden "
                                          "en refrendo, vale la documentación que obra en PROBOSQUE.")
                if not documentacion_vigente(exp, fecha_documento):
                    plazo = vigencia_refrendo(exp)
                    raise ValidationError(
                        f"La documentación que obra en PROBOSQUE tiene más de {plazo.texto_plazo if plazo else '—'}; "
                        "debe entregarse de nuevo.")
                revision.en_archivo_probosque = True
                revision.fecha_documento = fecha_documento
            elif archivo is None and revision.documento_id is None and revision.requisito.requiere_documento:
                raise ValidationError("Adjunte el archivo digitalizado del requisito.")
            if archivo is not None:
                doc = Documento.objects.create(
                    expediente=exp, tipo=TipoDocumento.REQUISITO, requisito=revision.requisito,
                    nombre=f"{revision.requisito.clave} · {archivo.name}", archivo=archivo,
                    registrado_por=usuario, unidad=usuario.unidad,
                )
                revision.documento = doc
        revision.estado = estado
        revision.observaciones = observaciones
        revision.revisado_por = usuario
        revision.revisado_en = timezone.now()
        revision.save()
        Evento.registrar(exp, usuario, "revision_requisito",
                         f"{revision.requisito.clave}: {revision.get_estado_display()}"
                         + (" (documentación en archivo de PROBOSQUE)" if revision.en_archivo_probosque else ""),
                         datos={"requisito": revision.requisito.clave, "estado": estado})
    return revision


def problemas_para_enviar(expediente):
    """Regla de envío a la Dirección (HU-1.2). Lista vacía = se puede enviar.

    1. Todos los requisitos aplicables están revisados (ninguno «sin revisar»).
    2. Ninguno está «faltante»: las ROP piden la documentación completa para atender la solicitud
       (CC 8.1.1.2 fr. XIV); la persona tiene el plazo de complemento para entregarlo.
    3. Cada requisito entregado tiene su archivo digitalizado, salvo la documentación que obra en
       PROBOSQUE en un refrendo (vigente según las reglas).
    El polígono no es condición: las ROP lo levantan después de entregar el expediente (CC 10.1 fr. III).
    """
    problemas = []
    revisiones = list(expediente.revisiones.select_related("requisito"))
    if not revisiones:
        problemas.append("El expediente no tiene requisitos que revisar.")
    pendientes = [r.requisito.clave for r in revisiones if r.estado == EstadoRevision.PENDIENTE]
    faltantes = [r.requisito.clave for r in revisiones if r.estado == EstadoRevision.FALTANTE]
    sin_archivo = [r.requisito.clave for r in revisiones
                   if r.estado == EstadoRevision.ENTREGADO and not r.documento_id and not r.en_archivo_probosque
                   and r.requisito.requiere_documento]
    if pendientes:
        problemas.append("Requisitos sin revisar: " + ", ".join(pendientes))
    if faltantes:
        problemas.append("Requisitos faltantes: " + ", ".join(faltantes))
    if sin_archivo:
        problemas.append("Requisitos entregados sin archivo digitalizado: " + ", ".join(sin_archivo))
    return problemas


def detalle_requisitos(expediente):
    return [{"clave": r.requisito.clave, "texto": r.requisito.titulo,
             "estado": r.get_estado_display() + (" (archivo PROBOSQUE)" if r.en_archivo_probosque else "")}
            for r in expediente.revisiones.select_related("requisito")]


def enviar_a_direccion(usuario, expediente):
    """Envía el expediente digital a la Dirección con fecha, hora y acuse."""
    _exigir_unidad(usuario, TipoUnidad.DELEGACION)
    _exigir_acceso(usuario, expediente)
    problemas = problemas_para_enviar(expediente)
    if problemas:
        raise ValidationError(problemas)
    direccion = expediente.programa.unidades_responsables.filter(tipo=TipoUnidad.DIRECCION).first()
    reenvio = expediente.estado.clave == "faltantes"
    with transaction.atomic():
        ahora = timezone.now()
        acuse = emitir_acuse(
            expediente, "envio_direccion",
            "Acuse de envío del expediente digital a la Dirección" + (" (con faltantes atendidos)" if reenvio else ""),
            usuario,
            [("Envía", expediente.delegacion.nombre), ("Recibe", direccion.nombre if direccion else "Dirección"),
             ("Fecha y hora del envío", fmt_fecha_hora(ahora)),
             ("Documentos digitalizados", str(expediente.documentos.filter(tipo=TipoDocumento.REQUISITO).count()))],
            destinatario=direccion.nombre if direccion else "", detalle=detalle_requisitos(expediente),
        )
        expediente.cambiar_estado("enviada_direccion", usuario, tipo_evento="envio", acuse=acuse,
                                  descripcion=f"Expediente digital enviado a {direccion or 'la Dirección'}.")
    return acuse


# ----------------------------------------------------------------------------- HU-1.3 polígono
def poligono_vigente(expediente):
    return expediente.poligonos.filter(vigente=True).first()


def registrar_poligono(usuario, expediente, geom, origen, levantado_por, responsable, fecha_levantamiento,
                       prestador=None, archivo=None, motivo_cambio=""):
    """Registra el polígono levantado en campo. Conserva el anterior (historial)."""
    _exigir_unidad(usuario, TipoUnidad.DELEGACION)
    _exigir_acceso(usuario, expediente)
    if not expediente.programa.usa_poligono:
        raise ValidationError(f"El programa {expediente.programa.nombre} no usa polígono.")
    if expediente.estado.clave not in ESTADOS_POLIGONO:
        raise ValidationError(f"El expediente está «{expediente.estado}»; no se puede cambiar el polígono.")
    if origen not in OrigenPoligono.values:
        raise ValidationError("Origen del polígono no reconocido.")
    if levantado_por == "prestador" and not (prestador or responsable):
        raise ValidationError("Indique el prestador de servicios forestales que levantó el polígono.")
    geometria.revisar_validez(geom)
    ubicacion, aviso = geometria.ubicacion_en_municipio(geom, expediente.predio.municipio)
    anterior = poligono_vigente(expediente)
    tipo_cambio, traslape = TipoCambio.INICIAL, None
    if anterior:
        traslape = geometria.traslape_pct(geom, anterior.geom)
        tipo_cambio = TipoCambio.CAMBIO_LUGAR if traslape < UMBRAL_CAMBIO_LUGAR_PCT else TipoCambio.CORRECCION
        if not motivo_cambio.strip():
            raise ValidationError("Indique el motivo del cambio del polígono.")
    with transaction.atomic():
        if anterior:
            anterior.vigente = False
            anterior.save(update_fields=["vigente"])
        pol = Poligono(
            expediente=expediente, geom=geom, superficie_ha=geometria.superficie_ha(geom),
            levantado_por=levantado_por, prestador=prestador, responsable=responsable,
            fecha_levantamiento=fecha_levantamiento, origen=origen, anterior=anterior, tipo_cambio=tipo_cambio,
            traslape_anterior_pct=traslape, ubicacion_municipio=ubicacion, aviso=aviso,
            motivo_cambio=motivo_cambio, registrado_por=usuario,
        )
        if archivo is not None:
            archivo.seek(0)
            pol.archivo.save(archivo.name, archivo, save=False)
        pol.save()
        texto = f"Polígono registrado ({pol.superficie_ha} ha, {pol.get_tipo_cambio_display().lower()})"
        if anterior:
            texto += f"; se conserva el anterior ({anterior.superficie_ha} ha, traslape {traslape} %)"
        Evento.registrar(expediente, usuario, "poligono", texto + ".",
                         datos={"poligono": pol.pk, "ubicacion": ubicacion, "aviso": aviso})
    return pol


# ----------------------------------------------------------------------------- HU-1.4 validación
@dataclass
class RevisionEvaluada:
    revision: RevisionRequisito
    valida: bool
    motivo: str = ""


def evaluar_para_validacion(expediente):
    """Revisa cada requisito con las reglas (incluida la vigencia en refrendo)."""
    resultado = []
    plazo = vigencia_refrendo(expediente)
    for r in expediente.revisiones.select_related("requisito", "documento"):
        if r.estado == EstadoRevision.NO_APLICA:
            resultado.append(RevisionEvaluada(r, True, "No aplica"))
        elif r.estado != EstadoRevision.ENTREGADO:
            resultado.append(RevisionEvaluada(r, False, r.get_estado_display()))
        elif r.en_archivo_probosque:
            if not expediente.es_refrendo or r.requisito.aplica_en_refrendo is not False:
                resultado.append(RevisionEvaluada(r, False, "Requisito que debe entregarse (no vale el archivo)"))
            elif documentacion_vigente(expediente, r.fecha_documento):
                resultado.append(RevisionEvaluada(
                    r, True, f"Refrendo: documentación de {r.fecha_documento:%d/%m/%Y}, vigente "
                             f"(hasta {plazo.texto_plazo})"))
            else:
                resultado.append(RevisionEvaluada(
                    r, False, f"Refrendo: documentación de {r.fecha_documento:%d/%m/%Y} con más de "
                              f"{plazo.texto_plazo if plazo else '—'}; no es válida"))
        elif not r.requisito.requiere_documento:
            resultado.append(RevisionEvaluada(r, True, "Cumple (condición sin documento)"))
        elif not r.documento_id:
            resultado.append(RevisionEvaluada(r, False, "Sin archivo digitalizado"))
        else:
            resultado.append(RevisionEvaluada(r, True, "Entregado"))
    return resultado


def validar_expediente(usuario, expediente, faltantes_ids=(), observaciones=""):
    """La Dirección valida el expediente o emite el aviso de faltantes con fecha límite.

    Los requisitos que no pasan la evaluación automática (por ejemplo, documentación de refrendo
    no vigente) se agregan siempre a los faltantes.
    """
    _exigir_unidad(usuario, TipoUnidad.DIRECCION)
    _exigir_acceso(usuario, expediente)
    evaluacion = evaluar_para_validacion(expediente)
    faltantes = {e.revision.pk: e for e in evaluacion if not e.valida}
    por_id = {e.revision.pk: e for e in evaluacion}
    for pk in faltantes_ids:
        pk = int(pk)
        if pk in por_id and pk not in faltantes:
            faltantes[pk] = RevisionEvaluada(por_id[pk].revision, False, "Señalado por la Dirección")
    detalle = [{"clave": e.revision.requisito.clave, "texto": e.revision.requisito.titulo,
                "estado": ("Faltante: " + faltantes[e.revision.pk].motivo) if e.revision.pk in faltantes else
                ("Válido: " + e.motivo)} for e in evaluacion]
    ahora = timezone.now()
    with transaction.atomic():
        if not faltantes:
            val = Validacion.objects.create(expediente=expediente, resultado=ResultadoValidacion.VALIDADO,
                                            usuario=usuario, fecha_hora=ahora, observaciones=observaciones,
                                            detalle=detalle)
            acuse = emitir_acuse(expediente, "validacion", "Constancia de validación del expediente", usuario,
                                 [("Resultado", "Expediente validado: cumple los requisitos de las reglas"),
                                  ("Fecha y hora", fmt_fecha_hora(ahora)),
                                  ("Observaciones", observaciones or "—")],
                                 destinatario=expediente.delegacion.nombre, detalle=detalle)
            val.acuse = acuse
            val.save(update_fields=["acuse"])
            expediente.cambiar_estado("validada", usuario, tipo_evento="validacion", acuse=acuse,
                                      descripcion="Expediente validado por la Dirección.")
            return val
        venc = plazos.vencimiento(expediente, "faltantes_direccion", fecha_evento=ahora)
        if venc is None or (not venc.tiene_fecha and not venc.sin_plazo_en_reglas):
            raise ValidationError("Las reglas del programa no tienen un plazo calculable para los faltantes.")
        # PEG: las reglas no dan plazo para completar (R-18); el aviso sale sin fecha límite y lo dice.
        limite = venc.vencimiento
        texto_limite = f"{limite:%d/%m/%Y}" if limite else plazos.SIN_PLAZO
        texto_plazo = (f"{venc.texto_plazo} ({venc.fundamento})" if limite else
                       f"{plazos.SIN_PLAZO} ({venc.fundamento or venc.nota})")
        val = Validacion.objects.create(
            expediente=expediente, resultado=ResultadoValidacion.FALTANTES, usuario=usuario, fecha_hora=ahora,
            observaciones=observaciones, detalle=detalle, fecha_limite=limite, plazo_aplicado=texto_plazo[:300],
        )
        val.faltantes.set(list(faltantes))
        RevisionRequisito.objects.filter(pk__in=list(faltantes)).update(estado=EstadoRevision.FALTANTE)
        acuse = emitir_acuse(
            expediente, "aviso_faltantes", "Aviso de faltantes", usuario,
            [("Fecha y hora del aviso", fmt_fecha_hora(ahora)),
             ("Fecha límite para entregar", texto_limite),
             ("Plazo aplicado", texto_plazo),
             ("Conducto", f"Por conducto de {expediente.delegacion.nombre}"),
             ("Observaciones", observaciones or "—")],
            destinatario=f"{expediente.solicitante.nombre}, por conducto de {expediente.delegacion.nombre}",
            detalle=[d for d in detalle if d["estado"].startswith("Faltante")],
        )
        val.acuse = acuse
        val.notificacion = notificaciones.emitir_notificacion(
            expediente, TipoNotificacion.FALTANTES, "Aviso de faltantes", usuario, acuse_envio=acuse, fecha_hora=ahora,
            datos={"validacion": val.pk, "fecha_limite": limite.isoformat() if limite else None},
        )
        val.save(update_fields=["acuse", "notificacion"])
        expediente.cambiar_estado("faltantes", usuario, tipo_evento="aviso_faltantes", acuse=acuse,
                                  descripcion=f"Aviso de faltantes ({len(faltantes)}) con fecha límite {texto_limite}.",
                                  datos={"fecha_limite": limite.isoformat() if limite else None})
    return val


def aviso_vigente(expediente):
    return expediente.validaciones.filter(resultado=ResultadoValidacion.FALTANTES).first()


def registrar_notificacion(usuario, validacion, medio=MedioNotificacion.PERSONAL, fecha_hora=None):
    """La Delegación registra que notificó el aviso de faltantes a la persona solicitante."""
    """Usa el servicio general del núcleo (``nucleo.notificaciones``)."""
    exp = validacion.expediente
    _exigir_unidad(usuario, TipoUnidad.DELEGACION)
    _exigir_acceso(usuario, exp)
    if validacion.notificado_en:
        raise ValidationError("El aviso ya se notificó.")
    if validacion.notificacion is None:
        raise ValidationError("El aviso no tiene notificación pendiente.")
    return notificaciones.registrar_notificacion(
        usuario, validacion.notificacion, medio=medio, fecha_hora=fecha_hora,
        titulo_acuse="Acuse de notificación del aviso de faltantes",
        renglones=[("Fecha límite para entregar", f"{validacion.fecha_limite:%d/%m/%Y}" if validacion.fecha_limite
                    else plazos.SIN_PLAZO)],
        detalle=[{"clave": r.requisito.clave, "texto": r.requisito.titulo, "estado": "Faltante"}
                 for r in validacion.faltantes.select_related("requisito")],
        descripcion="Aviso de faltantes notificado a la persona solicitante.",
    )


def plazo_recepcion(expediente):
    """Fecha límite para completar la documentación en la Delegación (desde la recepción, con tope)."""
    venc = plazos.vencimiento(expediente, "faltantes_ventanilla")
    return venc.vencimiento if venc else None
