"""Portal de personas beneficiarias (decisión de Joshua S2-05): cuentas externas sin unidad interna, sus accesos a
expedientes y el código de consulta de respaldo (folio + código, sin cuenta)."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from nucleo.models import Acuse, Expediente, Persona


class RolAcceso(models.TextChoices):
    BENEFICIARIA = "beneficiaria", "Persona beneficiaria"
    PRESTADOR = "prestador", "Prestador de servicios forestales (RFN)"


class CuentaExterna(models.Model):
    """Usuario externo: la persona beneficiaria o el Guardabosque (y el prestador con RFN). Usuario = CURP; no tiene
    unidad interna. Primer acceso con un código de un solo uso impreso en el acuse; la persona define su contraseña."""

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cuenta_externa")
    persona = models.ForeignKey(Persona, on_delete=models.PROTECT, related_name="cuentas_portal")
    creada_en = models.DateTimeField(default=timezone.now)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    codigo_hash = models.CharField(max_length=128, blank=True, help_text="Código de primer acceso (cifrado).")
    codigo_emitido_en = models.DateTimeField(null=True, blank=True)
    activada_en = models.DateTimeField(null=True, blank=True, help_text="Primer acceso: el código ya no sirve.")

    class Meta:
        verbose_name = "cuenta del portal"
        verbose_name_plural = "cuentas del portal"

    def __str__(self):
        return f"{self.usuario.username} · {self.persona.nombre}"


class AccesoExpediente(models.Model):
    """Qué expedientes ve una cuenta externa (y con qué papel)."""

    cuenta = models.ForeignKey(CuentaExterna, on_delete=models.CASCADE, related_name="accesos")
    expediente = models.ForeignKey(Expediente, on_delete=models.CASCADE, related_name="accesos_portal")
    rol = models.CharField(max_length=20, choices=RolAcceso.choices, default=RolAcceso.BENEFICIARIA)
    otorgado_en = models.DateTimeField(default=timezone.now)
    otorgado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        unique_together = [("cuenta", "expediente")]
        verbose_name = "acceso del portal a un expediente"
        verbose_name_plural = "accesos del portal a expedientes"


class CodigoConsulta(models.Model):
    """Respaldo sin cuenta: el folio del expediente y este código (impreso en el acuse) muestran solo ese expediente."""

    expediente = models.OneToOneField(Expediente, on_delete=models.CASCADE, related_name="codigo_consulta")
    codigo_hash = models.CharField(max_length=128)
    creado_en = models.DateTimeField(default=timezone.now)
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        verbose_name = "código de consulta"
        verbose_name_plural = "códigos de consulta"
