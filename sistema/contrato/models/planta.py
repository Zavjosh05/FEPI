"""HU-3.4 · Entrega de planta (solo PS y RHF): catálogos de especies y viveros, Vale de Planta con sus renglones por
especie y la salida de planta del vivero."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from nucleo.models import Acuse, Expediente, Unidad


class Especie(models.Model):
    """Especie de planta forestal que producen los viveros (catálogo sencillo)."""

    nombre = models.CharField(max_length=120, unique=True, help_text="Nombre común.")
    nombre_cientifico = models.CharField(max_length=160, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "especie de planta"
        verbose_name_plural = "especies de planta"

    def __str__(self):
        return self.nombre if not self.nombre_cientifico else f"{self.nombre} ({self.nombre_cientifico})"


class Vivero(models.Model):
    """Vivero forestal de PROBOSQUE. Su personal es el de la ``unidad`` (tipo vivero), si ya tiene usuarios."""

    clave = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=200)
    unidad = models.OneToOneField(Unidad, null=True, blank=True, on_delete=models.SET_NULL, related_name="vivero",
                                  help_text="Unidad (tipo vivero) cuyo personal registra las salidas de planta.")
    municipio = models.CharField(max_length=120, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


def ruta_vale(instancia, nombre):
    exp = instancia.expediente
    return f"vales/{exp.ejercicio.anio}/{exp.folio}/{nombre}"


class ValePlanta(models.Model):
    """Vale de Planta que emite la Delegación a un expediente con derecho a planta (PS y RHF)."""

    folio = models.CharField(max_length=40, unique=True, editable=False)
    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="vales")
    vivero = models.ForeignKey(Vivero, on_delete=models.PROTECT, related_name="vales")
    entregado_en = models.DateTimeField(default=timezone.now, help_text="Fecha y hora de la entrega del vale.")
    entregado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    vence_el = models.DateField(null=True, blank=True, help_text="Último día de vigencia (plazo de las reglas).")
    vigencia_texto = models.CharField(max_length=300, blank=True)
    anticipado = models.BooleanField(default=False, help_text="Entregado antes de la firma del contrato (carta compromiso).")
    carta_compromiso = models.FileField(upload_to=ruta_vale, max_length=300, blank=True)
    propuesta_total = models.PositiveIntegerField(null=True, blank=True, help_text="Piezas que proponía el sistema.")
    motivo_ajuste = models.TextField(blank=True, help_text="Por qué la cantidad difiere de la propuesta.")
    repone = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reposiciones",
                               help_text="Vale vencido al que repone (solo cubre lo no entregado).")
    planta_disponible = models.BooleanField(default=True, help_text="En reposición: el vivero confirmó disponibilidad.")
    archivo = models.FileField(upload_to=ruta_vale, max_length=300, blank=True, help_text="PDF del vale con su vigencia.")
    huella = models.CharField(max_length=64, blank=True)
    completado_en = models.DateTimeField(null=True, blank=True, help_text="Fecha y hora de la última salida que lo completó.")

    class Meta:
        ordering = ["-entregado_en", "-id"]
        verbose_name = "Vale de Planta"
        verbose_name_plural = "Vales de Planta"

    def __str__(self):
        return self.folio

    # ------------------------------------------------------------------ situación del vale
    @property
    def repuesto(self):
        return self.reposiciones.exists()

    @property
    def surtido(self):
        return self.completado_en is not None

    def vencido(self, hoy=None):
        hoy = hoy or timezone.localdate()
        return self.vence_el is not None and hoy > self.vence_el and not self.surtido

    def situacion(self, hoy=None):
        """«surtido», «repuesto», «vencido» o «vigente»."""
        if self.surtido:
            return "surtido"
        if self.repuesto:
            return "repuesto"
        return "vencido" if self.vencido(hoy) else "vigente"

    def vigente(self, hoy=None):
        return self.situacion(hoy) == "vigente"

    @property
    def total_autorizado(self):
        return sum(r.cantidad for r in self.renglones.all())

    @property
    def total_entregado(self):
        return sum(r.entregada for r in self.renglones.all())

    @property
    def total_pendiente(self):
        return self.total_autorizado - self.total_entregado


class RenglonVale(models.Model):
    """Especie y cantidad autorizadas en un vale."""

    vale = models.ForeignKey(ValePlanta, on_delete=models.CASCADE, related_name="renglones")
    especie = models.ForeignKey(Especie, on_delete=models.PROTECT, related_name="+")
    cantidad = models.PositiveIntegerField(help_text="Piezas autorizadas.")

    class Meta:
        ordering = ["id"]
        unique_together = [("vale", "especie")]

    def __str__(self):
        return f"{self.especie.nombre}: {self.cantidad}"

    @property
    def entregada(self):
        return sum(s.cantidad for s in self.salidas.all())

    @property
    def pendiente(self):
        return self.cantidad - self.entregada


class SalidaPlanta(models.Model):
    """Salida de planta del vivero contra un vale: especie, cantidad, fecha y hora, con acuse."""

    renglon = models.ForeignKey(RenglonVale, on_delete=models.PROTECT, related_name="salidas")
    vale = models.ForeignKey(ValePlanta, on_delete=models.PROTECT, related_name="salidas")
    cantidad = models.PositiveIntegerField()
    salido_en = models.DateTimeField(default=timezone.now, help_text="Fecha y hora de la salida de planta.")
    registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    registrada_en = models.DateTimeField(default=timezone.now)
    observaciones = models.TextField(blank=True)
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["salido_en", "id"]
        verbose_name = "salida de planta"
        verbose_name_plural = "salidas de planta"

    def __str__(self):
        return f"{self.vale.folio}: {self.renglon.especie.nombre} × {self.cantidad}"

    @property
    def especie(self):
        return self.renglon.especie
