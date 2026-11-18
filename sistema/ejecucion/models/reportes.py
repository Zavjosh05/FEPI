"""HU-4.3 · Evaluación de reportes (Guardabosques): la revisión que hace la Delegación de cada reporte mensual y acuse de
depósito, la evaluación por Guardabosque y por periodo que hace la Dirección de Protección Forestal y el envío de la
evaluación del periodo al CASPEG (que la valida con un acuerdo de su sesión de seguimiento, HU-2.4)."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from nucleo.models import Acuse, Ejercicio, Expediente, Unidad

from .comprobaciones import Comprobacion


class ResultadoRevision(models.TextChoices):
    REVISADO = "revisado", "Revisado"
    CON_OBSERVACIONES = "con_observaciones", "Revisado con observaciones"
    DEVUELTO = "devuelto", "Devuelto para corregir"


class RevisionReporte(models.Model):
    """Revisión de la Delegación de un reporte o de un acuse de depósito recibido (por el portal o en ventanilla). La
    vigente de cada comprobación es la más reciente."""

    comprobacion = models.ForeignKey(Comprobacion, on_delete=models.CASCADE, related_name="revisiones")
    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="revisiones_reporte")
    periodo = models.CharField(max_length=20, blank=True, help_text="Periodo del reporte (vacío en el acuse de depósito).")
    resultado = models.CharField(max_length=20, choices=ResultadoRevision.choices)
    observaciones = models.TextField(blank=True)
    revisada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    unidad = models.ForeignKey(Unidad, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    revisada_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-revisada_en", "-id"]
        verbose_name = "revisión de reporte"
        verbose_name_plural = "revisiones de reportes"

    def __str__(self):
        return f"{self.expediente.folio} · {self.comprobacion.nombre} · {self.get_resultado_display()}"


class ResultadoEvaluacion(models.TextChoices):
    CUMPLE = "cumple", "Cumple"
    NO_CUMPLE = "no_cumple", "No cumple"
    NO_ENTREGO = "no_entrego", "No entregó"


class EnvioEvaluacion(models.Model):
    """La evaluación de un periodo enviada al CASPEG para su validación, con su fecha, su hora y su acuse."""

    ejercicio = models.ForeignKey(Ejercicio, on_delete=models.PROTECT, related_name="envios_evaluacion")
    periodo = models.CharField(max_length=20, help_text="Clave de periodos_reportes de las reglas.")
    nombre_periodo = models.CharField(max_length=60, blank=True)
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    unidad = models.ForeignKey(Unidad, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    enviado_en = models.DateTimeField(default=timezone.now, help_text="Fecha y hora del envío al CASPEG.")
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    cumplen = models.PositiveIntegerField(default=0)
    no_cumplen = models.PositiveIntegerField(default=0)
    no_entregaron = models.PositiveIntegerField(default=0)
    datos = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-enviado_en", "-id"]
        verbose_name = "envío de la evaluación de un periodo"

    def __str__(self):
        return f"{self.ejercicio} · {self.nombre_periodo or self.periodo}"

    @property
    def total(self):
        return self.cumplen + self.no_cumplen + self.no_entregaron


class EvaluacionPeriodo(models.Model):
    """Evaluación de un Guardabosque (expediente) en un periodo: cumple, no cumple (con su motivo) o no entregó. Se puede
    cambiar mientras no se envía al CASPEG."""

    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="evaluaciones_periodo")
    periodo = models.CharField(max_length=20)
    nombre_periodo = models.CharField(max_length=60, blank=True)
    resultado = models.CharField(max_length=15, choices=ResultadoEvaluacion.choices)
    motivo = models.TextField(blank=True)
    comprobacion = models.ForeignKey(Comprobacion, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                     help_text="El reporte que se evaluó (vacío si no entregó).")
    automatica = models.BooleanField(default=False, help_text="«No entregó» lo pone el sistema: no hay reporte del periodo.")
    evaluada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    unidad = models.ForeignKey(Unidad, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    evaluada_en = models.DateTimeField(default=timezone.now)
    envio = models.ForeignKey(EnvioEvaluacion, null=True, blank=True, on_delete=models.PROTECT, related_name="evaluaciones")

    class Meta:
        ordering = ["periodo", "expediente__folio"]
        constraints = [models.UniqueConstraint(fields=["expediente", "periodo"], name="una_evaluacion_por_periodo")]
        verbose_name = "evaluación de un periodo"
        verbose_name_plural = "evaluaciones de periodos"

    def __str__(self):
        return f"{self.expediente.folio} · {self.nombre_periodo or self.periodo}: {self.get_resultado_display()}"

    @property
    def senalado(self):
        """Quien no cumplió o no entregó queda señalado para el seguimiento de incumplimientos."""
        return self.resultado != ResultadoEvaluacion.CUMPLE
