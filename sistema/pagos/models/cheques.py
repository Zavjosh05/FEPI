"""HU-5.3 · Entrega de cheques (PSAHEM): el cheque de cada ministración que emite la Fiduciaria, su envío a la Delegación, su
entrega a la persona beneficiaria y su cobro en un máximo de 3 meses (ROP PSAHEM 8.1.7 fr. XVI, líneas 2069 y 2070)."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from nucleo.models import Acuse, Expediente, Notificacion, Persona, Unidad

from .pagos import RemisionFiduciaria
from .solicitudes import SolicitudPago


class Cheque(models.Model):
    """Cheque de una ministración de una persona beneficiaria: uno por solicitud (o sea, por persona y ministración)."""

    solicitud = models.OneToOneField(SolicitudPago, on_delete=models.PROTECT, related_name="cheque")
    remision = models.OneToOneField(RemisionFiduciaria, on_delete=models.PROTECT, related_name="cheque")
    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="cheques")
    persona = models.ForeignKey(Persona, on_delete=models.PROTECT, related_name="cheques",
                                help_text="Persona beneficiaria a cuyo nombre se emite.")
    ministracion = models.PositiveIntegerField()
    numero = models.CharField(max_length=40, unique=True, help_text="Número de cheque.")
    importe = models.DecimalField(max_digits=14, decimal_places=2)
    # emisión (Fiduciaria)
    emitido_en = models.DateField(help_text="Fecha de emisión del cheque.")
    emitido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    registrado_en = models.DateTimeField(default=timezone.now)
    acuse_emision = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    # envío a la Delegación (Fiduciaria)
    delegacion = models.ForeignKey(Unidad, on_delete=models.PROTECT, related_name="cheques_recibidos",
                                   help_text="Delegación que lo entrega a la persona.")
    enviado_en = models.DateTimeField(null=True, blank=True, help_text="Fecha y hora del envío a la Delegación.")
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                    related_name="+")
    acuse_envio = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    aviso = models.ForeignKey(Notificacion, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                              help_text="Aviso de que el pago está listo, por conducto de la Delegación.")
    # entrega a la persona (Delegación)
    entregado_en = models.DateTimeField(null=True, blank=True, help_text="Fecha y hora de la entrega a la persona.")
    entregado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                      related_name="+")
    recibe_nombre = models.CharField(max_length=250, blank=True, help_text="Quién recibe: la persona o su representante.")
    acuse_entrega = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    # cobro en 3 meses desde la entrega (R-14)
    vence_cobro = models.DateField(null=True, blank=True)
    cobrado_en = models.DateField(null=True, blank=True)
    cobro_registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                             related_name="+")
    aviso_cobro = models.CharField(max_length=15, blank=True, help_text="Último aviso de revisar_plazos: por_vencer o vencido.")

    class Meta:
        ordering = ["-registrado_en", "-id"]
        verbose_name = "cheque de PSAHEM"
        verbose_name_plural = "cheques de PSAHEM"

    def __str__(self):
        return f"Cheque {self.numero} · {self.expediente.folio}/M{self.ministracion}"

    @property
    def enviado(self):
        return self.enviado_en is not None

    @property
    def entregado(self):
        return self.entregado_en is not None

    @property
    def cobrado(self):
        return self.cobrado_en is not None

    @property
    def situacion(self):
        if self.cobrado:
            return "Cobrado"
        if self.entregado:
            return "Entregado, por cobrar"
        if self.enviado:
            return "En la Delegación, por entregar"
        return "Emitido, por enviar"
