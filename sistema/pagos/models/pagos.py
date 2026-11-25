"""HU-5.2 · Pago de la ministración: la revisión de Administración y Finanzas, el pago (transferencia, cheque excepcional o
depósito) y, en PSAHEM, la remisión a la Fiduciaria."""
from django.conf import settings
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from nucleo.models import Acuse, Expediente, Notificacion

from .solicitudes import SolicitudPago


class ResultadoRevision(models.TextChoices):
    ACEPTADA = "aceptada", "Aceptada"
    DEVUELTA = "devuelta", "Devuelta con observaciones"


class RevisionSolicitud(models.Model):
    """Revisión de una solicitud por Administración y Finanzas: la acepta o la devuelve al área responsable con
    observaciones. Una solicitud devuelta puede tener varias revisiones (se corrige y se reenvía)."""

    solicitud = models.ForeignKey(SolicitudPago, on_delete=models.PROTECT, related_name="revisiones")
    resultado = models.CharField(max_length=10, choices=ResultadoRevision.choices)
    envio = models.PositiveIntegerField(default=1, help_text="Número de envío de la solicitud que se revisó.")
    observaciones = models.TextField(blank=True)
    revisada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    revisada_en = models.DateTimeField(default=timezone.now)
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    history = HistoricalRecords()

    class Meta:
        ordering = ["-revisada_en", "-id"]
        verbose_name = "revisión de solicitud de pago"
        verbose_name_plural = "revisiones de solicitudes de pago"

    def __str__(self):
        return f"{self.solicitud.folio}: {self.get_resultado_display()}"


class TipoPagoRegistrado(models.TextChoices):
    TRANSFERENCIA = "transferencia", "Transferencia electrónica"
    CHEQUE_EXCEPCIONAL = "cheque_excepcional", "Cheque (caso excepcional)"
    DEPOSITO = "deposito", "Depósito al Guardabosque"


class Pago(models.Model):
    """Pago de una ministración: siempre cuelga de una solicitud aceptada y es uno solo por solicitud."""

    solicitud = models.OneToOneField(SolicitudPago, on_delete=models.PROTECT, related_name="pago")
    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="pagos")
    ministracion = models.PositiveIntegerField()
    importe = models.DecimalField(max_digits=14, decimal_places=2)
    tipo = models.CharField(max_length=20, choices=TipoPagoRegistrado.choices)
    referencia = models.CharField(max_length=120, help_text="Referencia de la transferencia o depósito, o número de cheque.")
    fecha_pago = models.DateField(help_text="Fecha en que se realizó el pago.")
    motivo_cheque = models.TextField(blank=True, help_text="Obligatorio en el cheque: es un caso excepcional.")
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    registrado_en = models.DateTimeField(default=timezone.now)
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    aviso = models.ForeignKey(Notificacion, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                              help_text="Aviso de pago a la persona beneficiaria por conducto de la Delegación.")

    history = HistoricalRecords()

    class Meta:
        ordering = ["-fecha_pago", "-id"]
        verbose_name = "pago de ministración"
        verbose_name_plural = "pagos de ministraciones"

    def __str__(self):
        return f"Pago de {self.solicitud.folio}"


class RemisionFiduciaria(models.Model):
    """PSAHEM: solicitud del pago a la Fiduciaria por la Secretaría Técnica del Comité Técnico, con fecha y hora y su plazo de
    5 días hábiles desde que recibió la solicitud del área (ROP PSAHEM 10.1 fr. X, líneas 2290 a 2292)."""

    solicitud = models.OneToOneField(SolicitudPago, on_delete=models.PROTECT, related_name="remision")
    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="remisiones_fiduciaria")
    ministracion = models.PositiveIntegerField()
    remitida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    remitida_en = models.DateTimeField(default=timezone.now, help_text="Fecha y hora de la remisión a la Fiduciaria.")
    recibida_en = models.DateTimeField(help_text="Cuando la Secretaría Técnica recibió la solicitud del área (envío de HU-5.1).")
    vence_el = models.DateField(null=True, blank=True, help_text="Fin de los 5 días hábiles de la Secretaría Técnica.")
    en_plazo = models.BooleanField(default=True)
    oficio = models.CharField(max_length=120, blank=True, help_text="Oficio o referencia de la remisión.")
    observaciones = models.TextField(blank=True)
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    history = HistoricalRecords()

    class Meta:
        ordering = ["-remitida_en", "-id"]
        verbose_name = "remisión a la Fiduciaria"
        verbose_name_plural = "remisiones a la Fiduciaria"

    def __str__(self):
        return f"Remisión de {self.solicitud.folio}"
