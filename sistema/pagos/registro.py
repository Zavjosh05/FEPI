"""Registro del módulo M5 (Pagos) en los puntos de extensión del núcleo.

Cada historia agrega aquí lo suyo (filtros y paneles de bandeja de Delegación, área responsable, Administración y Finanzas y
Fiduciaria, menú, revisión de plazos, siguiente paso, receptores de acuerdos del Comité), igual que ``contrato/registro.py``.
"""
from django.db.models import Q
from django.urls import reverse

from nucleo import extensiones
from nucleo.models import TipoUnidad

HISTORIAS = [
    ("HU-5.1", "Solicitud de pago", "solicita cada ministración con el contrato, el oficio y la verificación"),
    ("HU-5.2", "Pago de la ministración", "Administración y Finanzas paga o, en PSAHEM, remite a la Fiduciaria"),
    ("HU-5.3", "Entrega de cheques", "la Fiduciaria emite y envía los cheques; la Delegación los entrega (PSAHEM)"),
]
HISTORIAS_CONSTRUIDAS = {"HU-5.1", "HU-5.2", "HU-5.3"}
USOS_DE_PLAZO = ["instruccion_pago_fiduciaria", "cobro_cheque"]


def historias_pendientes():
    return [h for h in HISTORIAS if h[0] not in HISTORIAS_CONSTRUIDAS]


def contexto_pestana(request, exp):
    from .vistas.comun import contexto_pagos

    return contexto_pagos(request, exp)


def _pestana(exp):
    return reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=pagos"


def siguiente_paso(usuario, exp):
    """Siguiente paso de M5 en el expediente."""
    from . import pagos, solicitudes

    estado, tipo = exp.estado.clave, usuario.tipo_unidad
    firmado = getattr(exp, "firma_contrato", None) is not None
    if estado == "ministracion_solicitada":
        sol = exp.solicitudes_pago.exclude(estado__in=("borrador", "devuelta", "pagada")).order_by("-ministracion").first()
        if sol is not None and tipo == TipoUnidad.ADMIN_FINANZAS and sol.estado == "enviada":
            return {"texto": f"Revisar la solicitud de pago de la ministración {sol.ministracion}", "url": _pestana(exp),
                    "ayuda": "Acéptela si sus soportes están completos o devuélvala con observaciones."}
        if sol is not None and tipo == TipoUnidad.ADMIN_FINANZAS and sol.estado == "aceptada" and not pagos.es_fiduciaria(exp):
            return {"texto": f"Registrar el pago de la ministración {sol.ministracion}", "url": _pestana(exp),
                    "ayuda": "Referencia, fecha del pago e importe igual al solicitado."}
        if sol is not None and tipo == TipoUnidad.SECRETARIA_COMITE and sol.estado == "aceptada" and pagos.es_fiduciaria(exp):
            return {"texto": "Solicitar el pago a la Fiduciaria", "url": _pestana(exp),
                    "ayuda": "En un máximo de 5 días hábiles desde que recibió la solicitud del área (ROP PSAHEM 10.1 fr. X)."}
    if tipo == TipoUnidad.FIDUCIARIA and estado == "remitida_fiduciaria":
        return {"texto": "Emitir el cheque", "url": _pestana(exp),
                "ayuda": "Número de cheque, importe igual al solicitado y fecha de emisión."}
    if tipo == TipoUnidad.FIDUCIARIA and estado == "cheque_emitido":
        return {"texto": "Enviar el cheque a la Delegación", "url": _pestana(exp),
                "ayuda": "Queda la fecha y la hora del envío y el aviso a la persona por la Delegación."}
    if tipo == TipoUnidad.DELEGACION and estado == "cheque_enviado":
        return {"texto": "Registrar la entrega del cheque", "url": _pestana(exp),
                "ayuda": "Quién recibe, fecha y hora; desde la entrega corren 3 meses para cobrarlo."}
    if estado == "pagada" and tipo == TipoUnidad.DELEGACION:
        aviso = exp.notificaciones.filter(tipo="pago", notificada_en__isnull=True, delegacion=usuario.unidad).first()
        if aviso is not None:
            return {"texto": "Notificar el pago a la persona beneficiaria", "url": reverse("contrato:notificaciones"),
                    "ayuda": "Registre la fecha, la hora y el medio de la notificación."}
    if tipo == TipoUnidad.DELEGACION and firmado and getattr(exp, "oficio_pago", None) is None and estado not in (
            "sin_firma_en_plazo", "recurso_liberado"):
        return {"texto": "Emitir el oficio de solicitud de pago", "url": _pestana(exp),
                "ayuda": "El contrato ya está firmado: el oficio de la Delegación es soporte de la solicitud de pago."}
    if tipo == TipoUnidad.DIRECCION and estado in solicitudes.ESTADOS_PARA_SOLICITAR:
        fila = solicitudes.siguiente_por_solicitar(exp)
        if fila is not None and fila["puede"]:
            devuelta = fila["solicitud"] is not None and fila["solicitud"].estado == "devuelta"
            return {"texto": (f"Corregir y reenviar la ministración {fila['numero']}" if devuelta
                              else f"Solicitar la ministración {fila['numero']}"), "url": _pestana(exp),
                    "ayuda": ("Falta " + ", ".join(s["nombre"].lower() for s in fila["faltan"]) + "."
                              if fila["faltan"] else "Soportes completos: se puede enviar a Administración y Finanzas.")}
    return None


def panel_oficios_por_emitir(request):
    from . import solicitudes

    if request.user.tipo_unidad != TipoUnidad.DELEGACION:
        return None
    pendientes = list(solicitudes.sin_oficio(request.user))
    if not pendientes:
        return None
    filas = [{"url": reverse("pagos:expediente", args=[e.folio]), "texto": e.folio,
              "detalle": f"{e.solicitante.nombre} · {e.predio.nombre}"} for e in pendientes[:6]]
    return {"plantilla": "pagos/_panel.html", "contexto": {
        "clave": "panel-oficios-por-emitir", "titulo": "Contratos firmados por emitir el oficio de solicitud de pago",
        "total": len(pendientes), "filas": filas, "enlace": reverse("pagos:solicitudes"),
        "accion": "Abrir las solicitudes de pago"}}


def panel_por_solicitar(request):
    from . import solicitudes

    if request.user.tipo_unidad != TipoUnidad.DIRECCION:
        return None
    pendientes = solicitudes.por_solicitar(request.user)
    if not pendientes:
        return None
    filas = [{"url": reverse("pagos:expediente", args=[f["exp"].folio]), "texto": f["exp"].folio,
              "detalle": f"{f['exp'].solicitante.nombre} · ministración {f['fila']['numero']}"
                         + (" (devuelta)" if f["fila"]["solicitud"] and f["fila"]["solicitud"].estado == "devuelta" else "")
                         + (" · faltan soportes" if f["fila"]["faltan"] else " · soportes completos")}
             for f in pendientes[:6]]
    return {"plantilla": "pagos/_panel.html", "contexto": {
        "clave": "panel-por-solicitar", "titulo": "Ministraciones por solicitar", "total": len(pendientes), "filas": filas,
        "enlace": reverse("pagos:solicitudes"), "accion": "Abrir las solicitudes de pago"}}


def panel_por_revisar(request):
    from . import pagos

    if request.user.tipo_unidad != TipoUnidad.ADMIN_FINANZAS:
        return None
    revisar, pagar = pagos.por_revisar(request.user), pagos.por_pagar(request.user)
    paneles = []
    for clave, titulo, lista, ayuda in (
            ("panel-por-revisar", "Solicitudes de pago por revisar", revisar,
             "Acéptelas si sus soportes están completos o devuélvalas al área responsable con observaciones."),
            ("panel-por-pagar", "Solicitudes aceptadas por pagar", pagar, "Registre la referencia, la fecha y el importe del pago.")):
        if lista:
            filas = [{"url": reverse("pagos:expediente", args=[s.expediente.folio]), "texto": s.folio,
                      "detalle": f"{s.expediente.solicitante.nombre} · ${s.importe:,.2f}"} for s in lista[:6]]
            paneles.append({"clave": clave, "titulo": titulo, "total": len(lista), "filas": filas, "ayuda": ayuda,
                            "enlace": reverse("pagos:pagos"), "accion": "Abrir el pago de ministraciones"})
    return {"plantilla": "pagos/_paneles.html", "contexto": {"paneles": paneles}} if paneles else None


def panel_por_remitir(request):
    from . import pagos

    if request.user.tipo_unidad != TipoUnidad.SECRETARIA_COMITE:
        return None
    pendientes = pagos.por_remitir(request.user)
    if not pendientes:
        return None
    from . import solicitudes

    filas = []
    for s in pendientes[:6]:
        v = solicitudes.plazo_remision(s)
        filas.append({"url": reverse("pagos:expediente", args=[s.expediente.folio]), "texto": s.folio,
                      "detalle": f"{s.expediente.solicitante.nombre} · plazo hasta {v.vencimiento:%d/%m/%Y}"
                                 + (f" ({v.estado()})" if v.estado() != "en plazo" else "")})
    return {"plantilla": "pagos/_panel.html", "contexto": {
        "clave": "panel-por-remitir", "titulo": "Pagos por solicitar a la Fiduciaria", "total": len(pendientes), "filas": filas,
        "ayuda": "Solicitudes aceptadas por Administración y Finanzas: 5 días hábiles desde que el área las envió.",
        "enlace": reverse("pagos:pagos"), "accion": "Abrir el pago de ministraciones"}}


def _panel_cheques(request, clave, titulo, filas_de, ayuda):
    lista = filas_de(request.user)
    if not lista:
        return None
    filas = []
    for x in lista[:6]:
        exp = x.expediente
        filas.append({"url": reverse("pagos:expediente", args=[exp.folio]), "texto": exp.folio,
                      "detalle": f"{exp.solicitante.nombre} · ministración {x.ministracion}"})
    return {"plantilla": "pagos/_panel.html", "contexto": {
        "clave": clave, "titulo": titulo, "total": len(lista), "filas": filas, "ayuda": ayuda,
        "enlace": reverse("pagos:cheques"), "accion": "Abrir los cheques"}}


def panel_cheques_por_emitir(request):
    from . import cheques

    return _panel_cheques(request, "panel-cheques-por-emitir", "Pagos remitidos por emitir su cheque", cheques.por_emitir,
                          "La Secretaría Técnica ya solicitó el pago a la Fiduciaria.")


def panel_cheques_por_enviar(request):
    from . import cheques

    return _panel_cheques(request, "panel-cheques-por-enviar", "Cheques por enviar a la Delegación", cheques.por_enviar,
                          "Quedan con fecha y hora de envío y su acuse.")


def panel_cheques_por_entregar(request):
    from . import cheques

    return _panel_cheques(request, "panel-cheques-por-entregar", "Cheques por entregar a las personas beneficiarias",
                          cheques.por_entregar, "Registre quién recibe y la fecha y hora de la entrega.")


def panel_cheques_por_vencer(request):
    from . import cheques

    if request.user.tipo_unidad not in (TipoUnidad.FIDUCIARIA, TipoUnidad.DELEGACION, TipoUnidad.DIRECCION):
        return None
    alertas = [f for f in cheques.por_cobrar(request.user) if f["estado"] in ("por vencer", "vencido")]
    if not alertas:
        return None
    filas = [{"url": reverse("pagos:expediente", args=[f["cheque"].expediente.folio]), "texto": f["cheque"].numero,
              "detalle": f"{f['cheque'].persona.nombre} · {f['estado']} ({f['vencimiento'].vencimiento:%d/%m/%Y})"}
             for f in alertas[:6]]
    return {"plantilla": "pagos/_panel.html", "contexto": {
        "clave": "panel-cheques-por-vencer", "titulo": "Cheques entregados por vencer o vencidos sin cobro",
        "total": len(alertas), "filas": filas, "ayuda": "Tienen 3 meses desde la entrega para cobrarse (solo aviso; la baja la registra HU-6.2, incumplimientos y reintegros).",
        "enlace": reverse("pagos:cheques"), "accion": "Abrir los cheques"}}


def filtro_admin_finanzas(usuario, qs):
    """En PSAHEM, una solicitud ya aceptada espera a la Secretaría Técnica: deja de estar por atender en Administración y Finanzas."""
    if usuario.tipo_unidad != TipoUnidad.ADMIN_FINANZAS:
        return qs
    return qs.exclude(Q(ejercicio__programa__clave="PSA", estado__clave="ministracion_solicitada",
                        solicitudes_pago__estado="aceptada"))


def extra_secretaria_comite(usuario):
    """P-26: en PSAHEM la solicitud aceptada que la Secretaría Técnica debe remitir a la Fiduciaria también está en su «por atender»."""
    if usuario.tipo_unidad != TipoUnidad.SECRETARIA_COMITE:
        return None
    from .models import SolicitudPago

    aceptadas = SolicitudPago.objects.filter(estado="aceptada").values("expediente_id")
    return Q(ejercicio__programa__clave="PSA", estado__clave="ministracion_solicitada", pk__in=aceptadas)


def registrar():
    if contexto_pestana in [p["contexto"] for p in extensiones.PESTANAS_EXPEDIENTE]:
        return
    extensiones.PESTANAS_EXPEDIENTE.append({"clave": "pagos", "nombre": "Pagos",
                                            "plantilla": "pagos/pestana_pagos.html", "contexto": contexto_pestana})
    extensiones.SIGUIENTES_PASOS.append(siguiente_paso)
    from . import cheques, pagos

    extensiones.PANELES_BANDEJA.extend([panel_oficios_por_emitir, panel_por_solicitar, panel_por_revisar, panel_por_remitir,
                                        panel_cheques_por_emitir, panel_cheques_por_enviar, panel_cheques_por_entregar,
                                        panel_cheques_por_vencer])
    extensiones.FILTROS_BANDEJA.append(filtro_admin_finanzas)
    extensiones.EXTRAS_BANDEJA.append(extra_secretaria_comite)
    extensiones.REVISIONES_PLAZO.extend([pagos.revisar_remisiones, cheques.revisar_cobros])
    T = TipoUnidad
    extensiones.MENU.extend([
        {"nombre": "Pagos", "url": "pagos:solicitudes", "grupo": "Pagos", "tipos": [T.DELEGACION, T.DIRECCION, T.JURIDICA]},
        {"nombre": "Pagos", "url": "pagos:pagos", "grupo": "Pagos", "tipos": [T.ADMIN_FINANZAS, T.SECRETARIA_COMITE]},
        {"nombre": "Cheques", "url": "pagos:cheques", "grupo": "Pagos", "tipos": [T.FIDUCIARIA, T.DELEGACION, T.ADMIN_FINANZAS]}])
    extensiones.DEMOS.append(cargar_demo)


def cargar_demo():
    from .demo import cargar_demo as cargar

    return cargar()
