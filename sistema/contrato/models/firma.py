"""HU-3.3 · Firma del contrato: la firma registrada por la Delegación (con la verificación de firmas y sello y,
en MFS y PEG, la formalización propia del programa) y el señalamiento de lo que no se firmó en plazo."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from nucleo.models import Acuse, Expediente

from .contratos import Contrato


class Firmante(models.TextChoices):
    PERSONA = "persona", "La persona beneficiaria"
    REPRESENTANTE = "representante", "Su representante"


def ruta_firma(instancia, nombre):
    exp = getattr(instancia, "expediente", None) or instancia.firma.expediente
    return f"contratos/{exp.ejercicio.anio}/firmados/{exp.folio}/{nombre}"


class FirmaContrato(models.Model):
    """El contrato firmado de una solicitud: fecha y hora de la firma, quién firma y el documento digitalizado."""

    contrato = models.OneToOneField(Contrato, on_delete=models.PROTECT, related_name="firma")
    expediente = models.OneToOneField(Expediente, on_delete=models.PROTECT, related_name="firma_contrato")
    firmado_en = models.DateTimeField(help_text="Fecha y hora de la firma.")
    firmante = models.CharField(max_length=15, choices=Firmante.choices)
    firmante_nombre = models.CharField(max_length=250)
    archivo = models.FileField(upload_to=ruta_firma, max_length=300, help_text="Contrato firmado, digitalizado.")
    huella = models.CharField(max_length=64, blank=True, help_text="SHA-256 del archivo.")
    verificacion = models.JSONField(default=list, help_text="Puntos verificados: clave, texto y si se cumple.")
    fecha_programada = models.DateField(null=True, blank=True, help_text="Fecha programada de firma (R-03).")
    fecha_liberacion = models.DateField(null=True, blank=True, help_text="Vencimiento para liberar el recurso (R-03).")
    en_fecha_programada = models.BooleanField(default=True)
    dentro_de_plazo = models.BooleanField(default=True, help_text="La firma es anterior al vencimiento para liberar.")
    observaciones = models.TextField(blank=True)
    registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    registrada_en = models.DateTimeField(default=timezone.now)
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-firmado_en"]
        verbose_name = "firma del contrato"
        verbose_name_plural = "firmas de contratos"

    def __str__(self):
        return f"Firma de {self.contrato.folio}"

    @property
    def situacion(self):
        """«En fecha programada» o «Fuera de la fecha programada» (antes del vencimiento para liberar)."""
        return "En la fecha programada" if self.en_fecha_programada else "Fuera de la fecha programada"


class ElementoFormalizacion(models.Model):
    """Elemento propio del programa que completa la firma (MFS: contrato de servicios técnicos con el RFN y carta
    compromiso; PEG: credencial del Guardabosque entregada)."""

    firma = models.ForeignKey(FirmaContrato, on_delete=models.CASCADE, related_name="elementos")
    clave = models.CharField(max_length=60)
    nombre = models.CharField(max_length=250)
    dato_etiqueta = models.CharField(max_length=120, blank=True)
    dato = models.CharField(max_length=120, blank=True, help_text="RFN del prestador, folio de la credencial…")
    archivo = models.FileField(upload_to=ruta_firma, max_length=300)

    class Meta:
        ordering = ["id"]
        unique_together = [("firma", "clave")]


class SinFirma(models.Model):
    """Contrato sin firma al vencer el plazo: queda señalado para liberar el recurso (criterio 3, P-08).

    El señalamiento lo hace ``revisar_plazos``; liberar el recurso **no es automático**: lo confirma una persona del
    área responsable con un motivo. La reasignación a la lista de espera es del sprint 3 (gancho
    ``extensiones.AL_LIBERAR_RECURSO``)."""

    expediente = models.OneToOneField(Expediente, on_delete=models.PROTECT, related_name="sin_firma")
    vencio_el = models.DateField(null=True, blank=True, help_text="Vencimiento para liberar el recurso que pasó.")
    senalado_en = models.DateTimeField(default=timezone.now)
    motivo = models.TextField()
    liberado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name="+")
    liberado_en = models.DateTimeField(null=True, blank=True)
    motivo_liberacion = models.TextField(blank=True)
    acuse_liberacion = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-senalado_en"]
        verbose_name = "contrato sin firma en plazo"
        verbose_name_plural = "contratos sin firma en plazo"

    def __str__(self):
        return f"Sin firma: {self.expediente.folio}"

    @property
    def liberado(self):
        return self.liberado_en is not None
