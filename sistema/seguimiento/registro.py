"""Registro del módulo M6 (Seguimiento y cierre) en los puntos de extensión del núcleo.

Pestaña «Seguimiento» del expediente, menú «Seguimiento y cierre», paneles de bandeja (recurso liberado por reasignar,
solicitudes por proponer y propuestas por llevar a sesión), siguiente paso, la sección del portal para desistimiento y
sustitución, los receptores de los acuerdos del Comité (``dictamen.seguimiento.RECEPTORES``), el recurso liberado de un
contrato sin firma (``extensiones.AL_LIBERAR_RECURSO``), la notificación de las reasignadas (``AL_NOTIFICAR``) y los datos de
demostración, igual que ``contrato/registro.py`` y ``pagos/registro.py``.
"""
from django.urls import reverse

from nucleo import extensiones, montos, plazos
from nucleo.models import TipoUnidad
from nucleo.templatetags.moneda import formato_moneda

HISTORIAS = [
    ("HU-6.1", "Lista de espera y sustituciones", "propone la reasignación del recurso liberado en el orden de la lista de espera y registra sustituciones y desistimientos con su acuse"),
    ("HU-6.2", "Incumplimientos y reintegros", "registra cada omisión con su plazo, el caso fortuito, la cancelación, el requerimiento de devolución con monto y cuenta, el reintegro y el Listado de Incumplidas"),
    ("HU-6.3", "Cierre del ejercicio", "cuadra los resultados finales con las verificaciones y los pagos, publica el padrón y registra el envío del informe al Comité"),
]
HISTORIAS_CONSTRUIDAS = {"HU-6.1", "HU-6.2"}
USOS_DE_PLAZO = ['aviso_caso_fortuito', 'interes_segunda_beneficiaria', 'subsanar_omisiones']
TIPOS_ACUERDO_M6 = ("reasignacion", "sustitucion", "liberacion_recurso", "caso_fortuito", "caso_especial", "cancelacion",
                    "suspension", "baja")


def historias_pendientes():
    return [h for h in HISTORIAS if h[0] not in HISTORIAS_CONSTRUIDAS]


def contexto_pestana(request, exp):
    """Cada historia suma aquí lo suyo a la pestaña."""
    from .vistas.reasignacion import contexto_reasignacion_exp

    contexto = {"historias": historias_pendientes(), "monto": montos.monto_si_aprobado(exp),
                "vencimientos": [v for v in plazos.vencimientos(exp, USOS_DE_PLAZO).values() if v is not None]}
    contexto.update(contexto_reasignacion_exp(request, exp))
    from .vistas.incumplimientos import contexto_incumplimientos_exp

    contexto.update(contexto_incumplimientos_exp(request, exp))
    return contexto


def _pestana(exp):
    return reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=seguimiento"


def siguiente_paso(usuario, exp):
    """Siguiente paso de M6 en el expediente."""
    from . import incumplimientos, reasignacion

    estado = exp.estado.clave
    abierto = incumplimientos.senalamientos_de(usuario).filter(expediente=exp).first() if usuario.tipo_unidad in (
        TipoUnidad.DIRECCION, TipoUnidad.DELEGACION) else None
    if abierto is not None:
        return {"texto": abierto.config.get("accion", "Atender el señalamiento"), "url": _pestana(exp),
                "ayuda": f"{abierto.descripcion} Lo preparó el sistema; lo confirma usted."}
    if usuario.tipo_unidad == TipoUnidad.JURIDICA and estado == "cancelada" and incumplimientos.por_emitir().filter(expediente=exp).exists():
        return {"texto": "Emitir el requerimiento de devolución", "url": _pestana(exp),
                "ayuda": "Con el monto y la cuenta para el depósito que registró Administración y Finanzas."}
    if usuario.tipo_unidad == TipoUnidad.ADMIN_FINANZAS and estado == "en_devolucion":
        return {"texto": "Comprobar el depósito del reintegro", "url": _pestana(exp), "ayuda": "Fecha, importe, referencia y comprobante."}
    if usuario.tipo_unidad == TipoUnidad.DIRECCION and estado in ("sustitucion", "caso_fortuito", "prorroga_solicitada",
                                                                  "verificada"):
        if not usuario.unidad.programas.filter(pk=exp.programa.pk).exists():
            return None
        if estado == "prorroga_solicitada" and exp.prorrogas.filter(autorizada__isnull=True).exists():
            return {"texto": "Resolver la prórroga por causa externa", "url": _pestana(exp),
                    "ayuda": "Autorizada con adendum (plazo nuevo) o negada, con su motivo."}
        tipos = [t for t in reasignacion.tipos_propuesta(exp) if t[0] not in incumplimientos.TIPOS_HU_6_2]
        if tipos and reasignacion.propuesta_abierta(exp) is None:
            return {"texto": f"Proponer al Comité: {tipos[0][1].lower()}", "url": _pestana(exp),
                    "ayuda": "La Secretaría Técnica la lleva a la sesión de seguimiento; el acuerdo se ejecuta al cumplirlo."}
    return None


def _panel(clave, titulo, total, filas, enlace, ayuda, accion):
    return {"plantilla": "pagos/_panel.html", "contexto": {"clave": clave, "titulo": titulo, "total": total, "filas": filas,
                                                            "enlace": enlace, "ayuda": ayuda, "accion": accion}}


def panel_recurso_liberado(request):
    """Dirección: recurso liberado por reasignar con solicitudes en lista de espera a las que alcanza."""
    from . import reasignacion

    if request.user.tipo_unidad != TipoUnidad.DIRECCION:
        return None
    filas = [f for f in reasignacion.ejercicios_con_lista(request.user) if f["total"] and f["alcanzadas"]]
    if not filas:
        return None
    return _panel("panel-recurso-liberado", "Recurso liberado por reasignar a la lista de espera", len(filas),
                  [{"url": reverse("seguimiento:pagina"), "texto": f"{f['ejercicio'].programa.nombre} {f['ejercicio'].anio}",
                    "detalle": f"{formato_moneda(f['total'])} liberados · alcanza para {len(f['alcanzadas'])} de "
                               f"{len(f['renglones'])} en lista de espera"} for f in filas],
                  reverse("seguimiento:pagina"), "Arme la propuesta en el orden de la lista de espera y envíela al Comité.",
                  "Ver la lista de espera")


def panel_solicitudes(request):
    """Dirección: solicitudes de sustitución, desistimiento o aviso de fallecimiento sin propuesta al Comité."""
    from . import reasignacion

    pendientes = list(reasignacion.solicitudes_por_proponer(request.user)[:50])
    if not pendientes:
        return None
    return _panel("panel-solicitudes-por-proponer", "Sustituciones y desistimientos por proponer al Comité", len(pendientes),
                  [{"url": _pestana(s.expediente), "texto": s.expediente.folio,
                    "detalle": f"{s.nombre} · {s.presentada_en:%d/%m/%Y %H:%M} h"} for s in pendientes[:6]],
                  reverse("seguimiento:pagina"), "Cada una ya tiene su acuse con la fecha y la hora; analícela y propóngala al Comité.",
                  "Abrir el seguimiento")


def panel_propuestas(request):
    """Secretaría Técnica: propuestas del área responsable por llevar a una sesión de seguimiento."""
    from . import reasignacion

    if request.user.tipo_unidad != TipoUnidad.SECRETARIA_COMITE:
        return None
    pendientes = list(reasignacion.propuestas_por_llevar()[:50])
    if not pendientes:
        return None
    return _panel("panel-propuestas-por-llevar", "Propuestas del área responsable por llevar a sesión", len(pendientes),
                  [{"url": reverse("seguimiento:pagina"), "texto": f"{p.nombre_tipo} · {p.ejercicio.programa.nombre}",
                    "detalle": f"{p.creada_en:%d/%m/%Y %H:%M} h · {p.acuse.folio if p.acuse_id else ''}"} for p in pendientes[:6]],
                  reverse("seguimiento:pagina"), "Regístrelas como acuerdo en una sesión de seguimiento convocada.",
                  "Ver las propuestas")


def panel_senalamientos(request):
    """Área responsable y Delegación: lo que el sistema preparó para confirmar (P-08)."""
    from . import incumplimientos

    pendientes = list(incumplimientos.senalamientos_de(request.user)[:50])
    if not pendientes:
        return None
    return _panel("panel-senalamientos", "Incumplimientos por atender (preparados por el sistema)", len(pendientes),
                  [{"url": _pestana(s.expediente), "texto": s.expediente.folio,
                    "detalle": f"{s.config.get('nombre', s.tipo)} · {s.config.get('accion', '')}"} for s in pendientes[:6]],
                  reverse("seguimiento:incumplimientos"), "El sistema los señaló al vencer el plazo o al recibir la evaluación; "
                  "nada se ejecuta solo: confírmelos.", "Ver los incumplimientos")


def panel_requerimientos(request):
    """Unidad Jurídica: requerimientos por emitir. Administración y Finanzas: depósitos por comprobar."""
    from . import incumplimientos

    tipo = request.user.tipo_unidad
    if tipo == TipoUnidad.JURIDICA:
        qs, titulo, ayuda = incumplimientos.por_emitir(), "Requerimientos de devolución por emitir",             "Apoyos cancelados: emita el requerimiento con el monto y la cuenta para el depósito."
    elif tipo == TipoUnidad.ADMIN_FINANZAS:
        qs, titulo, ayuda = incumplimientos.por_comprobar(), "Reintegros por comprobar",             "Requerimientos notificados: registre el depósito con su comprobante."
    else:
        return None
    pendientes = list(qs.select_related("expediente")[:50])
    if not pendientes:
        return None
    return _panel("panel-requerimientos", titulo, len(pendientes),
                  [{"url": _pestana(r.expediente), "texto": r.expediente.folio,
                    "detalle": f"{formato_moneda(r.monto_total)} · {r.motivo}"} for r in pendientes[:6]],
                  reverse("seguimiento:incumplimientos"), ayuda, "Abrir incumplimientos y reintegros")


def registrar():
    if contexto_pestana in [p["contexto"] for p in extensiones.PESTANAS_EXPEDIENTE]:
        return
    extensiones.PESTANAS_EXPEDIENTE.append({"clave": "seguimiento", "nombre": "Seguimiento",
                                            "plantilla": "seguimiento/pestana_seguimiento.html", "contexto": contexto_pestana})
    from dictamen import seguimiento as dictamen_seguimiento

    from . import reasignacion
    from .vistas.portal import seccion_portal

    T = TipoUnidad
    extensiones.MENU.append({"nombre": "Seguimiento", "url": "seguimiento:pagina",
                             "grupo": "Seguimiento y cierre", "tipos": [T.DIRECCION, T.SECRETARIA_COMITE, T.JURIDICA],
                             "estricto": True})
    extensiones.SIGUIENTES_PASOS.append(siguiente_paso)
    extensiones.PANELES_BANDEJA.append(panel_recurso_liberado)
    extensiones.PANELES_BANDEJA.append(panel_solicitudes)
    extensiones.PANELES_BANDEJA.append(panel_propuestas)
    extensiones.PANELES_BANDEJA.append(panel_senalamientos)
    extensiones.PANELES_BANDEJA.append(panel_requerimientos)
    from . import incumplimientos

    extensiones.MENU.append({"nombre": "Incumplimientos y reintegros", "url": "seguimiento:incumplimientos",
                             "grupo": "Seguimiento y cierre", "tipos": [T.JURIDICA, T.ADMIN_FINANZAS], "estricto": True})
    extensiones.AL_INCIDENCIA.append(incumplimientos.al_incidencia)
    extensiones.AL_REPORTE_INCUMPLIDO.append(incumplimientos.al_reporte_incumplido)
    extensiones.REVISIONES_PLAZO.append(incumplimientos.revisar)
    reasignacion.EJECUTORES.update({"cancelacion": incumplimientos._ejecutar_cancelacion,
                                    "baja_cheque": incumplimientos._ejecutar_cancelacion,
                                    "baja_reportes": incumplimientos._ejecutar_cancelacion,
                                    "suspension": incumplimientos._ejecutar_suspension,
                                    "levantar_suspension": incumplimientos._ejecutar_suspension})
    extensiones.AL_LIBERAR_RECURSO.append(reasignacion.al_liberar_recurso)
    extensiones.AL_NOTIFICAR.append(reasignacion.al_notificar)
    extensiones.SECCIONES_PORTAL.append(seccion_portal)
    for tipo in TIPOS_ACUERDO_M6:
        dictamen_seguimiento.RECEPTORES.setdefault(tipo, []).append(reasignacion.ejecutar_acuerdo)
    extensiones.DEMOS.append(cargar_demo)


def cargar_demo():
    from .demo import cargar_demo as cargar

    return cargar()
