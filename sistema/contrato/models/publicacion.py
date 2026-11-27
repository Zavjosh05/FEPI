"""HU-3.1 · Publicación de resultados: qué se publicó, cuándo, con qué acuse y en qué lugar quedó cada solicitud.

Los avisos y notificaciones a la persona **no** tienen modelo propio: son ``nucleo.Notificacion``
(``nucleo.notificaciones``). Aquí solo está lo que el núcleo no conoce: la publicación de los listados que el
Comité autorizó en su acta y el renglón publicado de cada solicitud (la copia que consulta la página pública).
"""
from django.conf import settings
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from dictamen.models import ResultadoListado, SesionComite
from nucleo.models import Acuse, Ejercicio, Expediente


class Publicacion(models.Model):
    """Los listados de una sesión de aprobación publicados por el área responsable del programa."""

    sesion = models.OneToOneField(SesionComite, on_delete=models.PROTECT, related_name="publicacion")
    ejercicio = models.ForeignKey(Ejercicio, on_delete=models.PROTECT, related_name="publicaciones")
    publicada_en = models.DateTimeField(default=timezone.now, help_text="Fecha y hora de la publicación.")
    publicada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    lugares = models.CharField(max_length=300, blank=True,
                               help_text="Dónde se publicó (página de PROBOSQUE, Oficinas Centrales, Delegaciones…).")
    fecha_limite = models.DateField(null=True, blank=True,
                                    help_text="Fecha que marca la convocatoria del programa, si las reglas la traen.")
    dentro_de_fecha = models.BooleanField(null=True, blank=True,
                                          help_text="Vacío cuando las reglas no traen fecha para publicar.")
    fundamento_fecha = models.CharField(max_length=300, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-publicada_en"]
        verbose_name = "publicación de resultados"
        verbose_name_plural = "publicaciones de resultados"

    def __str__(self):
        return f"Publicación {self.sesion.numero} ({self.publicada_en:%d/%m/%Y})"

    @property
    def situacion_fecha(self):
        """Texto de si se publicó dentro de la fecha de la convocatoria (R-05: sin fecha no se inventa una)."""
        if self.dentro_de_fecha is None:
            return "Sin fecha en las reglas: las ROP no fijan fecha ni días para publicar (R-05)."
        limite = f"{self.fecha_limite:%d/%m/%Y}"
        return (f"Dentro de la fecha de la convocatoria ({limite})." if self.dentro_de_fecha
                else f"Fuera de la fecha de la convocatoria ({limite}).")


class ResultadoPublicado(models.Model):
    """Renglón publicado de una solicitud. El nombre de la persona se guarda **solo** en el listado de
    personas beneficiarias (el padrón que las ROP mandan publicar); en los demás queda vacío."""

    publicacion = models.ForeignKey(Publicacion, on_delete=models.CASCADE, related_name="renglones")
    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="resultados_publicados")
    resultado = models.CharField(max_length=20, choices=ResultadoListado.choices)
    orden = models.PositiveIntegerField(null=True, blank=True)
    folio = models.CharField(max_length=40)
    predio = models.CharField(max_length=250)
    municipio = models.CharField(max_length=120)
    persona = models.CharField(max_length=250, blank=True)

    history = HistoricalRecords()

    class Meta:
        unique_together = [("publicacion", "expediente")]
        ordering = ["resultado", "orden", "folio"]

    def __str__(self):
        return f"{self.folio}: {self.get_resultado_display()}"
