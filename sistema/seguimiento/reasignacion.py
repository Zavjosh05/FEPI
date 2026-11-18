"""HU-6.1 · Lista de espera y sustituciones.

- **Recurso liberado** (``RecursoLiberado``): lo registra el sistema cuando el área responsable confirma la liberación de un
  contrato sin firma en plazo (``extensiones.AL_LIBERAR_RECURSO``), cuando el Comité da de baja por desistimiento, por
  fallecimiento sin sustitución o por caso fortuito, y cuando la verificación ajusta la superficie (lo que ya no se pagará).
  HU-6.2 suma la cancelación y el reintegro depositado.
- **Propuesta de reasignación** (``proponer_reasignacion``): el área responsable del programa reúne el recurso liberado del
  ejercicio y recorre la **lista de espera en su orden** (lugar del acta del Comité): cuánto se liberó, de qué expedientes y a
  quiénes alcanza (``datos/seguimiento.json`` → ``reasignacion``: por omisión se detiene en la primera a la que ya no le alcanza,
  decisión propia). La propuesta tiene su acuse y queda en la bandeja de la Secretaría Técnica.
- **Solicitudes de la persona** (``registrar_solicitud``): aviso del fallecimiento de la persona titular (hito
  ``fallecimiento_titular``), solicitud de sustitución por la segunda persona beneficiaria (con el plazo de las reglas,
  ``interes_segunda_beneficiaria``) y desistimiento por escrito (en núcleos agrarios, firmas de Presidencia, Secretaría y
  Tesorería y el sello). Se reciben en la Delegación o desde el portal con el mismo servicio; cada una con su acuse (fecha y
  hora) y el expediente pasa a «sustitución o desistimiento en trámite».
- **Propuestas por expediente** (``proponer``): sustitución, baja por desistimiento o por fallecimiento sin sustitución,
  atención del caso fortuito (continuar con la meta ajustada o terminar sin sanción) y apoyo con sobrevivencia menor por causas no
  imputables (PS y RHF). Cada propuesta dice el recurso que libera.
- **Comité** (``llevar_a_sesion``): la Secretaría Técnica registra el acuerdo de la propuesta en una sesión de seguimiento
  (aprobada o no) con el tipo de acuerdo de HU-2.4; el área responsable del programa lo cumple y entonces se ejecuta
  (``ejecutar_acuerdo``, registrado en ``dictamen.seguimiento.RECEPTORES``): las reasignadas pasan a «aprobada» y la Delegación
  les notifica el resultado (firman con la fecha límite propia de las reasignadas); la persona sustituta queda como persona
  beneficiaria (con historial); la baja libera el recurso. Un acuerdo que no viene de una propuesta solo deja constancia.
- **Prórroga por causa externa (MFS, flujo G)**: ``solicitar_prorroga`` y ``resolver_prorroga`` (adendum); quién la pide y quién
  la autoriza son parámetros (supuesto, R-17).
"""
import hashlib
from decimal import Decimal
from functools import lru_cache

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from dictamen import seguimiento as dictamen_seguimiento
from dictamen.comun import exigir_acceso, exigir_programa, exigir_unidad
from dictamen.models import EstadoSesion, ResolucionSesion, ResultadoListado, TipoSesion
from nucleo import montos, notificaciones, plazos
from nucleo.acuses import emitir_acuse
from nucleo.catalogos import leer_json
from nucleo.models import Evento, Expediente, Persona, TipoUnidad, Unidad
from nucleo.templatetags.moneda import formato_moneda
from portal import cuentas

from .models import EstadoPropuesta, MedioSolicitud, Propuesta, Prorroga, RecursoLiberado, SolicitudPersona

CERO = Decimal("0")
CENTAVO = Decimal("0.01")
# Estados desde los que se recibe una solicitud de sustitución, desistimiento o aviso de fallecimiento (datos/flujo_tramite.json).
ESTADOS_SOLICITUD = ("publicada", "notificada", "contrato_elaborado", "contrato_en_delegacion", "contratada", "planta_entregada",
                     "pagada", "cheque_entregado", "en_ejecucion", "comprobacion_enviada", "verificada", "caso_fortuito")


# ----------------------------------------------------------------------------- datos
@lru_cache(maxsize=2)
def _datos(ruta):
    return leer_json(ruta)


def datos_seguimiento():
    return _datos(str(settings.DATOS_DIR / "seguimiento.json"))


def _fmt(valor):
    return f"{timezone.localtime(valor):%d/%m/%Y %H:%M:%S} h"


def direccion_del_programa(ejercicio):
    return Unidad.objects.filter(tipo=TipoUnidad.DIRECCION, programas=ejercicio.programa_id).order_by("pk").first()


def _exigir_area(usuario, ejercicio):
    exigir_unidad(usuario, TipoUnidad.DIRECCION)
    if not usuario.unidad.programas.filter(pk=ejercicio.programa_id).exists():
        raise PermissionDenied("Su Dirección no es Instancia Ejecutora de este programa.")


def _leer_archivo(archivo):
    if archivo is None or not getattr(archivo, "name", ""):
        return None, ""
    nombre = archivo.name.rsplit("/", 1)[-1]
    if not nombre.lower().endswith(tuple(datos_seguimiento()["extensiones_archivo"])):
        raise ValidationError("El documento debe ser PDF, JPG o PNG.")
    archivo.seek(0)
    contenido = archivo.read()
    if not contenido:
        raise ValidationError("El archivo está vacío.")
    return contenido, nombre


# ----------------------------------------------------------------------------- montos
def total_aprobado(expediente):
    """Monto aprobado del expediente sin el ajuste de la verificación (lo que el Comité asignó)."""
    m = montos.monto_aprobado(expediente, superficie=montos.superficie_aprobada(expediente))
    return m.total or CERO


def ministrado(expediente):
    """Lo ya pagado al expediente (ministraciones pagadas; en PSAHEM, con el cheque entregado)."""
    return expediente.solicitudes_pago.filter(estado="pagada").aggregate(t=Sum("importe"))["t"] or CERO


def por_ministrar(expediente):
    return max(CERO, total_aprobado(expediente) - ministrado(expediente))


# ----------------------------------------------------------------------------- recurso liberado
def registrar_recurso(expediente, origen, monto, usuario=None, referencia="", descripcion="", momento=None, ejercicio=None):
    """Recurso que queda libre para reasignarse (idempotente por expediente, origen y referencia)."""
    monto = Decimal(monto or 0).quantize(CENTAVO)
    if monto <= 0:
        return None
    ejercicio = ejercicio or expediente.ejercicio
    existente = RecursoLiberado.objects.filter(ejercicio=ejercicio, expediente=expediente, origen=origen,
                                               referencia=referencia[:120]).first() if expediente is not None else None
    if existente is not None:
        return existente
    r = RecursoLiberado.objects.create(
        ejercicio=ejercicio, expediente=expediente, origen=origen, monto=monto, referencia=referencia[:120],
        descripcion=descripcion[:300], liberado_en=momento or timezone.now(), registrado_por=usuario)
    if expediente is not None:
        Evento.registrar(expediente, usuario, "recurso_liberado_registrado",
                         f"Recurso liberado para la lista de espera: {formato_moneda(monto)} ({r.nombre_origen.lower()}).",
                         datos={"recurso": r.pk})
    return r


def al_liberar_recurso(expediente, usuario):
    """``extensiones.AL_LIBERAR_RECURSO`` (HU-3.3): el recurso del contrato sin firma queda para la lista de espera."""
    senal = getattr(expediente, "sin_firma", None)
    referencia = senal.acuse_liberacion.folio if senal is not None and senal.acuse_liberacion_id else "sin firma"
    registrar_recurso(expediente, "sin_firma", por_ministrar(expediente), usuario, referencia,
                      "Contrato sin firma en plazo: recurso liberado por el área responsable.")


def materializar_ajustes(ejercicio):
    """Ajuste de superficie (HU-4.2): lo aprobado que ya no se pagará porque se verificó menos superficie."""
    from ejecucion.models import Verificacion

    vistos = set()
    for v in (Verificacion.objects.filter(expediente__ejercicio=ejercicio, total_verificado__isnull=False)
              .select_related("expediente").order_by("-registrada_en", "-id")):
        if v.expediente_id in vistos:
            continue
        vistos.add(v.expediente_id)
        exp = v.expediente
        m = montos.monto_aprobado(exp, superficie=montos.superficie_aprobada(exp))
        original = next((x.importe for x in m.ministraciones if x.numero == v.ministracion_ajustada), None)
        if original is None or m.total is None:
            continue
        otras = m.total - original                      # lo que se paga sin depender de la verificación
        liberado = m.total - max(otras, v.total_verificado)   # lo aprobado que ya no se pagará
        registrar_recurso(exp, "ajuste_superficie", liberado, None, v.acuse.folio if v.acuse_id else f"Verificación {v.pk}",
                          f"Se verificaron {v.verificada_texto} de {v.aprobada_texto} ha.", v.registrada_en)


def recursos_disponibles(ejercicio):
    materializar_ajustes(ejercicio)
    return (RecursoLiberado.objects.filter(ejercicio=ejercicio, propuesta__isnull=True, reasignado_en__isnull=True)
            .select_related("expediente").order_by("liberado_en", "id"))


def lista_de_espera(ejercicio):
    """Solicitudes del ejercicio que siguen en lista de espera, en su orden: ``[{"expediente", "lugar", "monto", "sesion"}]``."""
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
        monto = r.monto if r.monto is not None else (montos.monto_aprobado(r.expediente).total or CERO)
        lista.append({"expediente": r.expediente, "lugar": r.orden, "monto": monto, "sesion": r.sesion})
    return lista


def calcular(ejercicio, recursos=None):
    """La propuesta de reasignación antes de enviarla: recurso liberado, lista de espera en orden y a quiénes alcanza."""
    cfg = datos_seguimiento()["reasignacion"]
    recursos = list(recursos_disponibles(ejercicio) if recursos is None else recursos)
    total = sum((r.monto for r in recursos), CERO)
    disponible, renglones, detenida = total, [], False
    for i, x in enumerate(lista_de_espera(ejercicio), 1):
        alcanza = not detenida and x["monto"] <= disponible
        if alcanza:
            disponible -= x["monto"]
        elif not cfg.get("saltar_si_no_alcanza"):
            detenida = True
        renglones.append({**x, "posicion": i, "alcanza": alcanza, "saldo": disponible if alcanza else None})
    return {"recursos": recursos, "total": total, "renglones": renglones, "asignado": total - disponible, "saldo": disponible,
            "alcanzadas": [r for r in renglones if r["alcanza"]], "regla": cfg["regla_orden"],
            "fundamento": cfg["programas"].get(ejercicio.programa.clave, {}).get("fundamento", "")}


def proponer_reasignacion(usuario, ejercicio, observaciones="", momento=None):
    """El área responsable propone al Comité la reasignación del recurso liberado a la lista de espera (con acuse)."""
    _exigir_area(usuario, ejercicio)
    calculo = calcular(ejercicio)
    if calculo["total"] <= 0:
        raise ValidationError("No hay recurso liberado por reasignar en este ejercicio.")
    if not calculo["renglones"]:
        raise ValidationError("No hay solicitudes en la lista de espera del ejercicio.")
    if not calculo["alcanzadas"]:
        primera = calculo["renglones"][0]
        raise ValidationError(f"El recurso liberado ({formato_moneda(calculo['total'])}) no alcanza para la primera solicitud de "
                              f"la lista de espera ({primera['expediente'].folio}, {formato_moneda(primera['monto'])}).")
    ahora = momento or timezone.now()
    alcanzadas = [r["expediente"] for r in calculo["alcanzadas"]]
    texto = (f"Reasignar {formato_moneda(calculo['asignado'])} del recurso liberado ({formato_moneda(calculo['total'])}) a "
             + ", ".join(f"{r['expediente'].folio} (lugar {r['lugar']}, {formato_moneda(r['monto'])})" for r in calculo["alcanzadas"])
             + f", en el orden de la lista de espera. Saldo: {formato_moneda(calculo['saldo'])}.")
    with transaction.atomic():
        p = Propuesta.objects.create(
            ejercicio=ejercicio, tipo="reasignacion", descripcion=texto, fundamento=calculo["fundamento"][:400],
            monto_liberado=calculo["total"], monto_asignado=calculo["asignado"], saldo=calculo["saldo"], creada_por=usuario,
            unidad=usuario.unidad, creada_en=ahora,
            datos={"observaciones": (observaciones or "").strip(), "regla": calculo["regla"],
                   "recursos": [{"id": r.pk, "folio": r.expediente.folio if r.expediente_id else "", "origen": r.nombre_origen,
                                 "monto": str(r.monto), "referencia": r.referencia} for r in calculo["recursos"]],
                   "renglones": [{"expediente": r["expediente"].pk, "folio": r["expediente"].folio, "lugar": r["lugar"],
                                  "posicion": r["posicion"], "persona": r["expediente"].solicitante.nombre,
                                  "monto": str(r["monto"]), "alcanza": r["alcanza"],
                                  "saldo": str(r["saldo"]) if r["saldo"] is not None else None} for r in calculo["renglones"]]})
        p.expedientes.set(alcanzadas)
        RecursoLiberado.objects.filter(pk__in=[r.pk for r in calculo["recursos"]]).update(propuesta=p)
        detalle = ([{"clave": "Liberado", "texto": f"{r.expediente.folio if r.expediente_id else 'Saldo'} · {r.nombre_origen} · "
                     f"{r.referencia}"[:200], "estado": formato_moneda(r.monto)} for r in calculo["recursos"]]
                   + [{"clave": f"Lugar {r['lugar']}", "texto": f"{r['expediente'].folio} · {r['expediente'].solicitante.nombre} · "
                       f"{formato_moneda(r['monto'])}"[:200], "estado": "Alcanza" if r["alcanza"] else "No alcanza"}
                      for r in calculo["renglones"]])
        p.acuse = emitir_acuse(
            None, "propuesta_reasignacion", f"Propuesta de reasignación del recurso liberado ({ejercicio.programa.nombre} "
            f"{ejercicio.anio})", usuario,
            [("Programa", f"{ejercicio.programa.nombre} {ejercicio.anio}"), ("Fecha y hora", _fmt(ahora)),
             ("Recurso liberado", f"{formato_moneda(calculo['total'])} de {len(calculo['recursos'])} expediente(s)"),
             ("Se reasigna", formato_moneda(calculo["asignado"])), ("Saldo", formato_moneda(calculo["saldo"])),
             ("Orden", calculo["regla"]), ("Fundamento", calculo["fundamento"]), ("Propone", usuario.unidad.nombre)],
            destinatario="Secretaría Técnica del Comité", referencia=f"Propuesta de reasignación {p.pk}", detalle=detalle,
            encabezado_detalle=["Concepto", "Expediente", "Monto o resultado"])
        p.save(update_fields=["acuse"])
        for e in alcanzadas:
            Evento.registrar(e, usuario, "propuesta_reasignacion",
                             f"Propuesta de reasignación al Comité: alcanza el recurso liberado ({p.acuse.folio}).",
                             acuse=p.acuse, datos={"propuesta": p.pk})
    return p


# ----------------------------------------------------------------------------- solicitudes de la persona
def tipos_solicitud(expediente):
    d = datos_seguimiento()["solicitudes"]
    propios = d["programas"].get(expediente.programa.clave, {}).get("tipos", [])
    return [{**d["tipos"][t], "clave": t} for t in propios]


def tipo_solicitud(expediente, clave):
    t = next((x for x in tipos_solicitud(expediente) if x["clave"] == clave), None)
    if t is None:
        raise ValidationError(f"{expediente.programa.nombre} no recibe «{clave}».")
    return t


def fundamento_solicitud(expediente, clave):
    prog = datos_seguimiento()["solicitudes"]["programas"].get(expediente.programa.clave, {})
    return prog.get("fundamento_desistimiento" if clave == "desistimiento" else "fundamento_sustitucion", "")


def puntos_firma(expediente):
    """Puntos de firma y sello que se verifican en un desistimiento, por tipo de persona (datos)."""
    cfg = datos_seguimiento()["solicitudes"]["firmas_desistimiento"]
    clave = expediente.tipo_persona.clave
    return list(cfg.get(clave) or cfg["por_omision"])


def puede_solicitar(expediente):
    if expediente.estado.clave not in ESTADOS_SOLICITUD and expediente.estado.clave != "sustitucion":
        return False, f"El expediente está «{expediente.estado}»: no recibe solicitudes de sustitución ni desistimientos."
    return True, ""


def _medio(usuario, expediente):
    if cuentas.es_externo(usuario):
        if not cuentas.expedientes_de(usuario).filter(pk=expediente.pk).exists():
            raise PermissionDenied("El expediente no es suyo.")
        return MedioSolicitud.PORTAL
    if usuario.tipo_unidad == TipoUnidad.DELEGACION and usuario.unidad_id == expediente.delegacion_id:
        return MedioSolicitud.VENTANILLA
    raise PermissionDenied("La solicitud la presenta la persona desde el portal o la recibe la Delegación del expediente.")


def ultimo_fallecimiento(expediente):
    return expediente.solicitudes_seguimiento.filter(tipo="fallecimiento").order_by("-presentada_en", "-id").first()


def registrar_solicitud(usuario, expediente, tipo, archivo=None, persona_presenta="", motivo="", fecha_hecho=None,
                        segunda=None, causa="", firmas=(), momento=None):
    """Registra la solicitud de sustitución, el desistimiento o el aviso de fallecimiento, con su acuse (fecha y hora).

    ``segunda``: ``{"nombre", "curp", "telefono", "parentesco"}`` (sustitución). ``firmas``: puntos verificados del
    desistimiento (``puntos_firma``)."""
    medio = _medio(usuario, expediente)
    expediente.refresh_from_db()
    puede, motivo_no = puede_solicitar(expediente)
    if not puede:
        raise ValidationError(motivo_no)
    t = tipo_solicitud(expediente, tipo)
    portal = medio == MedioSolicitud.PORTAL
    if portal and not t.get("portal"):
        raise ValidationError(f"«{t['nombre']}» se presenta en la Delegación.")
    ahora = momento or timezone.now()
    hoy = timezone.localtime(ahora).date()
    contenido, nombre_archivo = _leer_archivo(archivo)
    if contenido is None and t.get("requiere_archivo"):
        raise ValidationError(f"Falta el documento: {t['nombre'].lower()}.")
    if t.get("pide_fecha_hecho"):
        if not fecha_hecho:
            raise ValidationError(f"Falta la {t['pide_fecha_hecho'].lower()}.")
        if fecha_hecho > hoy:
            raise ValidationError("La fecha del fallecimiento no puede ser posterior al aviso.")
    else:
        fecha_hecho = None
    persona = None
    if t.get("pide_segunda_persona"):
        segunda = segunda or {}
        if not (segunda.get("nombre") or "").strip():
            raise ValidationError("Escriba el nombre de la segunda persona beneficiaria.")
        causa = causa or ("fallecimiento" if ultimo_fallecimiento(expediente) else "imposibilidad")
        if causa not in ("fallecimiento", "imposibilidad"):
            raise ValidationError("La sustitución es por fallecimiento de la persona titular o por su imposibilidad.")
        if causa == "fallecimiento" and ultimo_fallecimiento(expediente) is None:
            raise ValidationError("Primero se registra el aviso del fallecimiento de la persona titular (con su fecha).")
        if causa == "imposibilidad" and not (motivo or "").strip():
            raise ValidationError("Escriba la causa justificada por la que la persona titular no puede continuar.")
    else:
        causa = ""
    puntos = []
    if t.get("pide_firmas"):
        requeridos = puntos_firma(expediente)
        marcados = set(firmas or ())
        faltan = [p for p in requeridos if p not in marcados]
        if faltan:
            raise ValidationError("El escrito no se recibe sin: " + "; ".join(faltan).lower() + ".")
        puntos = requeridos
        if not (motivo or "").strip():
            raise ValidationError("El desistimiento debe decir sus motivos.")
    quien = (persona_presenta or "").strip() or ((segunda or {}).get("nombre", "").strip() if t.get("pide_segunda_persona")
                                                else expediente.beneficiaria.nombre)
    estado_previo = expediente.estado.clave
    with transaction.atomic():
        if t.get("pide_segunda_persona"):
            persona = Persona.objects.create(tipo="fisica", nombre=segunda["nombre"].strip()[:250],
                                             curp=(segunda.get("curp") or "").strip().upper()[:18],
                                             telefono=(segunda.get("telefono") or "").strip()[:40])
        s = SolicitudPersona(expediente=expediente, tipo=tipo, nombre=t["nombre"][:200], medio=medio, presentada_en=ahora,
                             presentada_por=usuario, persona_presenta=quien[:250], motivo=(motivo or "").strip(),
                             fecha_hecho=fecha_hecho, segunda_persona=persona, causa=causa, firmas=puntos,
                             estado_al_presentar=estado_previo,
                             datos={"parentesco": (segunda or {}).get("parentesco", "")} if persona else {})
        if contenido is not None:
            s.huella = hashlib.sha256(contenido).hexdigest()
            s.archivo.save(f"{tipo}_{nombre_archivo}", ContentFile(contenido), save=False)
        s.save()
        if t.get("hito"):
            from datetime import datetime, time

            plazos.registrar_hito(expediente, t["hito"], usuario,
                                  timezone.make_aware(datetime.combine(fecha_hecho, time(12, 0))) if fecha_hecho else ahora,
                                  referencia=t["nombre"][:90], datos={"solicitud": s.pk})
        if tipo == "sustitucion" and causa == "fallecimiento":
            v = plazos.vencimiento(expediente, "interes_segunda_beneficiaria")
            if v is not None:
                s.plazo_texto = f"{v.nombre}: {v.texto}"[:300]
                if v.tiene_fecha:
                    s.vence, s.en_plazo = v.vencimiento, hoy <= v.vencimiento
        s.acuse = _acuse_solicitud(s, expediente, t, usuario, portal)
        s.save()
        Evento.registrar(expediente, usuario, f"solicitud_{tipo}",
                         f"{t['nombre']} {'enviada desde el portal' if portal else 'recibida en la Delegación'} el {_fmt(ahora)}"
                         + (f" ({s.situacion_plazo})" if s.en_plazo is not None else "") + ".",
                         acuse=s.acuse, datos={"solicitud": s.pk})
        if expediente.estado.clave != "sustitucion":
            expediente.cambiar_estado(
                "sustitucion", None if portal else usuario, por_sistema=portal, tipo_evento="sustitucion_estado",
                acuse=s.acuse, descripcion=f"{t['nombre']} con el acuse {s.acuse.folio}"
                + (f", enviada por {usuario.get_full_name() or usuario.username} desde el portal" if portal else "") + ".",
                datos={"solicitud": s.pk})
    return s


def _acuse_solicitud(s, expediente, t, usuario, portal):
    renglones = [("Solicitud", t["nombre"]), ("Expediente", f"{expediente.folio} · {expediente.programa.nombre}"),
                 ("Persona beneficiaria", expediente.beneficiaria.nombre), ("Medio", s.get_medio_display()),
                 ("Fecha y hora", _fmt(s.presentada_en)), ("Presenta", s.persona_presenta)]
    if portal:
        renglones.append(("Cuenta del portal", usuario.username))
    else:
        renglones.append(("Recibe", f"{usuario.get_full_name() or usuario.username}, {usuario.unidad.nombre}"))
    if s.fecha_hecho:
        renglones.append(("Fecha del fallecimiento", f"{s.fecha_hecho:%d/%m/%Y}"))
    if s.segunda_persona_id:
        renglones.append(("Segunda persona beneficiaria", s.segunda_persona.nombre
                          + (f" (CURP {s.segunda_persona.curp})" if s.segunda_persona.curp else "")))
        renglones.append(("Causa", "Fallecimiento de la persona titular" if s.causa == "fallecimiento"
                          else "Imposibilidad de la persona titular con causa justificada"))
    if s.motivo:
        renglones.append(("Motivos", s.motivo))
    if s.huella:
        renglones.append(("Documento", f"{s.nombre_archivo} (SHA-256 {s.huella[:16]}…)"))
    if s.plazo_texto:
        renglones.append(("Plazo", s.plazo_texto + (f" · {s.situacion_plazo.upper()}" if s.en_plazo is not None else "")))
    renglones.append(("Fundamento", fundamento_solicitud(expediente, s.tipo)))
    detalle = [{"clave": "Firma o sello", "texto": p, "estado": "Verificado"} for p in s.firmas]
    nota = "Fuera de plazo: se registra igual y queda señalado; el Comité resuelve." if s.en_plazo is False else \
        "El área responsable la analiza y la propone al Comité, que resuelve en su sesión de seguimiento."
    return emitir_acuse(expediente, f"solicitud_{s.tipo}", f"{t['nombre']} · {expediente.folio}", usuario, renglones,
                        destinatario="Instancia Normativa (Comité), por conducto del área responsable", detalle=detalle,
                        nota=nota, encabezado_detalle=["Punto", "Verificación", "Estado"])


# ----------------------------------------------------------------------------- propuestas por expediente
def tipos_propuesta(expediente):
    """Propuestas que el área puede hacer ahora para el expediente: ``[(clave, nombre)]``."""
    nombres = {k: v["nombre"] for k, v in datos_seguimiento()["propuestas"]["tipos"].items()}
    estado = expediente.estado.clave
    if propuesta_abierta(expediente) is not None:
        return []  # una propuesta a la vez por expediente
    tipos = []
    if estado == "sustitucion":
        pendientes = {s.tipo for s in expediente.solicitudes_seguimiento.filter(propuesta__isnull=True)}
        if "sustitucion" in pendientes:
            tipos.append("sustitucion")
        if "desistimiento" in pendientes:
            tipos.append("desistimiento")
        if "fallecimiento" in pendientes or ultimo_fallecimiento(expediente):
            tipos.append("fallecimiento")
    especiales = datos_seguimiento()["casos_especiales"].get(expediente.programa.clave, {})
    if estado == "caso_fortuito" and "caso_fortuito" in especiales:
        tipos.append("caso_fortuito")
    if estado == "verificada" and "sobrevivencia_menor" in especiales:
        from ejecucion import verificacion

        v = verificacion.vigente(expediente)
        if v is not None and v.resultado == "incumplimiento" and v.sobrevivencia_pct is not None \
                and not (v.datos or {}).get("aprobada_por_comite") \
                and any("sobrevivencia" in m for m in (v.datos or {}).get("motivos_incumplimiento", [])):
            tipos.append("sobrevivencia_menor")
    from . import incumplimientos  # HU-6.2: cancelación, suspensión y bajas

    tipos += incumplimientos.tipos_propuesta(None, expediente)
    return [(t, nombres[t]) for t in dict.fromkeys(tipos)]


def propuesta_abierta(expediente):
    return expediente.propuestas_seguimiento.exclude(estado=EstadoPropuesta.EJECUTADA).order_by("-creada_en").first()


def estado_previo(expediente):
    """El estado del que salió el expediente al entrar al estado actual (para volver a él)."""
    e = expediente.eventos.filter(estado_destino=expediente.estado).order_by("-fecha_hora", "-id").first()
    return e.estado_origen.clave if e is not None and e.estado_origen_id else None


def proponer(usuario, expediente, tipo, descripcion="", resolucion="", momento=None, base="ministrado"):
    """Propuesta al Comité para un expediente (sustitución, baja, caso fortuito, sobrevivencia menor), con su acuse."""
    _exigir_area(usuario, expediente.ejercicio)
    exigir_acceso(usuario, expediente)
    expediente.refresh_from_db()
    disponibles = dict(tipos_propuesta(expediente))
    if tipo not in disponibles:
        raise ValidationError("Esa propuesta no procede para el expediente en su estado actual "
                              f"(«{expediente.estado}»), o ya hay una propuesta en trámite.")
    cfg_tipos = datos_seguimiento()["propuestas"]
    resoluciones = cfg_tipos["resoluciones_caso_fortuito"]
    if tipo == "caso_fortuito" and resolucion not in resoluciones:
        raise ValidationError("Elija qué se propone para el caso fortuito: " + " o ".join(resoluciones.values()).lower() + ".")
    ahora = momento or timezone.now()
    solicitud = (expediente.solicitudes_seguimiento.filter(tipo=tipo, propuesta__isnull=True).order_by("-presentada_en").first()
                 if tipo in ("sustitucion", "desistimiento") else
                 ultimo_fallecimiento(expediente) if tipo == "fallecimiento" else None)
    total, pagado = total_aprobado(expediente), ministrado(expediente)
    libera = CERO
    datos = {"resolucion": resolucion, "estado_previo": estado_previo(expediente), "ministrado": str(pagado),
             "total_aprobado": str(total)}
    if tipo in ("desistimiento", "fallecimiento") or (tipo == "caso_fortuito" and resolucion == "liberar"):
        libera = max(CERO, total - pagado)
    cfg_tipo = cfg_tipos["tipos"][tipo]
    if cfg_tipo.get("listado"):                      # HU-6.2: cancelación y bajas
        from . import incumplimientos

        if base not in datos_seguimiento()["incumplimientos"]["reintegro"]["bases"]:
            raise ValidationError("Base del reintegro no reconocida.")
        libera = por_ministrar(expediente)
        datos["base"] = base
        datos["por_devolver"] = str(incumplimientos.monto_por_devolver(expediente, base))
    if tipo == "sustitucion":
        datos["persona_nueva"] = solicitud.segunda_persona_id
        datos["persona_anterior"] = expediente.beneficiaria.pk
    especiales = datos_seguimiento()["casos_especiales"].get(expediente.programa.clave, {})
    if tipo in ("cancelacion", "baja_cheque", "baja_reportes", "suspension", "levantar_suspension"):
        from . import incumplimientos

        fundamento = incumplimientos._sancion(expediente, "suspension_temporal" if "suspension" in tipo else "baja_del_programa",
                                              "cancelacion_baja")
    else:
        fundamento = (especiales.get(tipo) or fundamento_solicitud(expediente, "desistimiento" if tipo == "desistimiento" else "sustitucion"))
    texto = (descripcion or "").strip() or _texto_propuesta(expediente, tipo, solicitud, resolucion, libera, pagado, resoluciones)
    with transaction.atomic():
        p = Propuesta.objects.create(
            ejercicio=expediente.ejercicio, tipo=tipo, descripcion=texto, fundamento=fundamento[:400], monto_liberado=libera,
            creada_por=usuario, unidad=usuario.unidad, creada_en=ahora, datos=datos)
        p.expedientes.set([expediente])
        ligadas = [solicitud] + ([ultimo_fallecimiento(expediente)] if tipo == "sustitucion" else [])
        for s in ligadas:
            if s is not None and s.propuesta_id is None:
                s.propuesta = p
                s.save(update_fields=["propuesta"])
        renglones = [("Propuesta", p.nombre_tipo), ("Expediente", f"{expediente.folio} · {expediente.programa.nombre}"),
                     ("Persona beneficiaria", expediente.beneficiaria.nombre), ("Texto propuesto como acuerdo", texto),
                     ("Recurso liberado", formato_moneda(libera) if libera else "Ninguno: el apoyo continúa"),
                     ("Ministrado a la fecha", formato_moneda(pagado)), ("Fecha y hora", _fmt(ahora)),
                     ("Fundamento", fundamento), ("Propone", usuario.unidad.nombre)]
        if solicitud is not None and solicitud.acuse_id:
            renglones.insert(3, ("Solicitud de la persona", f"{solicitud.nombre} ({solicitud.acuse.folio})"))
        p.acuse = emitir_acuse(expediente, "propuesta_comite", f"Propuesta al Comité: {p.nombre_tipo.lower()}", usuario,
                               renglones, destinatario="Secretaría Técnica del Comité", referencia=f"Propuesta {p.pk}")
        p.save(update_fields=["acuse"])
        Evento.registrar(expediente, usuario, "propuesta_comite", f"Propuesta al Comité: {p.nombre_tipo.lower()} ({p.acuse.folio}).",
                         acuse=p.acuse, datos={"propuesta": p.pk})
    return p


def _texto_propuesta(expediente, tipo, solicitud, resolucion, libera, pagado, resoluciones):
    if tipo == "sustitucion":
        return (f"Aprobar la sustitución de la persona beneficiaria {expediente.beneficiaria.nombre} por "
                f"{solicitud.segunda_persona.nombre}, segunda persona beneficiaria, en el expediente {expediente.folio}.")
    if tipo in ("desistimiento", "fallecimiento"):
        causa = "por desistimiento por escrito" if tipo == "desistimiento" else "por fallecimiento de la persona titular sin sustitución"
        texto = f"Dar de baja el expediente {expediente.folio} {causa} y liberar {formato_moneda(libera)} para la lista de espera."
        if pagado:
            texto += f" Lo ministrado ({formato_moneda(pagado)}) se debe reintegrar de inmediato."
        return texto
    if tipo in ("cancelacion", "baja_cheque", "baja_reportes"):
        return (f"Cancelar el apoyo del expediente {expediente.folio} y dar de baja a {expediente.beneficiaria.nombre}; inscribirla en "
                f"el Listado de Personas Beneficiarias Incumplidas y requerir la devolución; liberar {formato_moneda(libera)} no "
                "ministrados para la lista de espera.")
    if tipo == "suspension":
        return f"Suspender temporalmente el apoyo del expediente {expediente.folio} para que se subsanen las omisiones."
    if tipo == "levantar_suspension":
        return f"Levantar la suspensión del apoyo del expediente {expediente.folio}."
    if tipo == "caso_fortuito":
        return f"Atender el caso fortuito del expediente {expediente.folio}: {resoluciones[resolucion].lower()}" + (
            f"; se liberan {formato_moneda(libera)}." if libera else ".")
    return (f"Aprobar el apoyo del expediente {expediente.folio} aunque la sobrevivencia no alcanzó la mínima, por causas no "
            "imputables a la persona beneficiaria.")


# ----------------------------------------------------------------------------- Comité
def propuestas_por_llevar(ejercicio=None):
    qs = Propuesta.objects.filter(estado=EstadoPropuesta.ENVIADA).select_related("ejercicio__programa", "acuse", "unidad")
    return qs.filter(ejercicio=ejercicio) if ejercicio is not None else qs


def sesiones_para(propuesta):
    return propuesta.ejercicio.sesiones.filter(tipo=TipoSesion.SEGUIMIENTO, convocatoria_enviada__isnull=False).exclude(
        estado=EstadoSesion.CELEBRADA).order_by("fecha_hora")


def llevar_a_sesion(usuario, propuesta, sesion, aprueba=True, descripcion=""):
    """La Secretaría Técnica registra el acuerdo del Comité sobre la propuesta (aprobada o no) en una sesión de seguimiento.
    El acuerdo lo cumple el área responsable del programa; al cumplirlo se ejecuta (``ejecutar_acuerdo``)."""
    exigir_unidad(usuario, TipoUnidad.SECRETARIA_COMITE)
    if propuesta.estado != EstadoPropuesta.ENVIADA:
        raise ValidationError("La propuesta ya se llevó al Comité.")
    if sesion.ejercicio_id != propuesta.ejercicio_id:
        raise ValidationError("La sesión debe ser del programa y ejercicio de la propuesta.")
    tipo = datos_seguimiento()["propuestas"]["tipos"][propuesta.tipo]["acuerdo"]
    texto = (descripcion or "").strip() or (("Se aprueba: " if aprueba else "No se aprueba: ") + propuesta.descripcion)
    with transaction.atomic():
        acuerdo = dictamen_seguimiento.registrar_acuerdo(usuario, sesion, tipo, texto, list(propuesta.expedientes.all()),
                                                        dictamen_seguimiento.unidad_sugerida(tipo, propuesta.ejercicio))
        propuesta.acuerdo, propuesta.aprobada, propuesta.estado = acuerdo, bool(aprueba), EstadoPropuesta.EN_SESION
        propuesta.save(update_fields=["acuerdo", "aprobada", "estado"])
    return acuerdo


def ejecutar_acuerdo(acuerdo):
    """``dictamen.seguimiento.RECEPTORES``: al cumplir el acuerdo, se ejecuta la propuesta que lo originó (si la hay)."""
    propuesta = Propuesta.objects.filter(acuerdo=acuerdo).first()
    if propuesta is None or propuesta.estado == EstadoPropuesta.EJECUTADA:
        return  # acuerdo registrado sin propuesta: solo constancia (HU-2.4)
    usuario = acuerdo.cumplido_por
    ejecuta = datos_seguimiento()["propuestas"].get("unidad_que_ejecuta", {})
    requerida = ejecuta.get(propuesta.tipo, ejecuta.get("por_omision", TipoUnidad.DIRECCION))
    if usuario.tipo_unidad != requerida:
        raise ValidationError(f"Este acuerdo lo cumple {TipoUnidad(requerida).label}.")
    EJECUTORES.get(propuesta.tipo, _sin_efecto)(propuesta, acuerdo, usuario)
    propuesta.estado, propuesta.ejecutada_en = EstadoPropuesta.EJECUTADA, timezone.now()
    propuesta.save(update_fields=["estado", "ejecutada_en"])


def _sin_efecto(propuesta, acuerdo, usuario):
    return None


def _motivo(acuerdo):
    return f"Acuerdo {acuerdo.numero} del Comité ({acuerdo.sesion.numero})."


def _volver(exp, usuario, acuerdo, previo, texto):
    """Regresa el expediente al estado del que salió (sustitución aprobada o propuesta no aprobada)."""
    exp.refresh_from_db()
    destino = previo or "en_ejecucion"
    exp.cambiar_estado(destino, usuario, motivo=_motivo(acuerdo), tipo_evento="acuerdo_ejecutado", descripcion=texto,
                       datos={"acuerdo": acuerdo.pk})


def _ejecutar_reasignacion(propuesta, acuerdo, usuario):
    ahora = timezone.now()
    if not propuesta.aprobada:
        propuesta.recursos.update(propuesta=None)
        return
    for r in propuesta.datos.get("renglones", []):
        if not r["alcanza"]:
            continue
        exp = Expediente.objects.get(pk=r["expediente"])
        if exp.estado.clave != "lista_espera":
            raise ValidationError(f"{exp.folio} ya no está en la lista de espera («{exp.estado}»).")
        exp.cambiar_estado("aprobada", usuario, motivo=_motivo(acuerdo), tipo_evento="reasignacion",
                           descripcion=f"Aprobada por reasignación del recurso liberado (lugar {r['lugar']} de la lista de "
                                       f"espera; acuerdo {acuerdo.numero}).", datos={"propuesta": propuesta.pk, "acuerdo": acuerdo.pk})
        plazos.registrar_hito(exp, "aprobacion_comite", usuario, ahora, referencia=f"Acuerdo {acuerdo.numero}",
                              datos={"acuerdo": acuerdo.pk, "reasignacion": propuesta.pk})
        firma = plazos.vencimiento(exp, "firma_liberacion")
        notificaciones.emitir_notificacion(
            exp, "resultados", f"Resultado de su solicitud {exp.folio}: aprobada por reasignación", usuario,
            renglones=[("Resultado", "Su solicitud fue aprobada por reasignación del recurso liberado: usted es persona beneficiaria"),
                       ("Acuerdo del Comité", f"{acuerdo.numero} ({acuerdo.sesion.numero})"),
                       ("Monto asignado", formato_moneda(Decimal(r["monto"]))),
                       ("Firma del contrato", "corre desde esta notificación" + (f"; {firma.config.get('nota', '')}" if firma else ""))],
            datos={"reasignacion": propuesta.pk, "acuerdo": acuerdo.pk})
    propuesta.recursos.update(reasignado_en=ahora)
    if propuesta.saldo and propuesta.saldo > 0:
        registrar_recurso(None, "saldo", propuesta.saldo, usuario, f"Propuesta {propuesta.pk}",
                          f"Saldo de la reasignación del acuerdo {acuerdo.numero}.", ejercicio=propuesta.ejercicio)


def _ejecutar_sustitucion(propuesta, acuerdo, usuario):
    exp = propuesta.expedientes.get()
    previo = propuesta.datos.get("estado_previo")
    if not propuesta.aprobada:
        _volver(exp, usuario, acuerdo, previo, f"El Comité no aprobó la sustitución (acuerdo {acuerdo.numero}); sigue la persona "
                                               "beneficiaria anterior.")
        return
    nueva = Persona.objects.get(pk=propuesta.datos["persona_nueva"])
    anterior = exp.beneficiaria
    exp.refresh_from_db()
    exp._change_reason = f"Sustitución de la persona beneficiaria (acuerdo {acuerdo.numero})"
    exp.persona_beneficiaria = nueva
    exp.save(update_fields=["persona_beneficiaria", "actualizado"])
    Evento.registrar(exp, usuario, "sustitucion_beneficiaria",
                     f"Persona beneficiaria sustituida: {anterior.nombre} → {nueva.nombre} (acuerdo {acuerdo.numero}).",
                     datos={"anterior": anterior.pk, "nueva": nueva.pk, "acuerdo": acuerdo.pk})
    _volver(exp, usuario, acuerdo, previo, f"Continúa con la persona sustituta {nueva.nombre} (acuerdo {acuerdo.numero}).")


def _ejecutar_baja(propuesta, acuerdo, usuario):
    exp = propuesta.expedientes.get()
    previo = propuesta.datos.get("estado_previo")
    if not propuesta.aprobada:
        _volver(exp, usuario, acuerdo, previo, f"El Comité no aprobó la baja (acuerdo {acuerdo.numero}).")
        return
    exp.refresh_from_db()
    pagado = ministrado(exp)
    destino = "cancelada" if pagado > 0 else "recurso_liberado"
    exp.cambiar_estado(destino, usuario, motivo=_motivo(acuerdo), tipo_evento="baja_por_acuerdo",
                       descripcion=f"{propuesta.nombre_tipo} (acuerdo {acuerdo.numero})"
                       + (f"; lo ministrado ({formato_moneda(pagado)}) se debe reintegrar." if pagado else "."),
                       datos={"acuerdo": acuerdo.pk, "propuesta": propuesta.pk})
    registrar_recurso(exp, propuesta.tipo if propuesta.tipo in ("desistimiento", "fallecimiento") else "caso_fortuito",
                      max(CERO, total_aprobado(exp) - pagado), usuario, f"Acuerdo {acuerdo.numero}", propuesta.nombre_tipo)
    if destino == "cancelada":  # HU-6.2: lo ministrado se requiere a la persona (sin inscripción en el Listado)
        from . import incumplimientos

        incumplimientos.preparar_requerimiento(exp, propuesta.nombre_tipo, propuesta, acuerdo)


def _ejecutar_caso_fortuito(propuesta, acuerdo, usuario):
    exp = propuesta.expedientes.get()
    if propuesta.aprobada and propuesta.datos.get("resolucion") == "liberar":
        exp.refresh_from_db()
        exp.cambiar_estado("recurso_liberado", usuario, motivo=_motivo(acuerdo), tipo_evento="baja_por_acuerdo",
                           descripcion=f"Caso fortuito: apoyo terminado sin sanción (acuerdo {acuerdo.numero}).",
                           datos={"acuerdo": acuerdo.pk})
        registrar_recurso(exp, "caso_fortuito", por_ministrar(exp), usuario, f"Acuerdo {acuerdo.numero}", "Caso fortuito")
        return
    texto = (f"Reanuda con la meta ajustada (acuerdo {acuerdo.numero})." if propuesta.aprobada else
             f"El Comité no aprobó la propuesta del caso fortuito (acuerdo {acuerdo.numero}); se reanuda.")
    _volver(exp, usuario, acuerdo, propuesta.datos.get("estado_previo"), texto)


def _ejecutar_sobrevivencia(propuesta, acuerdo, usuario):
    from ejecucion import verificacion

    exp = propuesta.expedientes.get()
    if not propuesta.aprobada:
        return
    v = verificacion.vigente(exp)
    v.datos = {**(v.datos or {}), "aprobada_por_comite": acuerdo.numero}
    v.save(update_fields=["datos"])
    Evento.registrar(exp, usuario, "sobrevivencia_menor_aprobada",
                     f"El Comité aprobó el apoyo con sobrevivencia menor por causas no imputables (acuerdo {acuerdo.numero}): "
                     "la siguiente ministración ya se puede solicitar.", datos={"acuerdo": acuerdo.pk})


EJECUTORES = {"reasignacion": _ejecutar_reasignacion, "sustitucion": _ejecutar_sustitucion, "desistimiento": _ejecutar_baja,
              "fallecimiento": _ejecutar_baja, "caso_fortuito": _ejecutar_caso_fortuito,
              "sobrevivencia_menor": _ejecutar_sobrevivencia}


def al_notificar(notificacion):
    """``extensiones.AL_NOTIFICAR``: notificada la aprobación por reasignación, el expediente pasa a «notificada» y desde ahí
    corre su firma (``evento_reasignada`` de ``firma_programada`` y ``firma_liberacion``)."""
    if notificacion.tipo != "resultados" or not (notificacion.datos or {}).get("reasignacion"):
        return
    exp = notificacion.expediente
    exp.refresh_from_db()
    if exp.estado.clave == "aprobada":
        exp.cambiar_estado("notificada", notificacion.notificada_por, acuse=notificacion.acuse_notificacion,
                           tipo_evento="reasignacion_notificada",
                           descripcion="Persona notificada de su aprobación por reasignación del recurso liberado.",
                           datos={"notificacion": notificacion.pk})


# ----------------------------------------------------------------------------- consultas
def solicitudes_visibles(usuario):
    from nucleo.models import expedientes_visibles

    return SolicitudPersona.objects.filter(expediente__in=expedientes_visibles(usuario)).select_related(
        "expediente__ejercicio__programa", "expediente__estado", "acuse", "propuesta", "segunda_persona")


def solicitudes_por_proponer(usuario):
    """Dirección: solicitudes recibidas de sus programas sin propuesta al Comité."""
    if usuario.tipo_unidad != TipoUnidad.DIRECCION:
        return SolicitudPersona.objects.none()
    return solicitudes_visibles(usuario).filter(propuesta__isnull=True, expediente__estado__clave="sustitucion").order_by("presentada_en")


def propuestas_visibles(usuario):
    qs = Propuesta.objects.select_related("ejercicio__programa", "acuse", "acuerdo__sesion", "unidad").prefetch_related("expedientes")
    if usuario.tipo_unidad == TipoUnidad.DIRECCION:
        return qs.filter(ejercicio__programa__in=usuario.unidad.programas.all())
    if usuario.tipo_unidad in (TipoUnidad.SECRETARIA_COMITE, TipoUnidad.JURIDICA) or usuario.is_superuser:
        return qs
    return qs.none()


def ejercicios_con_lista(usuario):
    """Dirección: por ejercicio de sus programas, el recurso liberado disponible y la lista de espera."""
    from nucleo.models import Ejercicio

    if usuario.tipo_unidad != TipoUnidad.DIRECCION:
        return []
    filas = []
    for ej in Ejercicio.objects.filter(programa__in=usuario.unidad.programas.all()).select_related("programa").order_by("programa__clave"):
        calculo = calcular(ej)
        if calculo["total"] or calculo["renglones"]:
            filas.append({"ejercicio": ej, **calculo})
    return filas


# ----------------------------------------------------------------------------- prórroga por causa externa (MFS)
def config_prorroga(expediente):
    cfg = datos_seguimiento()["prorroga"]
    return cfg if expediente.programa.clave in cfg["programas"] else None


def solicitar_prorroga(usuario, expediente, causa, plazo_solicitado=None, archivo=None, plazo_original=None, momento=None):
    """La Delegación registra la solicitud de prórroga por causa externa con su acuse (supuesto: R-17)."""
    cfg = config_prorroga(expediente)
    if cfg is None:
        raise ValidationError(f"{expediente.programa.nombre} no prevé prórroga por causa externa.")
    if usuario.tipo_unidad != cfg["solicita"] or (usuario.tipo_unidad == TipoUnidad.DELEGACION
                                                 and usuario.unidad_id != expediente.delegacion_id):
        raise PermissionDenied("La solicitud de prórroga la registra la Delegación del expediente (supuesto, R-17).")
    if not (causa or "").strip():
        raise ValidationError("Describa la causa externa por la que no se cumplió la meta.")
    expediente.refresh_from_db()
    ahora = momento or timezone.now()
    contenido, nombre_archivo = _leer_archivo(archivo)
    with transaction.atomic():
        p = Prorroga(expediente=expediente, causa=causa.strip(), plazo_original=plazo_original, plazo_solicitado=plazo_solicitado,
                     solicitada_en=ahora, solicitada_por=usuario, estado_al_solicitar=expediente.estado.clave)
        if contenido is not None:
            p.archivo.save(f"prorroga_{nombre_archivo}", ContentFile(contenido), save=False)
        p.save()
        p.acuse = emitir_acuse(expediente, "solicitud_prorroga", f"Solicitud de prórroga por causa externa · {expediente.folio}",
                               usuario, [("Expediente", f"{expediente.folio} · {expediente.programa.nombre}"),
                                         ("Persona beneficiaria", expediente.beneficiaria.nombre), ("Causa externa", p.causa),
                                         ("Plazo solicitado", f"{plazo_solicitado:%d/%m/%Y}" if plazo_solicitado else "—"),
                                         ("Fecha y hora", _fmt(ahora)), ("Recibe", usuario.unidad.nombre),
                                         ("Fundamento", cfg["fundamento"])],
                               destinatario="Área responsable del programa", nota=cfg["supuesto"])
        p.save(update_fields=["acuse"])
        expediente.cambiar_estado("prorroga_solicitada", usuario, tipo_evento="prorroga_solicitada", acuse=p.acuse,
                                  descripcion=f"Solicitud de prórroga por causa externa ({p.acuse.folio}).", datos={"prorroga": p.pk})
    return p


def resolver_prorroga(usuario, prorroga, autorizada, motivo, plazo_nuevo=None, archivo_adendum=None, momento=None):
    """El área responsable resuelve la prórroga: autorizada con el adendum al contrato (plazo nuevo) o negada (supuesto)."""
    from contrato.models import Adendum

    exp = prorroga.expediente
    cfg = config_prorroga(exp)
    if usuario.tipo_unidad != cfg["autoriza"]:
        raise PermissionDenied("La prórroga la resuelve el área responsable del programa (supuesto, R-17).")
    exigir_programa(usuario, exp)
    if prorroga.autorizada is not None:
        raise ValidationError("La prórroga ya se resolvió.")
    if not (motivo or "").strip():
        raise ValidationError("Escriba el motivo de la resolución.")
    contrato = getattr(exp, "contrato", None)
    if autorizada and (plazo_nuevo is None or contrato is None):
        raise ValidationError("La prórroga autorizada necesita el contrato del expediente y el plazo nuevo del adendum.")
    ahora = momento or timezone.now()
    contenido, nombre_archivo = _leer_archivo(archivo_adendum)
    with transaction.atomic():
        if autorizada:
            a = Adendum(contrato=contrato, motivo=prorroga.causa, plazo_original=prorroga.plazo_original, plazo_nuevo=plazo_nuevo,
                        creado_por=usuario, creado_en=ahora)
            if contenido is not None:
                a.archivo.save(f"adendum_{nombre_archivo}", ContentFile(contenido), save=False)
            a.save()
            prorroga.adendum = a
        prorroga.autorizada, prorroga.resuelta_en, prorroga.resuelta_por = bool(autorizada), ahora, usuario
        prorroga.motivo_resolucion = motivo.strip()
        prorroga.acuse_resolucion = emitir_acuse(
            exp, "resolucion_prorroga", f"Resolución de la prórroga · {exp.folio}", usuario,
            [("Resolución", "Autorizada con adendum" if autorizada else "Negada"), ("Motivo", motivo.strip()),
             ("Plazo nuevo", f"{plazo_nuevo:%d/%m/%Y}" if autorizada else "—"), ("Fecha y hora", _fmt(ahora)),
             ("Resuelve", usuario.unidad.nombre), ("Fundamento", cfg["fundamento"])],
            destinatario=exp.beneficiaria.nombre, nota=cfg["supuesto"])
        prorroga.save()
        exp.cambiar_estado("en_ejecucion", usuario, motivo=motivo.strip(), tipo_evento="prorroga_resuelta",
                           acuse=prorroga.acuse_resolucion,
                           descripcion=("Prórroga autorizada con adendum hasta el " + f"{plazo_nuevo:%d/%m/%Y}") if autorizada
                           else "Prórroga negada.", datos={"prorroga": prorroga.pk})
        notificaciones.emitir_notificacion(exp, "otro", f"Resolución de la prórroga de {exp.folio}", usuario,
                                           acuse_envio=prorroga.acuse_resolucion, destinatario=exp.beneficiaria,
                                           renglones=[("Resolución", "Autorizada con adendum" if autorizada else "Negada"),
                                                      ("Motivo", motivo.strip())])
    return prorroga
