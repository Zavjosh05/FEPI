"""Registro del módulo M3 (Publicación y contrato) en los puntos de extensión del núcleo.

Cada historia agrega aquí lo suyo (filtros y paneles de bandeja, menú, revisión de plazos, siguiente paso,
receptores de notificación y datos de demostración), igual que ``dictamen/registro.py``.
"""
from nucleo import extensiones
from nucleo.models import TipoUnidad

# Historias de la pestaña «Contrato» que todavía no se construyen (la plantilla dice cuál las llenará).
HISTORIAS = [
    ("HU-3.1", "Publicación y notificaciones", "publica los listados y envía los avisos por conducto de la Delegación"),
    ("HU-3.2", "Elaboración del contrato", "elabora el contrato sobre el modelo validado por la Unidad Jurídica"),
    ("HU-3.3", "Firma del contrato", "cita a la persona, recaba su firma y señala lo que no se firmó en plazo"),
    ("HU-3.4", "Entrega de planta", "valida el Vale de Planta y registra la salida por especie y cantidad"),
]
HISTORIAS_CONSTRUIDAS = {"HU-3.1", "HU-3.2", "HU-3.3"}
USOS_DE_PLAZO = ["cita_firma", "firma_programada", "firma_liberacion", "ptrfi_actualizado", "recoger_planta"]


def historias_pendientes():
    return [h for h in HISTORIAS if h[0] not in HISTORIAS_CONSTRUIDAS]


def contexto_pestana(request, exp):
    from .vistas.comun import contexto_contrato

    return contexto_contrato(request, exp)


def siguiente_paso(usuario, exp):
    """Siguiente paso de M3 en el expediente (P-13 y P-17)."""
    from django.urls import reverse

    from . import publicacion

    estado, tipo = exp.estado.clave, usuario.tipo_unidad
    if estado == "aprobada" and tipo == TipoUnidad.DIRECCION:
        sesion = publicacion.sesion_de_expediente(exp)
        if sesion is not None:
            return {"texto": "Publicar los resultados", "url": reverse("contrato:publicacion", args=[sesion.pk]),
                    "ayuda": f"Sesión {sesion.numero}: el acta autoriza la publicación." if sesion.autoriza_publicacion
                    else f"Sesión {sesion.numero}: el acta no autorizó la publicación."}
        return {"texto": "Ver lo que sigue: publicación y contrato",
                "url": reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=contrato"}
    if estado == "notificada" and tipo == TipoUnidad.DIRECCION:
        return {"texto": "Elaborar el contrato", "url": reverse("contrato:elaborar", args=[exp.folio]),
                "ayuda": "Sobre un modelo validado por la Unidad Jurídica."}
    if estado == "contrato_elaborado" and tipo == TipoUnidad.DIRECCION:
        return {"texto": "Revisar y enviar el contrato a la Delegación",
                "url": reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=contrato"}
    if estado == "contrato_en_delegacion" and tipo == TipoUnidad.DELEGACION:
        return {"texto": "Registrar la firma del contrato", "url": reverse("contrato:firmar", args=[exp.folio]),
                "ayuda": "Verifique las firmas y el sello y suba el contrato firmado."}
    if estado == "sin_firma_en_plazo" and tipo == TipoUnidad.DIRECCION:
        return {"texto": "Confirmar la liberación del recurso",
                "url": reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=contrato",
                "ayuda": "Venció el plazo de firma: la liberación la confirma el área responsable con un motivo."}
    if estado == "publicada" and tipo == TipoUnidad.DELEGACION:
        return {"texto": "Notificar a la persona beneficiaria", "url": reverse("contrato:notificaciones"),
                "ayuda": "Registre la fecha, la hora y el medio de la notificación."}
    return None


def panel_por_publicar(request):
    from . import publicacion

    if request.user.tipo_unidad != TipoUnidad.DIRECCION:
        return None
    sesiones = list(publicacion.sesiones_por_publicar(request.user))
    if not sesiones:
        return None
    return {"plantilla": "contrato/publicacion/_panel_publicar.html", "contexto": {"sesiones": sesiones}}


def panel_por_notificar(request):
    from . import publicacion

    if request.user.tipo_unidad != TipoUnidad.DELEGACION:
        return None
    pendientes = publicacion.por_entregar(request.user)
    total = pendientes.count()
    if not total:
        return None
    return {"plantilla": "contrato/publicacion/_panel_notificar.html",
            "contexto": {"total": total, "notificaciones": list(pendientes.order_by("enviada_en")[:6])}}


def panel_por_firmar(request):
    from . import firma
    from .vistas.firma import _fila

    if request.user.tipo_unidad != TipoUnidad.DELEGACION:
        return None
    qs = firma.por_firmar(request.user)
    total = qs.count()
    if not total:
        return None
    filas = [_fila(e) for e in qs.order_by("fecha_recepcion")[:6]]
    return {"plantilla": "contrato/firma/_panel_por_firmar.html", "contexto": {"total": total, "filas": filas}}


def panel_sin_firma(request):
    from . import firma

    if request.user.tipo_unidad != TipoUnidad.DIRECCION:
        return None
    senalados = firma.sin_firma(request.user)
    total = senalados.count()
    if not total:
        return None
    return {"plantilla": "contrato/firma/_panel_sin_firma.html",
            "contexto": {"total": total, "senalados": list(senalados[:6])}}


def panel_modelos_por_validar(request):
    from . import contratos

    if request.user.tipo_unidad != TipoUnidad.JURIDICA:
        return None
    modelos = contratos.modelos_por_validar()
    if not modelos:
        return None
    return {"plantilla": "contrato/contratos/_panel_validar.html", "contexto": {"modelos": modelos}}


def registrar():
    if contexto_pestana in [p["contexto"] for p in extensiones.PESTANAS_EXPEDIENTE]:
        return
    from . import firma, publicacion

    extensiones.PESTANAS_EXPEDIENTE.append({"clave": "contrato", "nombre": "Contrato",
                                            "plantilla": "contrato/pestana_contrato.html", "contexto": contexto_pestana})
    extensiones.SIGUIENTES_PASOS.append(siguiente_paso)
    extensiones.PANELES_BANDEJA.extend([panel_por_publicar, panel_por_notificar, panel_modelos_por_validar,
                                        panel_por_firmar, panel_sin_firma])
    extensiones.REVISIONES_PLAZO.append(firma.revisar_firmas)
    extensiones.AL_NOTIFICAR.append(publicacion.al_notificar)
    T = TipoUnidad
    extensiones.MENU.extend([
        {"nombre": "Publicación", "url": "contrato:publicaciones",
         "tipos": [T.DIRECCION, T.SECRETARIA_COMITE, T.JURIDICA]},
        {"nombre": "Notificaciones", "url": "contrato:notificaciones", "tipos": [T.DELEGACION, T.DIRECCION]},
        {"nombre": "Modelos", "url": "contrato:modelos", "tipos": [T.DIRECCION, T.JURIDICA]},
        {"nombre": "Contratos", "url": "contrato:contratos", "tipos": [T.DIRECCION, T.JURIDICA]},
        {"nombre": "Firmas", "url": "contrato:firmas", "tipos": [T.DELEGACION, T.DIRECCION]},
    ])
    extensiones.DEMOS.append(cargar_demo)


def cargar_demo():
    from .demo import cargar_demo as cargar

    return cargar()
