"""HU-2.2 · Dictamen jurídico: revisión de la documentación legal, acreditación de la propiedad o legal posesión del
predio y cotejo con el Listado de Personas Beneficiarias Incumplidas y con los predios con procedimiento o sanción.

El dictamen solo puede ser procedente si cada documento legal es válido, si se acredita la propiedad o legal posesión
del predio a nombre del titular, por la superficie que se apoya, vigente y sin conflicto (CC 8.1.1.2 fr. VII; 8.1.1.1
fr. VII), y si no hay coincidencias en los catálogos (8.1.1.1 fr. I, II, III y V). Al registrarlo se expide su documento
en PDF, adjunto al expediente (``documentos.emitir_juridico``).
"""
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from nucleo.models import Evento, TipoUnidad
from nucleo.trazabilidad import registra_usuario
from recepcion.models import EstadoRevision

from . import documentos
from .comun import completar_si_ya_hay_dos, datos_dictamen, exigir_acceso, exigir_unidad
from .models import DictamenJuridico, PersonaIncumplida, PredioSancionado, ResultadoJuridico, RevisionPropiedad


def _normal(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(texto.upper().split())


def cotejar(expediente):
    """Coincidencias del titular y del predio con los catálogos (automático; se muestra en pantalla)."""
    titular = expediente.solicitante
    coincidencias = []
    filtro = Q(persona=titular)
    if titular.curp:
        filtro |= Q(curp__iexact=titular.curp)
    if titular.rfc:
        filtro |= Q(rfc__iexact=titular.rfc)
    candidatos = set(PersonaIncumplida.objects.filter(activa=True).filter(filtro))
    nombre = _normal(titular.nombre)
    for p in PersonaIncumplida.objects.filter(activa=True):
        if _normal(p.nombre) == nombre:
            candidatos.add(p)
    for p in sorted(candidatos, key=lambda x: x.pk):
        criterio = ("persona" if p.persona_id == titular.pk else "CURP" if titular.curp and p.curp.upper() == titular.curp.upper()
                    else "RFC" if titular.rfc and p.rfc.upper() == titular.rfc.upper() else "nombre")
        coincidencias.append({
            "catalogo": "Listado de Personas Beneficiarias Incumplidas", "id": p.pk, "nombre": p.nombre,
            "coincide_por": criterio, "motivo": p.motivo, "fecha": p.fecha_inscripcion.isoformat(),
            "fundamento": "CC 8.1.1.1 inelegibles fr. I y II",
        })
    predio = expediente.predio
    for s in PredioSancionado.objects.filter(activo=True, reintegro_realizado=False).filter(
            Q(predio=predio) | Q(descripcion_predio__iexact=predio.folio)):
        coincidencias.append({
            "catalogo": "Predios con procedimiento o sanción", "id": s.pk, "nombre": s.descripcion_predio,
            "coincide_por": "predio", "motivo": f"{s.get_tipo_display()}: {s.descripcion}", "fecha": s.fecha.isoformat(),
            "fundamento": "CC 8.1.1.1 inelegibles fr. III y V",
        })
    return coincidencias


# ----------------------------------------------------------------------------- documentación legal
def documentos_legales(expediente):
    """Revisiones de los requisitos que son documento legal (los revisa la Unidad Jurídica; los que no aplican se
    listan como «no aplica», sin revisión)."""
    return list(expediente.revisiones.filter(requisito__es_documento_legal=True).select_related("requisito", "documento"))


def revisar_documentacion(expediente, documentacion=None, exigir_revision=False):
    """Revisión jurídica de cada documento legal: [{clave, texto, estado, valido, observacion}].

    ``documentacion``: {clave: {"valido": bool, "observacion": str}}. Sin ella, vale lo que la Dirección validó (los
    entregados y los que no aplican son válidos). Un documento no válido debe llevar su observación."""
    documentacion = documentacion or {}
    filas, sin_marcar, sin_observacion = [], [], []
    for r in documentos_legales(expediente):
        clave = r.requisito.clave
        estado = r.get_estado_display() + (" (archivo PROBOSQUE)" if r.en_archivo_probosque else "")
        if r.estado == EstadoRevision.NO_APLICA:
            filas.append({"clave": clave, "texto": r.requisito.titulo, "estado": estado, "valido": True, "aplica": False,
                          "observacion": ""})
            continue
        marca = documentacion.get(clave)
        if marca is None or marca.get("valido") is None:
            if exigir_revision:
                sin_marcar.append(clave)
            valido = r.estado == EstadoRevision.ENTREGADO
            observacion = ""
        else:
            valido = bool(marca["valido"])
            observacion = (marca.get("observacion") or "").strip()
        if not valido and not observacion and marca is not None:
            sin_observacion.append(clave)
        filas.append({"clave": clave, "texto": r.requisito.titulo, "estado": estado, "valido": valido, "aplica": True,
                      "observacion": observacion})
    if sin_marcar:
        raise ValidationError("Marque como válido o no válido cada documento legal: " + ", ".join(sin_marcar) + ".")
    if sin_observacion:
        raise ValidationError("Escriba por qué no es válido cada documento legal que marca así: " + ", ".join(sin_observacion) + ".")
    return filas


# ----------------------------------------------------------------------------- propiedad o legal posesión
def tipos_documento_propiedad(expediente=None):
    tipos = datos_dictamen()["propiedad"]["tipos_documento"]
    if expediente is None:
        return tipos
    return [t for t in tipos if not t.get("personas") or expediente.tipo_persona.clave in t["personas"]]


def superficie_a_acreditar(expediente):
    """Superficie del polígono vigente; si no hay polígono, la solicitada."""
    poligono = expediente.poligonos.filter(vigente=True).first()
    if poligono is not None:
        return poligono.superficie_ha
    return expediente.superficie_solicitada_ha


def _decimal(valor):
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor))
    except InvalidOperation:
        raise ValidationError("La superficie que ampara el documento debe ser un número de hectáreas.")


def evaluar_propiedad(expediente, datos, hoy=None):
    """Evalúa la acreditación de la propiedad o legal posesión. Devuelve los campos de ``RevisionPropiedad``.

    ``datos``: tipo_documento, titular_documento, titular_coincide, superficie_documento_ha, vigente_hasta,
    sin_conflicto y, opcionales, numero_documento, fecha_documento y observaciones."""
    if not datos:
        raise ValidationError("Registre la revisión de la propiedad o legal posesión del predio (CC 8.1.1.2 fr. VII).")
    hoy = hoy or timezone.localdate()
    tipos = {t["clave"]: t for t in datos_dictamen()["propiedad"]["tipos_documento"]}
    tipo = tipos.get(datos.get("tipo_documento"))
    if tipo is None:
        raise ValidationError("Elija el documento con el que se acredita la propiedad o legal posesión del predio.")
    if not (datos.get("titular_documento") or "").strip():
        raise ValidationError("Escriba a nombre de quién está el documento de propiedad o posesión.")
    if datos.get("titular_coincide") is None or datos.get("sin_conflicto") is None:
        raise ValidationError("Indique si el documento está a nombre del titular y si hay evidencia de conflicto.")
    motivos = []
    if tipo.get("personas") and expediente.tipo_persona.clave not in tipo["personas"]:
        motivos.append(f"el documento ({tipo['nombre']}) no corresponde a {expediente.tipo_persona.nombre.lower()}")
    titular_coincide = bool(datos["titular_coincide"])
    if not titular_coincide:
        motivos.append("el documento no está a nombre del titular de la solicitud")
    superficie_doc = _decimal(datos.get("superficie_documento_ha"))
    superficie_predio = superficie_a_acreditar(expediente)
    if superficie_doc is None:
        suficiente = False
        motivos.append("el documento no indica la superficie del predio (integrar la constancia de superficie)")
    else:
        suficiente = superficie_predio is None or superficie_doc + Decimal("0.0001") >= Decimal(superficie_predio)
        if not suficiente:
            motivos.append(f"el documento ampara {superficie_doc} ha y el predio a apoyar tiene {superficie_predio} ha")
    vigente_hasta = datos.get("vigente_hasta")
    fecha_documento = datos.get("fecha_documento")
    vigente = True
    if tipo.get("requiere_vigencia"):
        if vigente_hasta is None:
            vigente = False
            motivos.append(f"{tipo['nombre'].split(' (')[0].lower()}: falta la fecha de vigencia")
        elif vigente_hasta < hoy:
            vigente = False
            motivos.append(f"el documento venció el {vigente_hasta:%d/%m/%Y}")
        maximo = tipo.get("vigencia_maxima_anios")
        if vigente and maximo and fecha_documento and vigente_hasta > date(fecha_documento.year + maximo, fecha_documento.month,
                                                                            min(fecha_documento.day, 28)):
            vigente = False
            motivos.append(f"el contrato excede el plazo máximo de {maximo} años")
    sin_conflicto = bool(datos["sin_conflicto"])
    if not sin_conflicto:
        motivos.append("hay evidencia de conflicto de propiedad, posesión o representación (8.1.1.1 fr. VII)")
    return {
        "tipo_documento": tipo["clave"], "nombre_documento": tipo["nombre"][:200],
        "numero_documento": (datos.get("numero_documento") or "").strip()[:120], "fecha_documento": fecha_documento,
        "titular_documento": datos["titular_documento"].strip()[:250], "titular_coincide": titular_coincide,
        "superficie_documento_ha": superficie_doc, "superficie_predio_ha": superficie_predio,
        "superficie_suficiente": suficiente, "vigente_hasta": vigente_hasta, "vigente": vigente,
        "sin_conflicto": sin_conflicto, "observaciones": (datos.get("observaciones") or "").strip(),
        "acreditada": not motivos, "motivos": motivos,
    }


# ----------------------------------------------------------------------------- dictamen
@registra_usuario
def dictaminar(usuario, expediente, resultado, motivo, propiedad=None, documentacion=None, exigir_revision=False):
    """La Unidad Jurídica emite el dictamen jurídico y se expide su documento en PDF.

    No puede ser procedente si un documento legal no es válido, si no se acredita la propiedad o legal posesión del
    predio, o si el titular o el predio aparecen en los catálogos. Con ``exigir_revision`` (el dictamen llega de la
    pantalla) cada documento legal debe quedar marcado."""
    exigir_unidad(usuario, TipoUnidad.JURIDICA)
    exigir_acceso(usuario, expediente)
    if expediente.estado.clave != "validada":
        raise ValidationError(f"El expediente está «{expediente.estado}»; solo se dictamina un expediente validado.")
    if hasattr(expediente, "dictamen_juridico"):
        raise ValidationError("El expediente ya tiene dictamen jurídico.")
    if resultado not in ResultadoJuridico.values:
        raise ValidationError("El resultado debe ser procedente o no procedente.")
    if not (motivo or "").strip():
        raise ValidationError("El dictamen jurídico debe llevar su motivo.")
    revision_documentos = revisar_documentacion(expediente, documentacion, exigir_revision)
    revision_propiedad = evaluar_propiedad(expediente, propiedad)
    coincidencias = cotejar(expediente)
    if resultado == ResultadoJuridico.PROCEDENTE:
        if coincidencias:
            nombres = "; ".join(f"{c['catalogo']}: {c['nombre']}" for c in coincidencias)
            raise ValidationError(f"No puede ser procedente: el titular o el predio está en {nombres} "
                                  "(ROP CC 8.1.1.1, inelegibles).")
        no_validos = [d["clave"] for d in revision_documentos if not d["valido"]]
        if no_validos:
            raise ValidationError("No puede ser procedente: hay documentos legales no válidos (" + ", ".join(no_validos) + ").")
        if not revision_propiedad["acreditada"]:
            raise ValidationError("No puede ser procedente: no se acredita la propiedad o legal posesión del predio ("
                                  + "; ".join(revision_propiedad["motivos"]) + ").")
    ahora = timezone.now()
    with transaction.atomic():
        dictamen = DictamenJuridico.objects.create(expediente=expediente, resultado=resultado, motivo=motivo.strip(),
                                                   cotejo=coincidencias, documentacion=revision_documentos, usuario=usuario,
                                                   fecha_hora=ahora)
        RevisionPropiedad.objects.create(dictamen=dictamen, **revision_propiedad)
        documento = documentos.emitir_juridico(dictamen)
        Evento.registrar(expediente, usuario, "dictamen_juridico",
                         f"Dictamen jurídico {dictamen.folio} {dictamen.get_resultado_display().lower()}: {dictamen.motivo}",
                         datos={"resultado": resultado, "coincidencias": len(coincidencias), "documento": documento.pk,
                                "folio": dictamen.folio, "propiedad_acreditada": revision_propiedad["acreditada"]})
        completar_si_ya_hay_dos(expediente, usuario)
    return dictamen


@registra_usuario
def registrar_incumplida(usuario, **datos):
    exigir_unidad(usuario, TipoUnidad.JURIDICA)
    if not datos.get("nombre") or not datos.get("motivo"):
        raise ValidationError("Escriba el nombre y el motivo de la inscripción.")
    return PersonaIncumplida.objects.create(registrado_por=usuario, **datos)


@registra_usuario
def registrar_predio_sancionado(usuario, **datos):
    exigir_unidad(usuario, TipoUnidad.JURIDICA)
    if not datos.get("descripcion_predio") or not datos.get("descripcion"):
        raise ValidationError("Escriba el predio y la descripción del procedimiento o sanción.")
    return PredioSancionado.objects.create(registrado_por=usuario, **datos)


@registra_usuario
def dar_de_baja(usuario, registro, motivo):
    """Baja del Listado (no se borra: queda en su historial)."""
    exigir_unidad(usuario, TipoUnidad.JURIDICA)
    if not (motivo or "").strip():
        raise ValidationError("Indique el motivo de la baja.")
    if isinstance(registro, PersonaIncumplida):
        registro.activa = False
    else:
        registro.activo = False
    registro._change_reason = motivo[:100]
    registro.save()
    return registro
