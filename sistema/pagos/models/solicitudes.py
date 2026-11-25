"""HU-5.1 · Solicitud de pago: el oficio de la Delegación, el comprobante de la cuenta y la solicitud de cada
ministración con la copia de sus soportes."""
from django.conf import settings
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from nucleo.models import Acuse, Expediente


class EstadoSolicitud(models.TextChoices):
    """Ciclo de la solicitud de una ministración. HU-5.1 la deja ``enviada``; HU-5.2 la revisa, la devuelve, la acepta
    y la paga (o la remite a la Fiduciaria en PSAHEM)."""

    BORRADOR = "borrador", "Por enviar"
    ENVIADA = "enviada", "Enviada a Administración y Finanzas"
    DEVUELTA = "devuelta", "Devuelta con observaciones"
    ACEPTADA = "aceptada", "Aceptada por Administración y Finanzas"
    REMITIDA = "remitida", "Remitida a la Fiduciaria"
    PAGADA = "pagada", "Pagada"


class OficioPago(models.Model):
    """Oficio de solicitud de pago de la Delegación, en cuanto el contrato está firmado (uno por solicitud)."""

    expediente = models.OneToOneField(Expediente, on_delete=models.PROTECT, related_name="oficio_pago")
    folio = models.CharField(max_length=40, unique=True)
    emitido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    emitido_en = models.DateTimeField(default=timezone.now)
    archivo = models.FileField(upload_to="pagos/oficios/%Y/", max_length=300)
    huella = models.CharField(max_length=64, blank=True, help_text="SHA-256 del PDF.")
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    history = HistoricalRecords()

    class Meta:
        ordering = ["-emitido_en"]
        verbose_name = "oficio de solicitud de pago"
        verbose_name_plural = "oficios de solicitud de pago"

    def __str__(self):
        return self.folio


def ruta_comprobante(instancia, nombre):
    exp = instancia.expediente
    return f"pagos/{exp.ejercicio.anio}/{exp.folio}/{nombre}"


class ComprobanteCuenta(models.Model):
    """Comprobante de la cuenta bancaria de la persona beneficiaria (donde las reglas lo piden). El vigente es el
    más reciente; un cambio de cuenta se registra con un comprobante nuevo."""

    expediente = models.ForeignKey(Expediente, on_delete=models.CASCADE, related_name="comprobantes_cuenta")
    archivo = models.FileField(upload_to=ruta_comprobante, max_length=300)
    descripcion = models.CharField(max_length=250, blank=True)
    huella = models.CharField(max_length=64, blank=True)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    subido_en = models.DateTimeField(default=timezone.now)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-subido_en", "-id"]
        verbose_name = "comprobante de cuenta bancaria"
        verbose_name_plural = "comprobantes de cuenta bancaria"

    def __str__(self):
        return f"Comprobante de {self.expediente.folio}"


class SolicitudPago(models.Model):
    """Solicitud de pago de una ministración de un expediente: una por expediente y número de ministración. Guarda
    la copia de los soportes que tenía al enviarse y la fecha y hora del envío a Administración y Finanzas."""

    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="solicitudes_pago")
    ministracion = models.PositiveIntegerField(help_text="Número de la ministración (1 = primera).")
    porcentaje = models.DecimalField(max_digits=6, decimal_places=2)
    importe = models.DecimalField(max_digits=14, decimal_places=2, help_text="El de nucleo.montos.monto_aprobado.")
    tipo_pago = models.CharField(max_length=30, help_text="Clave de datos/pagos.json (tipos_pago).")
    estado = models.CharField(max_length=15, choices=EstadoSolicitud.choices, default=EstadoSolicitud.BORRADOR)
    preparada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    preparada_en = models.DateTimeField(default=timezone.now)
    enviada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                    related_name="+")
    enviada_en = models.DateTimeField(null=True, blank=True, help_text="Fecha y hora del envío a Administración y Finanzas.")
    envios = models.PositiveIntegerField(default=0, help_text="Veces que se envió (una devuelta se corrige y se reenvía).")
    acuse_envio = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    soportes = models.JSONField(default=list, blank=True, help_text="Copia de los soportes al momento del envío.")
    observaciones = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["expediente__folio", "ministracion"]
        unique_together = [("expediente", "ministracion")]
        verbose_name = "solicitud de pago"
        verbose_name_plural = "solicitudes de pago"

    def __str__(self):
        return self.folio

    @property
    def folio(self):
        return f"{self.expediente.folio}/M{self.ministracion}"

    @property
    def enviada(self):
        return self.enviada_en is not None
