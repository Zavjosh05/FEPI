"""HU-4.2 · Verificación en campo: el resultado (documento, superficie verificada y su ajuste, sobrevivencia), la entrega del
documento dentro del plazo del programa y las incidencias, cada una con su tipo y el documento que la avala."""
from django.conf import settings
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from nucleo.models import Acuse, Expediente, Unidad

from .comprobaciones import Comprobacion


class ResultadoVerificacion(models.TextChoices):
    CUMPLE = "cumple", "Cumple lo comprometido"
    AJUSTE = "ajuste", "Cumple con ajuste de superficie"
    INCUMPLIMIENTO = "incumplimiento", "Incumplimiento"


def ruta_verificacion(instancia, nombre):
    exp = instancia.expediente
    return f"ejecucion/{exp.ejercicio.anio}/{exp.folio}/verificacion/{nombre}"


class Verificacion(models.Model):
    """Resultado de la verificación de un expediente. La fecha y la hora del registro son las de la ENTREGA del documento de
    verificación al área responsable (R-04): con ellas se califica el plazo. La vigente es la más reciente."""

    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="verificaciones")
    comprobacion = models.ForeignKey(Comprobacion, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                     help_text="La comprobación que se verificó (aviso de término, informe, bitácora…).")
    tipo_documento = models.CharField(max_length=40, help_text="Clave de datos/ejecucion.json (verificacion.tipos_documento).")
    nombre_documento = models.CharField(max_length=200)
    fecha_visita = models.DateField(null=True, blank=True)
    superficie_aprobada_ha = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    superficie_verificada_ha = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    ajuste_pct = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True,
                                     help_text="Superficie verificada entre la aprobada, en porcentaje.")
    sobrevivencia_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    resultado = models.CharField(max_length=20, choices=ResultadoVerificacion.choices)
    observaciones = models.TextField(blank=True)
    archivo = models.FileField(upload_to=ruta_verificacion, max_length=300)
    huella = models.CharField(max_length=64, blank=True)
    registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    unidad = models.ForeignKey(Unidad, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    registrada_en = models.DateTimeField(default=timezone.now, help_text="Fecha y hora de la entrega del documento.")
    vence = models.DateField(null=True, blank=True)
    en_plazo = models.BooleanField(null=True)
    plazo_texto = models.CharField(max_length=300, blank=True)
    pago_proporcional = models.BooleanField(default=False)
    total_verificado = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    importe_ajustado = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True,
                                           help_text="Importe de la ministración que depende de la verificación.")
    ministracion_ajustada = models.PositiveIntegerField(null=True, blank=True)
    excedente_ministrado = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True,
                                               help_text="Lo ya ministrado por encima de lo verificado (gancho de HU-6.2).")
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    datos = models.JSONField(default=dict, blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-registrada_en", "-id"]
        verbose_name = "verificación en campo"
        verbose_name_plural = "verificaciones en campo"

    def __str__(self):
        return f"{self.expediente.folio} · {self.get_resultado_display()} ({self.registrada_en:%d/%m/%Y})"

    @property
    def situacion_plazo(self):
        if self.en_plazo is None:
            return "sin plazo que calificar"
        return "en plazo" if self.en_plazo else "fuera de plazo"

    @staticmethod
    def _sin_ceros(valor):
        return "" if valor is None else f"{valor.normalize():f}"

    @property
    def verificada_texto(self):
        return self._sin_ceros(self.superficie_verificada_ha)

    @property
    def aprobada_texto(self):
        return self._sin_ceros(self.superficie_aprobada_ha)


def ruta_incidencia(instancia, nombre):
    exp = instancia.expediente
    return f"ejecucion/{exp.ejercicio.anio}/{exp.folio}/incidencias/{nombre}"


class Incidencia(models.Model):
    """Incidencia encontrada o comprobada en la verificación: su tipo y el documento que la avala. Las de incumplimiento las
    atiende el área responsable con el seguimiento de incumplimientos (HU-6.2, ``extensiones.AL_INCIDENCIA``)."""

    verificacion = models.ForeignKey(Verificacion, on_delete=models.CASCADE, related_name="incidencias")
    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="incidencias")
    tipo = models.CharField(max_length=30, help_text="Clave de datos/ejecucion.json (verificacion.tipos_incidencia).")
    descripcion = models.TextField()
    archivo = models.FileField(upload_to=ruta_incidencia, max_length=300)
    huella = models.CharField(max_length=64, blank=True)
    registrada_en = models.DateTimeField(default=timezone.now)
    atendida_en = models.DateTimeField(null=True, blank=True, help_text="La llena HU-6.2 (omisiones, suspensión, cancelación).")
    datos = models.JSONField(default=dict, blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["registrada_en", "id"]
        verbose_name = "incidencia"
        verbose_name_plural = "incidencias"

    def __str__(self):
        return f"{self.expediente.folio} · {self.tipo}"

    @property
    def nombre_tipo(self):
        from ..comprobaciones import datos_ejecucion

        return datos_ejecucion()["verificacion"]["tipos_incidencia"].get(self.tipo, self.tipo)

    @property
    def nombre_archivo(self):
        return self.archivo.name.rsplit("/", 1)[-1] if self.archivo else ""
