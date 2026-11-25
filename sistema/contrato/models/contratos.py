"""HU-3.2 · Modelos de contrato (con sus versiones y la validación de la Unidad Jurídica), contratos elaborados
y, preparado para el sprint 3, el adendum (ampliación de plazo por causa externa en MFS).

Las ROP no traen el texto del modelo de Contrato de Adhesión ni del Convenio de Concertación (R-07): el área
responsable lo registra y la Unidad Jurídica lo valida (S2-04). Cada cambio del texto crea una **versión**
nueva que queda sin validar; un contrato se elabora siempre sobre una versión validada y la conserva.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from nucleo.models import Acuse, Ejercicio, Expediente


class TipoModelo(models.TextChoices):
    CONTRATO_ADHESION = "contrato_adhesion", "Contrato de Adhesión"
    CONVENIO_CONCERTACION = "convenio_concertacion", "Convenio de Concertación"
    ADENDUM = "adendum", "Adendum"


class EstadoVersion(models.TextChoices):
    PENDIENTE = "pendiente", "Por validar"
    VALIDADA = "validada", "Validada por la Unidad Jurídica"
    DEVUELTA = "devuelta", "Devuelta con observaciones"


class ModeloContrato(models.Model):
    """Un modelo (por programa-ejercicio y tipo) con sus versiones; la vigente es la última."""

    ejercicio = models.ForeignKey(Ejercicio, on_delete=models.PROTECT, related_name="modelos_contrato")
    tipo = models.CharField(max_length=30, choices=TipoModelo.choices)
    nombre = models.CharField(max_length=200)
    es_base = models.BooleanField(default=False, help_text="Plantilla base propia del sistema (borrador por validar).")
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(default=timezone.now)

    history = HistoricalRecords()

    class Meta:
        ordering = ["ejercicio", "tipo", "nombre"]
        unique_together = [("ejercicio", "tipo", "nombre")]
        verbose_name = "modelo de contrato"
        verbose_name_plural = "modelos de contrato"

    def __str__(self):
        return f"{self.nombre} ({self.ejercicio})"

    @property
    def vigente(self):
        """Última versión del texto (la que cuenta para elaborar contratos)."""
        return self.versiones.order_by("-numero").first()

    @property
    def validado(self):
        v = self.vigente
        return v is not None and v.estado == EstadoVersion.VALIDADA


class VersionModelo(models.Model):
    modelo = models.ForeignKey(ModeloContrato, on_delete=models.CASCADE, related_name="versiones")
    numero = models.PositiveIntegerField()
    texto = models.TextField(help_text="Plantilla con campos «{{campo}}» que se llenan con los datos del expediente.")
    estado = models.CharField(max_length=12, choices=EstadoVersion.choices, default=EstadoVersion.PENDIENTE)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creada_en = models.DateTimeField(default=timezone.now)
    revisada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name="+")
    revisada_en = models.DateTimeField(null=True, blank=True, help_text="Fecha y hora de la validación o devolución.")
    observaciones = models.TextField(blank=True, help_text="Observaciones de la Unidad Jurídica.")

    history = HistoricalRecords()

    class Meta:
        ordering = ["modelo", "-numero"]
        unique_together = [("modelo", "numero")]

    def __str__(self):
        return f"{self.modelo.nombre}, versión {self.numero}"


class EstadoContrato(models.TextChoices):
    ELABORADO = "elaborado", "Elaborado"
    ENVIADO = "enviado", "Enviado a la Delegación"


def ruta_contrato(instancia, nombre):
    exp = getattr(instancia, "expediente", None) or instancia.contrato.expediente  # el adendum cuelga del contrato
    return f"contratos/{exp.ejercicio.anio}/{nombre}"


class Contrato(models.Model):
    """El contrato (o convenio) de una solicitud aprobada: uno por expediente."""

    expediente = models.OneToOneField(Expediente, on_delete=models.PROTECT, related_name="contrato")
    folio = models.CharField(max_length=40, unique=True, editable=False)
    version_modelo = models.ForeignKey(VersionModelo, on_delete=models.PROTECT, related_name="contratos")
    tipo = models.CharField(max_length=30, choices=TipoModelo.choices)
    texto = models.TextField(help_text="Texto del modelo con los datos del expediente (copia de lo elaborado).")
    datos = models.JSONField(default=dict, blank=True, help_text="Datos con los que se llenó el modelo.")
    archivo = models.FileField(upload_to=ruta_contrato, max_length=300)
    huella = models.CharField(max_length=64, blank=True, help_text="SHA-256 del PDF.")
    elaborado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    elaborado_en = models.DateTimeField(default=timezone.now)
    rehechos = models.PositiveIntegerField(default=0, help_text="Veces que se rehízo antes de enviarlo.")
    estado = models.CharField(max_length=12, choices=EstadoContrato.choices, default=EstadoContrato.ELABORADO)
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                    related_name="+")
    enviado_en = models.DateTimeField(null=True, blank=True, help_text="Fecha y hora del envío a la Delegación.")
    acuse_envio = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    history = HistoricalRecords()

    class Meta:
        ordering = ["-elaborado_en"]

    def __str__(self):
        return f"{self.folio} · {self.expediente.folio}"

    @property
    def enviado(self):
        return self.enviado_en is not None


class Adendum(models.Model):
    """Preparado para el sprint 3 (sin pantalla ni servicio): adendum o ampliación de plazo ligada a un contrato.

    La función M3.2 incluye la ampliación de plazo por causa externa en MFS; MFS aún no tiene archivo de reglas
    (llegan en el sprint 3), por eso solo queda el modelo de datos."""

    contrato = models.ForeignKey(Contrato, on_delete=models.PROTECT, related_name="adendums")
    version_modelo = models.ForeignKey(VersionModelo, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    motivo = models.TextField(help_text="Causa externa que justifica la ampliación.")
    plazo_original = models.DateField(null=True, blank=True)
    plazo_nuevo = models.DateField(null=True, blank=True)
    archivo = models.FileField(upload_to=ruta_contrato, max_length=300, blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(default=timezone.now)

    history = HistoricalRecords()

    class Meta:
        ordering = ["contrato", "creado_en"]
        verbose_name = "adendum"
        verbose_name_plural = "adendums"

    def __str__(self):
        return f"Adendum de {self.contrato.folio}"
