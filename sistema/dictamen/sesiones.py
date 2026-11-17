"""Sesiones del Comité (comunes a la aprobación y al seguimiento): creación, documentos y convocatoria.

La Secretaría Técnica expide la convocatoria con el orden del día, con la anticipación de las reglas
del programa (CC 9.4.2: 3 días hábiles las ordinarias, 24 horas las extraordinarias).
"""
from datetime import datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from nucleo import dias_habiles
from nucleo.acuses import emitir_acuse
from nucleo.catalogos import leer_json
from nucleo.models import Consecutivo, TipoUnidad

from .comun import datos_dictamen, exigir_unidad
from .models import CaracterSesion, DocumentoSesion, EstadoSesion, SesionComite


def _invitados(comite):
    """Invitados del Comité: listas o textos de las reglas (PEG trae permanentes en lista y especiales en un texto)."""
    invitados = []
    for clave in ("invitados_permanentes_solo_voz", "invitados_especiales_solo_voz"):
        valor = comite.get(clave)
        if isinstance(valor, list):
            invitados += valor
        elif valor:
            invitados.append(valor)
    return invitados


def integrantes_comite(ejercicio):
    """Integrantes del Comité del programa: de las reglas (``instancias.comite``; en PSAHEM
    ``instancias.comite_tecnico``, el Comité Técnico del FIPASAHEM) o de reglas/catalogos.json."""
    from django.conf import settings

    instancias = (ejercicio.datos or {}).get("instancias") or {}
    comite = instancias.get("comite") or instancias.get("comite_tecnico")
    if comite:
        return {
            "nombre": comite.get("nombre", ""), "fundamento": f"{comite.get('numeral', '')} (línea {comite.get('linea', '')})",
            "presidencia": comite.get("presidencia", ""), "secretaria_tecnica": comite.get("secretaria_tecnica", ""),
            "vocales": comite.get("vocales_con_voz_y_voto", []), "invitados": _invitados(comite),
            "composicion": comite.get("integracion", ""),
        }
    catalogo = leer_json(settings.REGLAS_DIR / "catalogos.json")
    clave = {"PSA": "PSAHEM"}.get(ejercicio.programa.clave, ejercicio.programa.clave)
    for c in catalogo.get("comites", []):
        if c.get("programa") == clave:
            return {"nombre": c["nombre"], "fundamento": f"líneas {c.get('lineas')}", "composicion": c.get("composicion", ""),
                    "presidencia": "", "secretaria_tecnica": "", "vocales": [], "invitados": []}
    return {"nombre": f"Comité del programa {ejercicio.programa.clave}", "vocales": [], "invitados": []}


def crear_sesion(usuario, ejercicio, tipo, fecha_hora, lugar, orden_del_dia, caracter=CaracterSesion.ORDINARIA,
                 presupuesto=None):
    exigir_unidad(usuario, TipoUnidad.SECRETARIA_COMITE)
    if not orden_del_dia.strip():
        raise ValidationError("La convocatoria debe llevar el orden del día.")
    n = Consecutivo.siguiente(f"sesion-{ejercicio.programa.clave}-{ejercicio.anio}")
    numero = f"{'SO' if caracter == CaracterSesion.ORDINARIA else 'SE'}-{ejercicio.programa.clave}-{ejercicio.anio}-{n:02d}"
    return SesionComite.objects.create(
        ejercicio=ejercicio, tipo=tipo, caracter=caracter, numero=numero, fecha_hora=fecha_hora, lugar=lugar,
        orden_del_dia=orden_del_dia, integrantes=integrantes_comite(ejercicio), presupuesto=presupuesto, creada_por=usuario,
    )


def agregar_documento(usuario, sesion, archivo, nombre=""):
    exigir_unidad(usuario, TipoUnidad.SECRETARIA_COMITE)
    if sesion.estado == EstadoSesion.CELEBRADA:
        raise ValidationError("La sesión ya tiene acta; no se agregan documentos.")
    return DocumentoSesion.objects.create(sesion=sesion, nombre=nombre or archivo.name, archivo=archivo,
                                          registrado_por=usuario)


def anticipacion_requerida(sesion):
    """(texto, fecha y hora límite para enviar la convocatoria) según el plazo de las reglas."""
    clave = datos_dictamen()["plazos"]["convocatoria_comite"]
    plazo = sesion.ejercicio.plazo(clave)
    if plazo is None:
        return None, None
    cantidad, texto_plazo = plazo.cantidad, plazo.texto_plazo
    if sesion.caracter == CaracterSesion.EXTRAORDINARIA:
        horas = (plazo.datos or {}).get("cantidad_extraordinaria_horas")
        dias = (plazo.datos or {}).get("cantidad_extraordinaria_dias")  # PEG: un día (9.4.2, línea 8942)
        if horas is None and dias is None:
            return None, None
        if horas is not None:
            return f"{horas} horas ({plazo.fundamento})", sesion.fecha_hora - timedelta(hours=horas)
        cantidad, texto_plazo = dias, f"{dias} día{'s' if dias != 1 else ''} hábil{'es' if dias != 1 else ''}"
    # N días hábiles de anticipación: entre el día del envío y el de la sesión debe haber N días hábiles.
    fecha_sesion = timezone.localtime(sesion.fecha_hora).date()
    limite = fecha_sesion
    contados = 0
    while contados < cantidad:
        limite -= timedelta(days=1)
        if dias_habiles.es_habil(limite):
            contados += 1
    fin_del_dia = timezone.make_aware(datetime.combine(limite, time(23, 59, 59)))
    return f"{texto_plazo} de anticipación ({plazo.fundamento})", fin_del_dia


def enviar_convocatoria(usuario, sesion, momento=None):
    """Envía la convocatoria con orden del día y documentos; queda la fecha y hora del envío y su acuse.

    `momento` (solo servicios, pruebas y demostración; la interfaz no lo pasa) es la fecha de envío; por omisión, ahora."""
    exigir_unidad(usuario, TipoUnidad.SECRETARIA_COMITE)
    if sesion.convocatoria_enviada:
        raise ValidationError("La convocatoria ya se envió.")
    if not sesion.puntos:
        raise ValidationError("La convocatoria debe llevar el orden del día.")
    if not sesion.documentos.exists():
        raise ValidationError("Adjunte los documentos de la sesión antes de convocar.")
    ahora = momento or timezone.now()
    texto, limite = anticipacion_requerida(sesion)
    if limite is not None and ahora > limite:
        raise ValidationError(f"La convocatoria debe enviarse con {texto}: a más tardar el "
                              f"{timezone.localtime(limite):%d/%m/%Y}. Cambie la fecha de la sesión o convoque a una extraordinaria.")
    integrantes = sesion.integrantes or {}
    destinatarios = [integrantes.get("presidencia", "")] + list(integrantes.get("vocales", [])) + list(integrantes.get("invitados", []))
    with transaction.atomic():
        acuse = emitir_acuse(
            None, "convocatoria_comite", f"Convocatoria a la {sesion.get_tipo_display().lower()} {sesion.numero}", usuario,
            [("Comité", integrantes.get("nombre", "")), ("Carácter", sesion.get_caracter_display()),
             ("Fecha y hora de la sesión", f"{timezone.localtime(sesion.fecha_hora):%d/%m/%Y %H:%M} h"),
             ("Lugar", sesion.lugar), ("Fecha y hora del envío", f"{timezone.localtime(ahora):%d/%m/%Y %H:%M:%S} h"),
             ("Anticipación requerida", texto or "Sin plazo en las reglas"),
             ("Documentos", ", ".join(d.nombre for d in sesion.documentos.all()))],
            destinatario="Integrantes del Comité", referencia=f"Sesión {sesion.numero}",
            detalle=[{"clave": str(i), "texto": p, "estado": ""} for i, p in enumerate(sesion.puntos, 1)]
            + [{"clave": "Conv.", "texto": d, "estado": ""} for d in destinatarios if d],
            encabezado_detalle=["Punto", "Orden del día e integrantes convocados", ""],
        )
        sesion.convocatoria_enviada = ahora
        sesion.acuse_convocatoria = acuse
        sesion.estado = EstadoSesion.CONVOCADA
        sesion.save(update_fields=["convocatoria_enviada", "acuse_convocatoria", "estado"])
    return acuse
