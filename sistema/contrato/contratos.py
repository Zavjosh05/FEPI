"""HU-3.2 · Elaboración del contrato.

- Modelos de contrato (S2-04, R-07): las ROP no traen el texto; el área responsable del programa lo registra
  (plantilla con campos «{{campo}}») y la Unidad Jurídica lo **valida** (fecha y hora, quién, observaciones) o lo
  devuelve con observaciones. Un cambio del texto crea una versión nueva que vuelve a quedar sin validar.
- ``elaborar_contrato``: uno por solicitud aprobada, publicada y notificada, **solo sobre un modelo validado**
  (lo impide el servicio). Genera el PDF con los datos de la solicitud (persona, predio, municipio, superficie,
  monto y ministraciones de ``nucleo.montos``, modalidad y plazos). Se puede rehacer mientras no se envíe.
- ``enviar_a_delegacion``: fecha y hora del envío y acuse; el expediente pasa a la bandeja de la Delegación para la
  firma (HU-3.3).
"""
import hashlib
import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from dictamen.comun import exigir_programa, exigir_unidad
from nucleo import montos, plazos, reglas
from nucleo.acuses import _pdf, emitir_acuse
from nucleo.models import Consecutivo, Evento, TipoUnidad, expedientes_visibles
from nucleo.templatetags.moneda import formato_moneda

from .models import Contrato, EstadoContrato, EstadoVersion, ModeloContrato, TipoModelo, VersionModelo

CAMPOS = {
    "folio_contrato": "Folio del contrato",
    "programa": "Programa",
    "ejercicio": "Ejercicio (año)",
    "persona": "Persona beneficiaria",
    "tipo_persona": "Tipo de persona",
    "representante": "Representante (si lo hay)",
    "predio": "Nombre del predio",
    "folio_predio": "Folio del predio",
    "municipio": "Municipio",
    "delegacion": "Delegación Regional Forestal",
    "modalidad": "Modalidad o concepto de apoyo",
    "solicitante": "Persona solicitante (en PEG, el núcleo agrario)",
    "superficie_ha": "Superficie aprobada (ha)",
    "superficie_texto": "Superficie aprobada, como frase («, en una superficie aprobada de N hectáreas»; vacía si el programa no paga por hectárea)",
    "monto_por_hectarea": "Monto unitario (por hectárea, por apoyo o por persona)",
    "base_del_monto": "Base del monto («$2,000.00 por hectárea», «$30,000.00 por apoyo», «$25,550.00 por persona beneficiaria al año»)",
    "monto_total": "Monto total del apoyo",
    "ministraciones": "Ministraciones (número, porcentaje e importe)",
    "plazo_firma": "Plazo para la firma",
    "fecha_elaboracion": "Fecha de elaboración",
    "folio_solicitud": "Folio de la solicitud",
}
_CAMPO = re.compile(r"\{\{\s*(\w+)\s*\}\}")

MARCA_BORRADOR = "BORRADOR – modelo por validar"

PLANTILLAS_BASE = {
    TipoModelo.CONTRATO_ADHESION: MARCA_BORRADOR + """

CONTRATO DE ADHESIÓN {{folio_contrato}}

Que celebran, por una parte, la Protectora de Bosques del Estado de México (PROBOSQUE), por conducto de la {{delegacion}}, y por la otra {{persona}} ({{tipo_persona}}), en lo sucesivo «la persona beneficiaria», en el marco del programa {{programa}} {{ejercicio}} y de sus Reglas de Operación.

PRIMERA. Objeto. La persona beneficiaria se obliga a realizar las actividades comprometidas en su solicitud {{folio_solicitud}} en el predio «{{predio}}» (folio {{folio_predio}}), municipio de {{municipio}}, modalidad {{modalidad}}{{superficie_texto}}.

SEGUNDA. Apoyo. PROBOSQUE otorgará un apoyo de {{monto_total}} ({{base_del_monto}}), en las siguientes ministraciones: {{ministraciones}}.

TERCERA. Firma y vigencia. El presente contrato se firma dentro del plazo siguiente: {{plazo_firma}}. Su vigencia corre hasta el cumplimiento de las actividades comprometidas.

CUARTA. Obligaciones. La persona beneficiaria cumplirá las obligaciones de las Reglas de Operación del programa, permitirá las verificaciones en campo y reintegrará el recurso en los casos que ellas señalan.

Elaborado el {{fecha_elaboracion}}.
""",
    TipoModelo.CONVENIO_CONCERTACION: MARCA_BORRADOR + """

CONVENIO DE CONCERTACIÓN {{folio_contrato}}

Que celebran PROBOSQUE y la Comisión Nacional Forestal, por una parte, y por la otra {{persona}} ({{tipo_persona}}), en el marco del programa {{programa}} {{ejercicio}} (fondos concurrentes).

PRIMERA. Objeto. Incorporar el predio «{{predio}}» (folio {{folio_predio}}), municipio de {{municipio}}, con {{superficie_ha}} hectáreas, a la modalidad {{modalidad}}.

SEGUNDA. Apoyo. El apoyo es de {{monto_total}} ({{base_del_monto}}), en las ministraciones: {{ministraciones}}.

TERCERA. Firma. {{plazo_firma}}.

Elaborado el {{fecha_elaboracion}} para la solicitud {{folio_solicitud}}.
""",
    TipoModelo.ADENDUM: MARCA_BORRADOR + """

ADENDUM AL CONTRATO {{folio_contrato}}

Se modifica el contrato de {{persona}} para el predio «{{predio}}» ({{municipio}}) del programa {{programa}} {{ejercicio}}, en lo siguiente: (describa la modificación y el motivo).

Elaborado el {{fecha_elaboracion}}.
""",
}


# ----------------------------------------------------------------------------- permisos y textos
def _exigir_area(usuario, programa):
    from .publicacion import _ConPrograma

    exigir_unidad(usuario, TipoUnidad.DIRECCION)
    exigir_programa(usuario, _ConPrograma(programa))


def campos_desconocidos(texto):
    return sorted({c for c in _CAMPO.findall(texto or "") if c not in CAMPOS})


def _validar_texto(texto):
    if not (texto or "").strip():
        raise ValidationError("El modelo necesita su texto.")
    desconocidos = campos_desconocidos(texto)
    if desconocidos:
        raise ValidationError("Campos desconocidos en el modelo: " + ", ".join("{{" + c + "}}" for c in desconocidos)
                              + ". Los campos válidos están en la lista de la pantalla.")


def llenar(texto, datos):
    """Llena los campos «{{campo}}» con los datos (un campo sin dato queda como «—»)."""
    return _CAMPO.sub(lambda m: str(datos.get(m.group(1)) or "—"), texto)


# ----------------------------------------------------------------------------- modelos
def registrar_modelo(usuario, ejercicio, tipo, nombre, texto, es_base=False):
    """El área responsable registra un modelo (versión 1, por validar)."""
    _exigir_area(usuario, ejercicio.programa)
    if tipo not in TipoModelo.values:
        raise ValidationError("Tipo de modelo no reconocido.")
    if not (nombre or "").strip():
        raise ValidationError("El modelo necesita un nombre.")
    _validar_texto(texto)
    if ModeloContrato.objects.filter(ejercicio=ejercicio, tipo=tipo, nombre=nombre.strip()).exists():
        raise ValidationError("Ya existe un modelo de ese tipo con ese nombre; modifíquelo para crear otra versión.")
    with transaction.atomic():
        modelo = ModeloContrato.objects.create(ejercicio=ejercicio, tipo=tipo, nombre=nombre.strip(), es_base=es_base,
                                               creado_por=usuario)
        VersionModelo.objects.create(modelo=modelo, numero=1, texto=texto.strip(), creada_por=usuario)
    return modelo


def crear_plantilla_base(usuario, ejercicio, tipo=TipoModelo.CONTRATO_ADHESION):
    """Plantilla base propia, marcada visiblemente como «BORRADOR – modelo por validar»."""
    if tipo not in PLANTILLAS_BASE:
        raise ValidationError("Tipo de modelo no reconocido.")
    nombre = f"Plantilla base · {TipoModelo(tipo).label} ({MARCA_BORRADOR})"
    return registrar_modelo(usuario, ejercicio, tipo, nombre, PLANTILLAS_BASE[tipo], es_base=True)


def modificar_modelo(usuario, modelo, texto):
    """Cambia el texto: se crea una versión nueva, por validar (aunque la anterior estuviera validada)."""
    _exigir_area(usuario, modelo.ejercicio.programa)
    _validar_texto(texto)
    vigente = modelo.vigente
    if vigente.texto.strip() == texto.strip():
        raise ValidationError("El texto no cambió: no hay versión nueva que registrar.")
    return VersionModelo.objects.create(modelo=modelo, numero=vigente.numero + 1, texto=texto.strip(),
                                        creada_por=usuario)


def _revisar(usuario, version, estado, observaciones):
    exigir_unidad(usuario, TipoUnidad.JURIDICA)
    if version.modelo.vigente != version:
        raise ValidationError("Solo se valida la versión vigente del modelo.")
    if version.estado != EstadoVersion.PENDIENTE:
        raise ValidationError("Esta versión ya se revisó.")
    version.estado, version.revisada_por, version.revisada_en = estado, usuario, timezone.now()
    version.observaciones = (observaciones or "").strip()
    version.save(update_fields=["estado", "revisada_por", "revisada_en", "observaciones"])
    return version


def validar_version(usuario, version, observaciones=""):
    """La Unidad Jurídica valida la versión (fecha y hora, quién y observaciones)."""
    return _revisar(usuario, version, EstadoVersion.VALIDADA, observaciones)


def devolver_version(usuario, version, observaciones):
    """La Unidad Jurídica la devuelve con observaciones (obligatorias)."""
    if not (observaciones or "").strip():
        raise ValidationError("Al devolver un modelo hay que anotar las observaciones.")
    return _revisar(usuario, version, EstadoVersion.DEVUELTA, observaciones)


def modelos_por_validar():
    return [m for m in ModeloContrato.objects.select_related("ejercicio__programa") if m.vigente.estado == EstadoVersion.PENDIENTE]


def modelos_visibles(usuario):
    qs = ModeloContrato.objects.select_related("ejercicio__programa")
    if usuario.tipo_unidad == TipoUnidad.DIRECCION:
        qs = qs.filter(ejercicio__programa__in=usuario.unidad.programas.all())
    return qs


# ----------------------------------------------------------------------------- contrato
def tipo_requerido(expediente):
    """Contrato de Adhesión; Convenio de Concertación en PSAHEM con fondos concurrentes (MLPSA-FC)."""
    if expediente.programa.clave == "PSA" and expediente.modalidad and expediente.modalidad.clave == "fondos_concurrentes":
        return TipoModelo.CONVENIO_CONCERTACION
    return TipoModelo.CONTRATO_ADHESION


def modelos_elegibles(expediente):
    """Modelos validados del programa-ejercicio y del tipo que le toca al expediente."""
    return [m for m in ModeloContrato.objects.filter(ejercicio=expediente.ejercicio, tipo=tipo_requerido(expediente))
            if m.validado]


def datos_del_contrato(expediente, folio, ahora):
    m = montos.monto_aprobado(expediente)
    firma = plazos.vencimiento(expediente, "firma_programada")
    ministraciones = [f"{x.numero}.ª ministración, {x.porcentaje.normalize():f} % ({formato_moneda(x.importe)})"
                      for x in m.ministraciones] or ["sin ministraciones (concepto sin recurso económico)"]
    sol = expediente.solicitante
    persona, tipo_persona = sol.nombre, expediente.tipo_persona.nombre
    conf = reglas.persona_beneficiaria_distinta(expediente.ejercicio)
    if conf and expediente.persona_beneficiaria_id:
        # PEG: el contrato es de la persona Guardabosque; el núcleo agrario que la designó firma y sella (10.1 fr. XII).
        persona, tipo_persona = expediente.persona_beneficiaria.nombre, f"{conf['etiqueta']}, {sol.nombre}"
    superficie = f"{m.superficie_ha.normalize():f}"
    return {
        "folio_contrato": folio, "folio_solicitud": expediente.folio,
        "programa": expediente.programa.nombre, "ejercicio": str(expediente.ejercicio.anio),
        "persona": persona, "tipo_persona": tipo_persona, "solicitante": sol.nombre,
        "representante": sol.representante or "", "predio": expediente.predio.nombre,
        "folio_predio": expediente.predio.folio, "municipio": expediente.predio.municipio.nombre,
        "delegacion": expediente.delegacion.nombre,
        "modalidad": expediente.modalidad.nombre if expediente.modalidad else "—",
        "superficie_ha": superficie, "monto_por_hectarea": formato_moneda(m.monto_ha), "base_del_monto": m.texto_base,
        "superficie_texto": f", en una superficie aprobada de {superficie} hectáreas" if m.por_hectarea else "",
        "monto_total": formato_moneda(m.total), "ministraciones": "; ".join(ministraciones),
        "plazo_firma": firma.texto if firma else "las Reglas de Operación no fijan plazo para este programa",
        "fecha_elaboracion": f"{timezone.localtime(ahora):%d/%m/%Y}",
        # solo para el PDF (no se guardan en el JSON del contrato)
        "_detalle": [{"numero": x.numero, "porcentaje": f"{x.porcentaje.normalize():f}", "importe": formato_moneda(x.importe),
                      "condicion": x.condicion} for x in m.ministraciones],
        "_regimen": m.regimen_nombre or m.regimen,
        "_por_hectarea": m.por_hectarea, "_nota_monto": m.nota,
    }


def elaborar_contrato(usuario, expediente, modelo, momento=None):
    """Elabora (o rehace, si aún no se envía) el contrato del expediente sobre un modelo validado."""
    _exigir_area(usuario, expediente.programa)
    expediente.refresh_from_db()
    existente = Contrato.objects.filter(expediente=expediente).first()
    estado = expediente.estado.clave
    if existente and existente.enviado:
        raise ValidationError("El contrato ya se envió a la Delegación; no se rehace.")
    if existente is None and estado != "notificada":
        if estado == "aprobada":
            raise ValidationError("La solicitud está aprobada pero sus resultados aún no se publican.")
        if estado == "publicada":
            raise ValidationError("Falta que la Delegación notifique a la persona beneficiaria del resultado.")
        raise ValidationError(f"El expediente está «{expediente.estado}»; el contrato se elabora solo de una "
                              "solicitud aprobada, publicada y notificada.")
    if modelo.ejercicio_id != expediente.ejercicio_id:
        raise ValidationError("El modelo no es del programa y ejercicio de la solicitud.")
    tipo = tipo_requerido(expediente)
    if modelo.tipo != tipo:
        raise ValidationError(f"A esta solicitud le corresponde un modelo de {TipoModelo(tipo).label}.")
    version = modelo.vigente
    if version is None or version.estado != EstadoVersion.VALIDADA:
        raise ValidationError(f"El modelo «{modelo.nombre}» no está validado por la Unidad Jurídica: no se puede "
                              "elaborar un contrato sobre él.")
    ahora = momento or timezone.now()
    with transaction.atomic():
        folio = existente.folio if existente else (
            f"CTO-{expediente.programa.clave}-{expediente.ejercicio.anio}-"
            f"{Consecutivo.siguiente(f'contrato-{expediente.programa.clave}-{expediente.ejercicio.anio}'):04d}")
        datos = datos_del_contrato(expediente, folio, ahora)
        texto = llenar(version.texto, datos)
        html = render_to_string("contrato/contratos/contrato_pdf.html", {
            "texto": texto, "parrafos": [p.strip() for p in texto.split("\n\n") if p.strip()], "folio": folio,
            "expediente": expediente, "version": version, "tipo": TipoModelo(tipo).label, "datos": datos,
            "validada_en": timezone.localtime(version.revisada_en), "fecha": timezone.localtime(ahora),
            "ministraciones": datos["_detalle"], "regimen": datos["_regimen"],
        })
        pdf = _pdf(html)
        datos_json = {k: v for k, v in datos.items() if not k.startswith("_")}
        if existente:
            contrato = existente
            if contrato.archivo:
                contrato.archivo.delete(save=False)
            contrato.version_modelo, contrato.tipo, contrato.texto, contrato.datos = version, tipo, texto, datos_json
            contrato.elaborado_por, contrato.elaborado_en, contrato.rehechos = usuario, ahora, contrato.rehechos + 1
        else:
            contrato = Contrato(expediente=expediente, folio=folio, version_modelo=version, tipo=tipo, texto=texto,
                                datos=datos_json, elaborado_por=usuario, elaborado_en=ahora)
        contrato.huella = hashlib.sha256(pdf).hexdigest()
        contrato.archivo.save(f"{folio}.pdf", ContentFile(pdf), save=False)
        contrato.save()
        descripcion = (f"{TipoModelo(tipo).label} {folio} elaborado sobre «{modelo.nombre}», versión {version.numero}"
                       + (" (rehecho)" if existente else ""))
        if existente:
            Evento.registrar(expediente, usuario, "contrato_rehecho", descripcion, datos={"contrato": contrato.pk})
        else:
            expediente.cambiar_estado("contrato_elaborado", usuario, tipo_evento="contrato_elaborado",
                                      descripcion=descripcion, datos={"contrato": contrato.pk})
    return contrato


def enviar_a_delegacion(usuario, contrato, momento=None):
    """Envía el contrato a la Delegación: fecha y hora, acuse y paso a la bandeja de la Delegación."""
    exp = contrato.expediente
    _exigir_area(usuario, exp.programa)
    if contrato.enviado:
        raise ValidationError("El contrato ya se envió a la Delegación.")
    exp.refresh_from_db()
    if exp.estado.clave != "contrato_elaborado":
        raise ValidationError(f"El expediente está «{exp.estado}»; solo se envía un contrato elaborado.")
    ahora = momento or timezone.now()
    with transaction.atomic():
        acuse = emitir_acuse(
            exp, "envio_contrato", f"Envío del {TipoModelo(contrato.tipo).label.lower()} {contrato.folio} a la Delegación",
            usuario,
            [("Contrato", contrato.folio), ("Solicitud", exp.folio),
             ("Persona beneficiaria", exp.solicitante.nombre),
             ("Modelo", f"{contrato.version_modelo.modelo.nombre}, versión {contrato.version_modelo.numero}"),
             ("Huella del PDF (SHA-256)", contrato.huella),
             ("Envía", usuario.unidad.nombre), ("Delegación que lo recibe", exp.delegacion.nombre),
             ("Fecha y hora del envío", f"{timezone.localtime(ahora):%d/%m/%Y %H:%M:%S} h")],
            destinatario=exp.delegacion.nombre)
        contrato.estado, contrato.enviado_por, contrato.enviado_en, contrato.acuse_envio = (
            EstadoContrato.ENVIADO, usuario, ahora, acuse)
        contrato.save(update_fields=["estado", "enviado_por", "enviado_en", "acuse_envio"])
        exp.cambiar_estado("contrato_en_delegacion", usuario, tipo_evento="contrato_enviado", acuse=acuse,
                           descripcion=f"{contrato.folio} enviado a {exp.delegacion.nombre} para su firma",
                           datos={"contrato": contrato.pk})
    return acuse


# ----------------------------------------------------------------------------- consultas
def por_elaborar(usuario):
    return expedientes_visibles(usuario).filter(estado__clave="notificada")


def por_enviar(usuario):
    return expedientes_visibles(usuario).filter(estado__clave="contrato_elaborado")


def contratos_visibles(usuario):
    return Contrato.objects.filter(expediente__in=expedientes_visibles(usuario)).select_related(
        "expediente__predio__municipio", "expediente__ejercicio__programa", "expediente__solicitante",
        "version_modelo__modelo", "acuse_envio")
