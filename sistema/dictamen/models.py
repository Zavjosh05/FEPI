"""Módulo M2 · Dictamen y Comité (modelos compartidos por las cuatro historias).

- HU-2.1: DictamenTecnico.
- HU-2.2: DictamenJuridico, PersonaIncumplida (Listado de Personas Beneficiarias Incumplidas) y
  PredioSancionado (predios con procedimiento o sanción).
- HU-2.3: SesionComite (tipo aprobación), DocumentoSesion y ResolucionSesion (listados del acta).
- HU-2.4: SesionComite (tipo seguimiento) y Acuerdo.
"""
from django.conf import settings
from django.contrib.gis.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from nucleo.models import Acuse, Ejercicio, Expediente, Municipio, Persona, Predio, Unidad


# ----------------------------------------------------------------------------- HU-2.1
class ResultadoTecnico(models.TextChoices):
    FACTIBLE = "factible", "Factible"
    NO_FACTIBLE = "no_factible", "No factible"


class DictamenTecnico(models.Model):
    expediente = models.OneToOneField(Expediente, on_delete=models.CASCADE, related_name="dictamen_tecnico")
    resultado = models.CharField(max_length=20, choices=ResultadoTecnico.choices)
    motivo = models.TextField()
    superficie_factible_ha = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    verificacion = models.JSONField(default=list, help_text="Lista de verificación con los criterios del programa.")
    analisis = models.JSONField(default=dict, help_text="Análisis cartográfico al momento de dictaminar.")
    fecha_limite = models.DateField(null=True, blank=True, help_text="Vencimiento del plazo de dictaminación.")
    dentro_de_plazo = models.BooleanField(null=True, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    fecha_hora = models.DateTimeField(default=timezone.now)
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "dictamen técnico"
        verbose_name_plural = "dictámenes técnicos"

    def __str__(self):
        return f"{self.expediente.folio} · {self.get_resultado_display()}"


# ----------------------------------------------------------------------------- HU-2.2
class ResultadoJuridico(models.TextChoices):
    PROCEDENTE = "procedente", "Procedente"
    NO_PROCEDENTE = "no_procedente", "No procedente"


class DictamenJuridico(models.Model):
    expediente = models.OneToOneField(Expediente, on_delete=models.CASCADE, related_name="dictamen_juridico")
    resultado = models.CharField(max_length=20, choices=ResultadoJuridico.choices)
    motivo = models.TextField()
    cotejo = models.JSONField(default=list, help_text="Coincidencias con el Listado y los predios sancionados.")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    fecha_hora = models.DateTimeField(default=timezone.now)
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "dictamen jurídico"
        verbose_name_plural = "dictámenes jurídicos"

    def __str__(self):
        return f"{self.expediente.folio} · {self.get_resultado_display()}"


class PersonaIncumplida(models.Model):
    """Registro del Listado de Personas Beneficiarias Incumplidas de PROBOSQUE."""

    nombre = models.CharField(max_length=250)
    curp = models.CharField("CURP", max_length=18, blank=True)
    rfc = models.CharField("RFC", max_length=13, blank=True)
    persona = models.ForeignKey(Persona, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    programa = models.CharField(max_length=120, blank=True, help_text="Programa y ejercicio del incumplimiento.")
    motivo = models.TextField()
    acuerdo = models.CharField(max_length=200, blank=True, help_text="Acuerdo del Comité que ordenó la inscripción.")
    fecha_inscripcion = models.DateField(default=timezone.localdate)
    activa = models.BooleanField(default=True, help_text="Desactivar (no borrar) si se da de baja del Listado.")
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")
    history = HistoricalRecords()

    class Meta:
        ordering = ["nombre"]
        verbose_name = "persona en el Listado de Incumplidas"
        verbose_name_plural = "Listado de Personas Beneficiarias Incumplidas"

    def __str__(self):
        return self.nombre


class TipoSancion(models.TextChoices):
    PROCEDIMIENTO = "procedimiento", "Procedimiento administrativo en curso"
    SANCION = "sancion", "Sanción administrativa"


class PredioSancionado(models.Model):
    """Predio con procedimiento administrativo o sanción por la normatividad forestal."""

    predio = models.ForeignKey(Predio, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    descripcion_predio = models.CharField(max_length=250, help_text="Nombre o ubicación del predio.")
    municipio = models.ForeignKey(Municipio, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    tipo = models.CharField(max_length=20, choices=TipoSancion.choices)
    descripcion = models.TextField()
    autoridad = models.CharField(max_length=200, blank=True)
    fecha = models.DateField(default=timezone.localdate)
    reintegro_realizado = models.BooleanField(default=False,
                                              help_text="Con el reintegro hecho deja de impedir el apoyo (CC 8.1.1.1 fr. III).")
    activo = models.BooleanField(default=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")
    history = HistoricalRecords()

    class Meta:
        ordering = ["descripcion_predio"]
        verbose_name = "predio con procedimiento o sanción"
        verbose_name_plural = "predios con procedimiento o sanción"

    def __str__(self):
        return self.descripcion_predio


# ----------------------------------------------------------------------------- HU-2.3 y HU-2.4
class TipoSesion(models.TextChoices):
    APROBACION = "aprobacion", "Sesión de aprobación"
    SEGUIMIENTO = "seguimiento", "Sesión de seguimiento"


class CaracterSesion(models.TextChoices):
    ORDINARIA = "ordinaria", "Ordinaria"
    EXTRAORDINARIA = "extraordinaria", "Extraordinaria"


class EstadoSesion(models.TextChoices):
    PREPARACION = "preparacion", "En preparación"
    CONVOCADA = "convocada", "Convocada"
    CELEBRADA = "celebrada", "Celebrada (acta registrada)"


class SesionComite(models.Model):
    ejercicio = models.ForeignKey(Ejercicio, on_delete=models.PROTECT, related_name="sesiones")
    tipo = models.CharField(max_length=20, choices=TipoSesion.choices)
    caracter = models.CharField(max_length=20, choices=CaracterSesion.choices, default=CaracterSesion.ORDINARIA)
    numero = models.CharField(max_length=60, help_text="Número o clave de la sesión.")
    fecha_hora = models.DateTimeField(help_text="Fecha y hora de celebración.")
    lugar = models.CharField(max_length=250, help_text="Lugar o plataforma digital.")
    orden_del_dia = models.TextField(help_text="Un punto por renglón.")
    integrantes = models.JSONField(default=dict, blank=True)
    estado = models.CharField(max_length=20, choices=EstadoSesion.choices, default=EstadoSesion.PREPARACION)
    presupuesto = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True,
                                      help_text="Recurso disponible para la propuesta de listados.")
    convocatoria_enviada = models.DateTimeField(null=True, blank=True)
    acuse_convocatoria = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    acta_fecha = models.DateTimeField(null=True, blank=True)
    autoriza_publicacion = models.BooleanField(default=False)
    observaciones_acta = models.TextField(blank=True)
    acuse_acta = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    history = HistoricalRecords()

    class Meta:
        ordering = ["-fecha_hora"]
        verbose_name = "sesión del Comité"
        verbose_name_plural = "sesiones del Comité"

    def __str__(self):
        return f"{self.numero} ({self.get_tipo_display().lower()})"

    @property
    def puntos(self):
        return [p.strip() for p in self.orden_del_dia.splitlines() if p.strip()]


def ruta_documento_sesion(instancia, nombre):
    return f"sesiones/{instancia.sesion.ejercicio.anio}/{instancia.sesion.pk}/{nombre}"


class DocumentoSesion(models.Model):
    sesion = models.ForeignKey(SesionComite, on_delete=models.CASCADE, related_name="documentos")
    nombre = models.CharField(max_length=250)
    archivo = models.FileField(upload_to=ruta_documento_sesion, max_length=300)
    fecha_hora = models.DateTimeField(default=timezone.now)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["fecha_hora"]

    def __str__(self):
        return self.nombre


class ResultadoListado(models.TextChoices):
    BENEFICIARIA = "beneficiaria", "Lista de Personas Beneficiarias"
    LISTA_ESPERA = "lista_espera", "Lista de espera"
    NO_FACTIBLE = "no_factible", "Lista de solicitudes No factibles"


class ResolucionSesion(models.Model):
    """Lugar de cada expediente en los listados de una sesión de aprobación."""

    sesion = models.ForeignKey(SesionComite, on_delete=models.CASCADE, related_name="resoluciones")
    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="resoluciones_comite")
    resultado = models.CharField(max_length=20, choices=ResultadoListado.choices)
    resultado_propuesto = models.CharField(max_length=20, choices=ResultadoListado.choices)
    orden = models.PositiveIntegerField(null=True, blank=True)
    orden_propuesto = models.PositiveIntegerField(null=True, blank=True)
    monto = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    criterios = models.JSONField(default=list, blank=True, help_text="Criterios de priorización que cumple.")
    motivo_ajuste = models.TextField(blank=True, help_text="Constancia del Comité si cambió la propuesta.")
    history = HistoricalRecords()

    class Meta:
        unique_together = [("sesion", "expediente")]
        ordering = ["resultado", "orden"]

    def __str__(self):
        return f"{self.sesion.numero} · {self.expediente.folio}: {self.get_resultado_display()}"

    @property
    def ajustada(self):
        """Solo la resolución que el Comité cambió (lleva constancia); las que apenas se recorren de lugar no."""
        return bool(self.motivo_ajuste)


class EstadoAcuerdo(models.TextChoices):
    PENDIENTE = "pendiente", "Pendiente"
    CUMPLIDO = "cumplido", "Cumplido"


class Acuerdo(models.Model):
    sesion = models.ForeignKey(SesionComite, on_delete=models.PROTECT, related_name="acuerdos")
    numero = models.CharField(max_length=80)
    tipo = models.CharField(max_length=40, help_text="Clave del tipo de acuerdo (datos/dictamen.json).")
    descripcion = models.TextField()
    expedientes = models.ManyToManyField(Expediente, related_name="acuerdos_comite")
    unidad_responsable = models.ForeignKey(Unidad, on_delete=models.PROTECT, related_name="acuerdos_pendientes")
    ministracion = models.PositiveIntegerField(null=True, blank=True, help_text="PSAHEM: número de ministración.")
    periodo = models.CharField(max_length=40, blank=True, help_text="PEG: periodo de reportes evaluado.")
    estado = models.CharField(max_length=20, choices=EstadoAcuerdo.choices, default=EstadoAcuerdo.PENDIENTE)
    cumplido_en = models.DateTimeField(null=True, blank=True)
    cumplido_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name="+")
    observaciones_cumplimiento = models.TextField(blank=True)
    registrado = models.DateTimeField(default=timezone.now)
    history = HistoricalRecords()

    class Meta:
        ordering = ["sesion", "numero"]

    def __str__(self):
        return f"{self.numero} {self.descripcion[:50]}"
