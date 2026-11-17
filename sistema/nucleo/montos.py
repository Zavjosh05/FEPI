"""Monto aprobado de un expediente y sus ministraciones (S2-02d; generalizado en S3-02). Lo usan el Comité (HU-2.3),
el contrato (HU-3.2) y los pagos (HU-5.x): una sola regla para todo el sistema.

- Superficie: la que se pase o, si no, la superficie aprobada que dé un módulo
  (``extensiones.SUPERFICIE_APROBADA``: el dictamen técnico da la superficie factible) o la solicitada.
- Tipo de monto: sale de la unidad del monto en las reglas (``datos/sistema.json`` → ``tipos_de_monto``):
  **por hectárea** (CC, PS, RHF, PSAHEM: superficie × monto), **por apoyo** (MFS: un monto fijo por concepto) o
  **por persona** (PEG: monto anual por Guardabosque × personas beneficiarias del expediente, una por núcleo agrario).
- Monto: el ``MontoApoyo`` de la modalidad del expediente; si no hay uno propio de la modalidad, el que vale para
  todas. Un concepto sin dinero (monto vacío, como las plantaciones navideñas de PS) da 0. Los montos que piden una
  condición (``requiere``, como la certificación FSC en PSAHEM) solo cuentan si se pasa esa condición. Si la modalidad
  trae varios montos fijos marcados con ``componente`` (MFS, certificación FSC grupal: acompañamiento, certificación y
  administrador de recursos), el apoyo es su suma (lectura del cuadro de las ROP por confirmar, R-17).
- Ministraciones: las del régimen de pago del expediente (``ajustes_reglas.<CLAVE>.regimen_pago`` en
  ``datos/sistema.json``): por superficie (CC: pago único hasta 5 ha, dos ministraciones arriba), por
  modalidad (PS, RHF), por el mapa de modalidad a régimen de las reglas (MFS: ``regimen_pago_por_modalidad``,
  estudio técnico 70/30 y certificación 50/50) o fijo (PSAHEM 70/30; PEG hasta cuatro). Una ministración marcada
  ``supuesto`` en las reglas (PEG: 25 % cada una, el reparto no está en las ROP) se muestra como tal. El importe de la
  última absorbe el redondeo para que la suma dé el total.
"""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError

from . import extensiones
from .catalogos import datos_sistema
from .templatetags.moneda import formato_moneda

CENTAVO = Decimal("0.01")
POR_HECTAREA, POR_APOYO, POR_PERSONA = "por_hectarea", "por_apoyo", "por_persona"


@dataclass
class MinistracionCalculada:
    numero: int
    porcentaje: Decimal
    importe: Decimal
    condicion: str = ""
    fundamento: str = ""
    supuesto: bool = False  # el porcentaje no está en las ROP (PEG: 25 % cada una, por confirmar con el cliente)


@dataclass
class MontoAprobado:
    superficie_ha: Decimal
    monto_ha: Decimal  # monto unitario: por hectárea, por apoyo o por persona según ``tipo_monto``
    total: Decimal
    concepto: object = None  # MontoApoyo o None
    regimen: str = ""
    ministraciones: list = field(default_factory=list)
    nota: str = ""
    regimen_nombre: str = ""
    tipo_monto: str = POR_HECTAREA
    cantidad: Decimal = Decimal("0")  # hectáreas, apoyos o personas, según el tipo de monto
    supuesto: bool = False  # alguna ministración es un supuesto del archivo de reglas (PEG)

    @property
    def sin_dinero(self):
        return self.total == 0

    @property
    def monto_unitario(self):
        return self.monto_ha

    @property
    def por_hectarea(self):
        return self.tipo_monto == POR_HECTAREA

    @property
    def texto_unidad(self):
        """«por hectárea», «por apoyo» o «por persona beneficiaria» (``tipos_de_monto.nombres``)."""
        return nombres_tipo_monto().get(self.tipo_monto, self.tipo_monto.replace("_", " "))

    @property
    def texto_base(self):
        """«$2,000.00 por hectárea», «$30,000.00 por apoyo», «$25,550.00 por persona beneficiaria»."""
        return f"{formato_moneda(self.monto_ha)} {self.texto_unidad}"

    @property
    def texto_calculo(self):
        """Cómo se llega al total, para pantallas y documentos."""
        if self.tipo_monto == POR_HECTAREA:
            return f"{self.superficie_ha.normalize():f} ha × {formato_moneda(self.monto_ha)} = {formato_moneda(self.total)}"
        if self.tipo_monto == POR_PERSONA:
            return (f"{self.cantidad.normalize():f} × {formato_moneda(self.monto_ha)} {self.texto_unidad} = "
                    f"{formato_moneda(self.total)}")
        return f"{formato_moneda(self.total)} (monto fijo {self.texto_unidad})"


def superficie_aprobada(expediente):
    for funcion in extensiones.SUPERFICIE_APROBADA:
        valor = funcion(expediente)
        if valor is not None:
            return Decimal(valor)
    return expediente.superficie_solicitada_ha or Decimal("0")


# ----------------------------------------------------------------------------- tipo de monto
def _config_tipos():
    return datos_sistema().get("tipos_de_monto", {})


def nombres_tipo_monto():
    return _config_tipos().get("nombres", {})


def tipo_de_monto(monto, config=None):
    """Tipo del monto según su unidad en las reglas (primera regla de ``tipos_de_monto`` que coincida) o None."""
    unidad = (monto.unidad or "").lower()
    for regla in (config if config is not None else _config_tipos()).get("reglas", []):
        if regla["contiene"].lower() in unidad:
            return regla["tipo"]
    return None


def _por_hectarea(monto):
    return tipo_de_monto(monto) == POR_HECTAREA


def personas_beneficiarias(expediente):
    """Personas beneficiarias del expediente para un monto por persona. PEG: una sola persona Guardabosque por núcleo
    agrario (ROP PEG 8.1.2 k), así que siempre es 1."""
    return Decimal("1")


def concepto_de_monto(expediente, condiciones=()):
    """El MontoApoyo que aplica (o None si el ejercicio no trae un monto para el expediente)."""
    condiciones = set(condiciones)
    config = _config_tipos()
    montos = [m for m in expediente.ejercicio.montos.select_related("modalidad")
              if not m.datos.get("requiere") or m.datos["requiere"] in condiciones]
    propios = [m for m in montos if expediente.modalidad_id and m.modalidad_id == expediente.modalidad_id]
    if propios:
        # Con condición cumplida gana el monto que la pide (por ejemplo, FSC); si no, el primero con tipo conocido.
        propios.sort(key=lambda m: (not m.datos.get("requiere"), tipo_de_monto(m, config) is None, m.pk))
        return propios[0]
    generales = [m for m in montos if m.modalidad_id is None and m.monto is not None
                 and tipo_de_monto(m, config) is not None]
    return generales[0] if generales else None


def _componentes(expediente, concepto):
    """Montos de la misma modalidad marcados con ``componente`` (se suman: certificación FSC grupal en MFS)."""
    if not concepto.datos.get("componente") or concepto.modalidad_id is None:
        return [concepto]
    return [m for m in expediente.ejercicio.montos.filter(modalidad_id=concepto.modalidad_id).order_by("pk")
            if m.datos.get("componente") and m.monto is not None]


# ----------------------------------------------------------------------------- régimen y ministraciones
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
    if ajuste.get("mapa_de_reglas") and expediente.modalidad_id:
        mapa = expediente.ejercicio.datos.get(ajuste["mapa_de_reglas"], {})
        return mapa.get(expediente.modalidad.clave, "")
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
        calculadas.append(MinistracionCalculada(r.numero, r.porcentaje, importe, r.condicion, r.fundamento,
                                                r.supuesto))
    return calculadas


def monto_aprobado(expediente, superficie=None, condiciones=()):
    """Monto del apoyo del expediente (superficie × monto por hectárea, monto fijo por apoyo o monto por persona) con
    sus ministraciones."""
    superficie = Decimal(superficie) if superficie is not None else superficie_aprobada(expediente)
    concepto = concepto_de_monto(expediente, condiciones)
    regimen = regimen_de_pago(expediente, superficie)
    if concepto is None or concepto.monto is None:
        nota = (f"Concepto sin recurso económico: {concepto.unidad}." if concepto else
                "Las reglas no traen un monto para esta modalidad.")
        return MontoAprobado(superficie, Decimal("0"), Decimal("0"), concepto, regimen, [], nota,
                             nombre_regimen(expediente, regimen))
    tipo = tipo_de_monto(concepto) or POR_HECTAREA
    nota = ""
    if tipo == POR_HECTAREA:
        cantidad, unitario = superficie, concepto.monto
    else:
        partes = _componentes(expediente, concepto)
        unitario = sum((m.monto for m in partes), Decimal("0"))
        if len(partes) > 1:
            nota = ("Suma de los componentes del cuadro de montos (" +
                    ", ".join(m.datos["componente"].replace("_", " ") for m in partes) +
                    "); la lectura de las columnas del cuadro está por confirmar con el cliente.")
        cantidad = personas_beneficiarias(expediente) if tipo == POR_PERSONA else Decimal("1")
    total = (cantidad * unitario).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    calculadas = ministraciones(expediente, total, regimen)
    supuesto = any(m.supuesto for m in calculadas)
    if supuesto:
        nota = (nota + " " if nota else "") + ("El reparto de las ministraciones no está en las Reglas de Operación: "
                                              "los porcentajes son un supuesto por confirmar con el cliente.")
    return MontoAprobado(superficie, unitario, total, concepto, regimen, calculadas, nota,
                         nombre_regimen(expediente, regimen), tipo_monto=tipo, cantidad=cantidad, supuesto=supuesto)


SIN_APOYO = {"lista_espera", "no_factible", "desechada", "recurso_liberado"}
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
