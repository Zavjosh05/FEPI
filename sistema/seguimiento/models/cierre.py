"""HU-6.3 · Cierre del ejercicio: el cierre de cada expediente con sus resultados finales, la publicación del padrón de personas
beneficiarias y el informe anual al Comité con su envío y su recepción."""
from django.conf import settings
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from nucleo.models import Acuse, Ejercicio, Expediente


class CierreExpediente(models.Model):
    """El expediente quedó cerrado con lo aprobado, verificado, pagado y reintegrado que se ve en ``resumen`` (copia al cerrar)."""

    expediente = models.OneToOneField(Expediente, on_delete=models.PROTECT, related_name="cierre")
    tipo = models.CharField(max_length=20, help_text="Clave de datos/seguimiento.json (cierre.cierre_expediente.tipos).")
    resumen = models.JSONField(default=dict, blank=True, help_text="Aprobado, verificado, pagado, reintegrado y liberado al cerrar.")
    motivo = models.TextField(blank=True)
    cerrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    cerrado_en = models.DateTimeField(default=timezone.now)
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    history = HistoricalRecords()

    class Meta:
        ordering = ["-cerrado_en", "-id"]
        verbose_name = "cierre de expediente"
        verbose_name_plural = "cierres de expedientes"

    def __str__(self):
        return f"{self.expediente.folio} · cierre"


class PadronPublicacion(models.Model):
    """El área responsable publica el padrón del programa y ejercicio; desde entonces la página pública lo muestra y se actualiza
    sola con las bajas, cancelaciones y sustituciones de los expedientes."""

    ejercicio = models.OneToOneField(Ejercicio, on_delete=models.PROTECT, related_name="padron_publicacion")
    publicada_en = models.DateTimeField(default=timezone.now)
    publicada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    fundamento = models.CharField(max_length=300, blank=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "publicación del padrón"
        verbose_name_plural = "publicaciones del padrón"

    def __str__(self):
        return f"Padrón {self.ejercicio}"


def ruta_informe(instancia, nombre):
    return f"seguimiento/{instancia.ejercicio.anio}/{instancia.ejercicio.programa.clave}/informe/{nombre}"


class InformeAnual(models.Model):
    """Informe anual de la ejecución del programa al Comité: el PDF con los resultados finales y las diferencias, la fecha y la
    hora de su envío (con su acuse) y su recepción en la sesión del Comité."""

    ejercicio = models.OneToOneField(Ejercicio, on_delete=models.PROTECT, related_name="informe_anual")
    resumen = models.JSONField(default=dict, blank=True, help_text="Totales y diferencias al enviar.")
    archivo = models.FileField(upload_to=ruta_informe, max_length=300)
    huella = models.CharField(max_length=64, blank=True)
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    enviado_en = models.DateTimeField(default=timezone.now, help_text="Fecha y hora del envío al Comité.")
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    sesion = models.ForeignKey("dictamen.SesionComite", null=True, blank=True, on_delete=models.SET_NULL, related_name="informes_anuales")
    recibido_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    recibido_en = models.DateTimeField(null=True, blank=True)
    acuse_recepcion = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    observaciones = models.TextField(blank=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "informe anual al Comité"
        verbose_name_plural = "informes anuales al Comité"

    def __str__(self):
        return f"Informe anual {self.ejercicio}"
