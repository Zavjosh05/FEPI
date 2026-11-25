"""Monto aprobado de un expediente y sus ministraciones (S2-02d). Lo usan el Comité (HU-2.3), el contrato
(HU-3.2) y los pagos (HU-5.x): una sola regla para todo el sistema.

- Superficie: la que se pase o, si no, la superficie aprobada que dé un módulo
  (``extensiones.SUPERFICIE_APROBADA``: el dictamen técnico da la superficie factible) o la solicitada.
- Monto por hectárea: el ``MontoApoyo`` del ejercicio por hectárea de la modalidad del expediente; si no hay
  uno propio de la modalidad, el que vale para todas. Un concepto sin dinero (monto vacío, como las
  plantaciones navideñas de PS) da 0. Los montos que piden una condición (``requiere``, como la
  certificación FSC en PSAHEM) solo cuentan si se pasa esa condición.
- Ministraciones: las del régimen de pago del expediente (``ajustes_reglas.<CLAVE>.regimen_pago`` en
  ``datos/sistema.json``): por superficie (CC: pago único hasta 5 ha, dos ministraciones arriba), por
  modalidad (PS, RHF) o fijo (PSAHEM). El importe de la última absorbe el redondeo para que la suma dé el
  total.
"""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError

from . import extensiones
from .catalogos import datos_sistema

CENTAVO = Decimal("0.01")


@dataclass
class MinistracionCalculada:
    numero: int
    porcentaje: Decimal
    importe: Decimal
    condicion: str = ""
    fundamento: str = ""


@dataclass
class MontoAprobado:
    superficie_ha: Decimal
    monto_ha: Decimal
    total: Decimal
    concepto: object = None  # MontoApoyo o None
    regimen: str = ""
    ministraciones: list = field(default_factory=list)
    nota: str = ""
    regimen_nombre: str = ""

    @property
    def sin_dinero(self):
        return self.total == 0


def superficie_aprobada(expediente):
    for funcion in extensiones.SUPERFICIE_APROBADA:
        valor = funcion(expediente)
        if valor is not None:
            return Decimal(valor)
    return expediente.superficie_solicitada_ha or Decimal("0")


def _por_hectarea(monto):
    return "hect" in (monto.unidad or "").lower()


def concepto_de_monto(expediente, condiciones=()):
    """El MontoApoyo que aplica (o None si el ejercicio no trae monto por hectárea para el expediente)."""
    condiciones = set(condiciones)
    montos = [m for m in expediente.ejercicio.montos.select_related("modalidad")
              if not m.datos.get("requiere") or m.datos["requiere"] in condiciones]
    propios = [m for m in montos if expediente.modalidad_id and m.modalidad_id == expediente.modalidad_id]
    if propios:
        # Con condición cumplida gana el monto que la pide (por ejemplo, FSC); si no, el primero por hectárea.
        propios.sort(key=lambda m: (not m.datos.get("requiere"), not _por_hectarea(m), m.pk))
        return propios[0]
    generales = [m for m in montos if m.modalidad_id is None and m.monto is not None and _por_hectarea(m)]
    return generales[0] if generales else None


def regimen_de_pago(expediente, superficie):
    ajuste = datos_sistema().get("ajustes_reglas", {}).get(expediente.programa.clave, {}).get("regimen_pago", {})
    if "fijo" in ajuste:
        return ajuste["fijo"]
    if "por_superficie" in ajuste:
        conf = ajuste["por_superficie"]
        umbral = Decimal(str(expediente.ejercicio.datos.get("superficie", {}).get(conf["umbral_ha"])))
        return conf["hasta"] if superficie <= umbral else conf["mas_de"]
    if ajuste.get("por_modalidad") and expediente.modalidad_id:
        return expediente.modalidad.clave
    regimenes = set(expediente.ejercicio.ministraciones.values_list("regimen", flat=True))
    return regimenes.pop() if len(regimenes) == 1 else ""


def nombre_regimen(expediente, regimen):
    """Nombre legible del régimen de pago (P-19): el de la modalidad, el de ``nombres_regimen`` o la clave."""
    if not regimen:
        return ""
    propio = datos_sistema().get("nombres_regimen", {}).get(regimen)
    if propio:
        return propio
    modalidad = expediente.ejercicio.modalidades.filter(clave=regimen).first()
    return modalidad.nombre if modalidad else regimen.replace("_", " ").capitalize()


def ministraciones(expediente, total, regimen):
    reglas = list(expediente.ejercicio.ministraciones.filter(regimen=regimen).order_by("numero"))
    if total == 0 or not reglas:
        return []
    suma_pct = sum(r.porcentaje for r in reglas)
    if suma_pct != 100:
        raise ValidationError(f"Las ministraciones del régimen «{regimen}» suman {suma_pct} %, no 100 %.")
    calculadas, acumulado = [], Decimal("0")
    for i, r in enumerate(reglas):
        if i == len(reglas) - 1:
            importe = total - acumulado
        else:
            importe = (total * r.porcentaje / 100).quantize(CENTAVO, rounding=ROUND_HALF_UP)
            acumulado += importe
        calculadas.append(MinistracionCalculada(r.numero, r.porcentaje, importe, r.condicion, r.fundamento))
    return calculadas


def monto_aprobado(expediente, superficie=None, condiciones=()):
    """Monto del apoyo del expediente (superficie × monto por hectárea) con sus ministraciones."""
    superficie = Decimal(superficie) if superficie is not None else superficie_aprobada(expediente)
    concepto = concepto_de_monto(expediente, condiciones)
    if concepto is None or concepto.monto is None:
        nota = (f"Concepto sin recurso económico: {concepto.unidad}." if concepto else
                "Las reglas no traen un monto por hectárea para esta modalidad.")
        regimen = regimen_de_pago(expediente, superficie)
        return MontoAprobado(superficie, Decimal("0"), Decimal("0"), concepto, regimen, [], nota,
                             nombre_regimen(expediente, regimen))
    total = (superficie * concepto.monto).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    regimen = regimen_de_pago(expediente, superficie)
    return MontoAprobado(superficie, concepto.monto, total, concepto, regimen,
                         ministraciones(expediente, total, regimen), regimen_nombre=nombre_regimen(expediente, regimen))


SIN_APOYO = {"lista_espera", "no_factible", "desechada", "recurso_liberado", "baja"}
ORDEN_APROBADA = 50  # Estado.orden de «aprobada» en datos/flujo_tramite.json


def monto_si_aprobado(expediente):
    """El monto aprobado si el expediente ya es de una persona beneficiaria (de «aprobada» en adelante)."""
    estado = expediente.estado
    if estado.orden < ORDEN_APROBADA or estado.clave in SIN_APOYO:
        return None
    return monto_aprobado(expediente)


def monto_por_hectarea_referencia(ejercicio):
    """Primer monto por hectárea del ejercicio, solo para mostrar en pantalla (no para calcular)."""
    for m in ejercicio.montos.all():
        if m.monto is not None and _por_hectarea(m):
            return m.monto
    return None
