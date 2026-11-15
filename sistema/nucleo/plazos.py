"""Plazos con evento de arranque (R-03 y R-12): un solo servicio para todo el sistema.

Un **uso** es para qué quiere el sistema una fecha («faltantes_ventanilla», «firma_programada»…). En
``datos/sistema.json`` (``usos_de_plazo``) cada uso se resuelve **por programa** (``por_omision`` más lo
que cambie el programa) a:

- ``plazo``: clave del plazo en las reglas del ejercicio (``reglas/<CLAVE>.json``);
- ``evento``: qué lo arranca (``recepcion_solicitud``, ``aviso_direccion``, ``notificacion_persona``,
  ``publicacion_resultados``, ``entrega_vale``, ``entrega_cheque``, ``firma_contrato``…);
- opcionales: ``tipo_notificacion`` (para ``notificacion_persona``), ``tope`` (``{"plazo": clave}`` toma
  su ``fecha_fin``; ``{"fecha": "AAAA-MM-DD"}``; ``{"dato": campo, "solo_reasignadas": true}`` toma un
  campo extra del plazo), ``evento_reasignada`` (otro evento para las personas reasignadas desde la lista
  de espera), ``unidad`` (cuando las reglas no dicen si los días son hábiles), ``decision_propia`` y
  ``nota``.

Los eventos se leen así: ``recepcion_solicitud`` del expediente; ``aviso_direccion`` y
``notificacion_persona`` de ``nucleo.Notificacion``; cualquier otro, del último ``Hito`` con esa clave
(lo registra el módulo que lo produce con ``registrar_hito``) o de una función de
``extensiones.EVENTOS_PLAZO``. Si el evento no ha ocurrido, el vencimiento es «sin fecha todavía».
"""
from dataclasses import dataclass, field
from datetime import date, datetime

from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from . import dias_habiles, extensiones
from .catalogos import datos_sistema
from .models import Hito

SIN_FECHA = "sin fecha todavía"

NOMBRES_EVENTO = {
    "recepcion_solicitud": "la recepción de la solicitud",
    "aviso_direccion": "el aviso de faltantes de la Dirección",
    "notificacion_persona": "la notificación a la persona",
    "publicacion_resultados": "la publicación de resultados",
    "firma_contrato": "la firma del contrato",
    "entrega_vale": "la entrega del Vale de Salida de Planta",
    "entrega_cheque": "la entrega del cheque",
    "solicitud_pago_fiduciaria": "la solicitud de pago del área a la Secretaría Técnica",
    "conclusion_actividades": "la conclusión de las actividades",
}


@dataclass
class Vencimiento:
    uso: str
    plazo: object  # nucleo.Plazo o None
    evento: str
    fecha_evento: datetime | date | None = None
    vencimiento: date | None = None
    tope: date | None = None
    topado: bool = False
    evento_despues_del_tope: bool = False
    decision_propia: bool = False
    nota: str = ""
    config: dict = field(default_factory=dict)

    @property
    def tiene_fecha(self):
        return self.vencimiento is not None

    @property
    def nombre_evento(self):
        return NOMBRES_EVENTO.get(self.evento, self.evento.replace("_", " "))

    @property
    def texto_plazo(self):
        if self.plazo is None:
            return "—"
        if self.config.get("unidad") and self.plazo.cantidad is not None:
            from .models import UnidadPlazo
            return f"{self.plazo.cantidad} {dict(UnidadPlazo.choices).get(self.config['unidad'], self.config['unidad'])}"
        return self.plazo.texto_plazo

    @property
    def fundamento(self):
        return self.plazo.fundamento if self.plazo else ""

    @property
    def texto(self):
        """Frase para pantallas y acuses."""
        if not self.tiene_fecha:
            return f"{SIN_FECHA} (corre desde {self.nombre_evento})"
        texto = f"{self.vencimiento:%d/%m/%Y} ({self.texto_plazo} desde {self.nombre_evento}"
        if self.topado:
            texto += f", sin pasar del {self.tope:%d/%m/%Y}"
        return texto + ")"

    def estado(self, hoy=None):
        """«sin fecha todavía», «en plazo», «por vencer» (5 días hábiles o menos) o «vencido»."""
        if not self.tiene_fecha:
            return SIN_FECHA
        hoy = hoy or timezone.localdate()
        if hoy > self.vencimiento:
            return "vencido"
        return "por vencer" if dias_habiles.dias_habiles_entre(hoy, self.vencimiento) <= 5 else "en plazo"


# ----------------------------------------------------------------------------- configuración
def config_uso(programa_clave, uso, sistema=None):
    """Configuración del uso para el programa: ``por_omision`` con lo que cambie el programa encima."""
    usos = (sistema or datos_sistema()).get("usos_de_plazo", {})
    base = dict(usos.get("por_omision", {}).get(uso, {}))
    propio = usos.get(programa_clave, {}).get(uso)
    if propio is None and not base:
        conocidos = {u for k, v in usos.items() if isinstance(v, dict) for u in v}
        if uso not in conocidos:
            raise ImproperlyConfigured(f"El uso de plazo «{uso}» no está en datos/sistema.json (usos_de_plazo).")
        return None  # es de otro programa
    if propio is False:  # el programa no tiene ese plazo
        return None
    base.update(propio or {})
    return base


def usos_configurados(programa_clave, sistema=None):
    usos = (sistema or datos_sistema()).get("usos_de_plazo", {})
    claves = set(usos.get("por_omision", {})) | {k for k, v in usos.get(programa_clave, {}).items() if v is not False}
    return sorted(c for c in claves if config_uso(programa_clave, c, sistema) is not None)


# ----------------------------------------------------------------------------- eventos
def registrar_hito(expediente, clave, usuario=None, fecha_hora=None, referencia="", datos=None):
    """Registra un evento fechado del trámite (publicación, firma, entrega del Vale o del cheque…)."""
    return Hito.objects.create(expediente=expediente, clave=clave, fecha_hora=fecha_hora or timezone.now(),
                               usuario=usuario, referencia=referencia[:120], datos=datos or {})


def _ultima_notificacion(expediente, tipo, notificada=True):
    qs = expediente.notificaciones.filter(tipo=tipo)
    if notificada:
        qs = qs.filter(notificada_en__isnull=False).order_by("-notificada_en", "-id")
    else:
        qs = qs.order_by("-enviada_en", "-id")
    return qs.first()


def fecha_de_evento(expediente, evento, config=None):
    """Fecha y hora en que ocurrió el evento para el expediente, o None si aún no ocurre."""
    config = config or {}
    if evento in extensiones.EVENTOS_PLAZO:
        return extensiones.EVENTOS_PLAZO[evento](expediente, config)
    if evento == "recepcion_solicitud":
        return expediente.fecha_recepcion
    if evento == "aviso_direccion":
        n = _ultima_notificacion(expediente, "faltantes", notificada=False)
        return n.enviada_en if n else None
    if evento == "notificacion_persona":
        n = _ultima_notificacion(expediente, config.get("tipo_notificacion", "resultados"))
        return n.notificada_en if n else None
    hito = expediente.hitos.filter(clave=evento).order_by("-fecha_hora", "-id").first()
    return hito.fecha_hora if hito else None


def es_reasignada(expediente):
    """Aprobada por reasignación desde la lista de espera (flujo alterno C)."""
    return expediente.eventos.filter(estado_origen__clave="lista_espera", estado_destino__clave="aprobada").exists()


def _fecha_tope(expediente, plazo, tope):
    if not tope:
        return None
    if tope.get("solo_reasignadas") and not es_reasignada(expediente):
        return None
    if "fecha" in tope:
        return date.fromisoformat(tope["fecha"])
    if "plazo" in tope:
        otro = expediente.ejercicio.plazo(tope["plazo"])
        return otro.fecha_fin if otro else None
    if "dato" in tope and plazo is not None:
        valor = plazo.datos.get(tope["dato"])
        return date.fromisoformat(valor) if valor else None
    return None


# ----------------------------------------------------------------------------- servicio
def vencimiento(expediente, uso, fecha_evento=None):
    """Vencimiento del plazo ``uso`` para el expediente (``Vencimiento``; None si el programa no lo tiene).

    ``fecha_evento`` sustituye la fecha del evento (por ejemplo, para mostrar «si se emite hoy»).
    """
    config = config_uso(expediente.programa.clave, uso)
    if config is None:
        return None
    plazo = expediente.ejercicio.plazo(config["plazo"]) if config.get("plazo") else None
    evento = config.get("evento", "")
    if config.get("evento_reasignada") and es_reasignada(expediente):
        evento = config["evento_reasignada"]
    res = Vencimiento(uso=uso, plazo=plazo, evento=evento, decision_propia=bool(config.get("decision_propia")),
                      nota=config.get("nota", ""), config=config)
    res.fecha_evento = fecha_evento or fecha_de_evento(expediente, evento, config)
    res.tope = _fecha_tope(expediente, plazo, config.get("tope"))
    if res.fecha_evento is None:
        return res
    if plazo is not None and plazo.cantidad is not None:
        unidad = config.get("unidad") or plazo.unidad
        if unidad not in dias_habiles.UNIDADES_CALCULABLES:
            return res
        res.vencimiento = dias_habiles.calcular_vencimiento(res.fecha_evento, plazo.cantidad, unidad)
    elif plazo is not None and plazo.fecha_fin:
        res.vencimiento = plazo.fecha_fin
    else:
        return res
    if res.tope:
        inicio = dias_habiles._como_fecha(res.fecha_evento)
        if inicio > res.tope:
            # El evento ocurrió después de la fecha límite (fuera del calendario de la Convocatoria):
            # no se puede topar; se señala para que la unidad lo revise.
            res.evento_despues_del_tope = True
        elif res.vencimiento > res.tope:
            res.vencimiento, res.topado = res.tope, True
    return res


def vencimientos(expediente):
    """Todos los usos configurados para el programa del expediente, con su vencimiento."""
    return {u: vencimiento(expediente, u) for u in usos_configurados(expediente.programa.clave)}
