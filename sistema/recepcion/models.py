"""Módulo M1 · Recepción y expediente.

- RevisionRequisito (HU-1.2): cada requisito aplicable queda entregado, faltante o no aplica.
- Poligono (HU-1.3): polígono levantado en campo; los anteriores se conservan (historial).
- Validacion (HU-1.4): validación de la Dirección o aviso de faltantes con fecha límite.
- ObservacionValidacion (HU-1.4): resultado y observación de la Dirección sobre cada requisito al validar (qué falta o
  por qué no es válido); el aviso de faltantes las lleva una por una.
"""
from django.conf import settings
from django.contrib.gis.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from nucleo.models import Acuse, Documento, Expediente, Notificacion, Persona, Requisito


class EstadoRevision(models.TextChoices):
    PENDIENTE = "pendiente", "Sin revisar"
    ENTREGADO = "entregado", "Entregado"
    FALTANTE = "faltante", "Faltante"
    NO_APLICA = "no_aplica", "No aplica"


class RevisionRequisito(models.Model):
    expediente = models.ForeignKey(Expediente, on_delete=models.CASCADE, related_name="revisiones")
    requisito = models.ForeignKey(Requisito, on_delete=models.PROTECT, related_name="revisiones")
    estado = models.CharField(max_length=20, choices=EstadoRevision.choices, default=EstadoRevision.PENDIENTE)
    documento = models.ForeignKey(Documento, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    en_archivo_probosque = models.BooleanField(
        default=False, help_text="Refrendo: la documentación obra en los archivos de PROBOSQUE (no se vuelve a pedir).",
    )
    fecha_documento = models.DateField(
        null=True, blank=True, help_text="Fecha de la documentación que obra en PROBOSQUE (para su vigencia).",
    )
    observaciones = models.CharField(max_length=500, blank=True)
    revisado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name="+")
    revisado_en = models.DateTimeField(null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        unique_together = [("expediente", "requisito")]
        ordering = ["requisito__orden"]
        verbose_name = "revisión de requisito"
        verbose_name_plural = "revisiones de requisitos"

    def __str__(self):
        return f"{self.expediente.folio} · {self.requisito.clave}: {self.get_estado_display()}"

    @property
    def tiene_archivo(self):
        return self.documento_id is not None

    @property
    def observacion_direccion(self):
        """Última observación de la Dirección sobre este requisito en un aviso de faltantes (HU-1.4), o None."""
        return (self.observaciones_direccion.filter(faltante=True, validacion__resultado="faltantes")
                .select_related("validacion").order_by("-validacion__fecha_hora", "-id").first())


class LevantadoPor(models.TextChoices):
    DELEGACION = "delegacion", "Personal de la Delegación"
    PRESTADOR = "prestador", "Prestador de servicios forestales"


class OrigenPoligono(models.TextChoices):
    GEOJSON = "geojson", "Archivo GeoJSON"
    KML = "kml", "Archivo KML"
    SHP = "shp", "Shapefile (zip)"
    DIBUJO = "dibujo", "Dibujado en el mapa"


class TipoCambio(models.TextChoices):
    INICIAL = "inicial", "Primer polígono"
    CORRECCION = "correccion", "Corrección en el mismo lugar"
    CAMBIO_LUGAR = "cambio_lugar", "Cambio de lugar"


class UbicacionMunicipio(models.TextChoices):
    DENTRO = "dentro", "Dentro del municipio"
    PARCIAL = "parcial", "Parte fuera del municipio"
    FUERA = "fuera", "Fuera del municipio"


def ruta_poligono(instancia, nombre):
    exp = instancia.expediente
    return f"expedientes/{exp.ejercicio.anio}/{exp.folio}/poligonos/{nombre}"


class Poligono(models.Model):
    expediente = models.ForeignKey(Expediente, on_delete=models.CASCADE, related_name="poligonos")
    geom = models.MultiPolygonField(srid=4326)
    superficie_ha = models.DecimalField(max_digits=12, decimal_places=4, help_text="Calculada en EPSG:32614.")
    levantado_por = models.CharField(max_length=20, choices=LevantadoPor.choices)
    prestador = models.ForeignKey(Persona, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    responsable = models.CharField(max_length=200, help_text="Nombre de quien levantó el polígono en campo.")
    fecha_levantamiento = models.DateField()
    origen = models.CharField(max_length=20, choices=OrigenPoligono.choices)
    archivo = models.FileField(upload_to=ruta_poligono, blank=True, max_length=300)
    vigente = models.BooleanField(default=True)
    anterior = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="posteriores")
    tipo_cambio = models.CharField(max_length=20, choices=TipoCambio.choices, default=TipoCambio.INICIAL)
    traslape_anterior_pct = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    ubicacion_municipio = models.CharField(max_length=10, choices=UbicacionMunicipio.choices)
    aviso = models.CharField(max_length=500, blank=True)
    motivo_cambio = models.CharField(max_length=500, blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    registrado_en = models.DateTimeField(default=timezone.now)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-registrado_en", "-id"]
        verbose_name = "polígono"
        verbose_name_plural = "polígonos"

    def __str__(self):
        return f"{self.expediente.folio} · {self.superficie_ha} ha ({'vigente' if self.vigente else 'anterior'})"


class ResultadoValidacion(models.TextChoices):
    VALIDADO = "validado", "Expediente validado"
    FALTANTES = "faltantes", "Aviso de faltantes"


class Validacion(models.Model):
    expediente = models.ForeignKey(Expediente, on_delete=models.CASCADE, related_name="validaciones")
    resultado = models.CharField(max_length=20, choices=ResultadoValidacion.choices)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    fecha_hora = models.DateTimeField(default=timezone.now)
    observaciones = models.TextField(blank=True)
    faltantes = models.ManyToManyField(RevisionRequisito, blank=True, related_name="avisos")
    detalle = models.JSONField(default=list, blank=True, help_text="Copia de lo revisado al momento de validar.")
    fecha_limite = models.DateField(null=True, blank=True)
    plazo_aplicado = models.CharField(max_length=300, blank=True)
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notificado_en = models.DateTimeField(null=True, blank=True, help_text="Notificación por conducto de la Delegación.")
    notificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                       related_name="+")
    acuse_notificacion = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notificacion = models.OneToOneField(
        Notificacion, null=True, blank=True, on_delete=models.SET_NULL, related_name="validacion",
        help_text="Aviso de faltantes: su notificación por conducto de la Delegación (núcleo).",
    )
    vencimiento_avisado = models.BooleanField(default=False)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-fecha_hora", "-id"]
        verbose_name = "validación"
        verbose_name_plural = "validaciones"

    def __str__(self):
        return f"{self.expediente.folio} · {self.get_resultado_display()}"


class OrigenObservacion(models.TextChoices):
    REGLAS = "reglas", "Revisión con las reglas"
    DIRECCION = "direccion", "Señalado por la Dirección"


class ObservacionValidacion(models.Model):
    """HU-1.4 · Lo que la Dirección dictó sobre cada requisito en una validación: válido o faltante, y su observación."""

    validacion = models.ForeignKey(Validacion, on_delete=models.CASCADE, related_name="observaciones_requisitos")
    revision = models.ForeignKey(RevisionRequisito, on_delete=models.PROTECT, related_name="observaciones_direccion")
    faltante = models.BooleanField(default=False)
    origen = models.CharField(max_length=20, choices=OrigenObservacion.choices, blank=True,
                              help_text="Quién lo marcó como faltante: la revisión con las reglas o la Dirección.")
    observacion = models.TextField(help_text="Qué falta o por qué no es válido; en los válidos, la nota de la revisión.")
    history = HistoricalRecords()

    class Meta:
        ordering = ["revision__requisito__orden", "id"]
        verbose_name = "observación de la validación"
        verbose_name_plural = "observaciones de la validación"

    def __str__(self):
        return f"{self.revision.requisito.clave}: {'Faltante' if self.faltante else 'Válido'} · {self.observacion[:60]}"
