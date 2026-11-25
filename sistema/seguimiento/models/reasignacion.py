"""HU-6.1 · Lista de espera y sustituciones: las solicitudes de la persona
(sustitución, desistimiento, aviso de fallecimiento) con su acuse, y las propuestas del área responsable al Comité con el
acuerdo que las resuelve. ``Propuesta`` es común a las propuestas de M6 (HU-6.2 suma las suyas por tipo)."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from dictamen.models import Acuerdo
from nucleo.models import Acuse, Ejercicio, Expediente, Persona, Unidad


class EstadoPropuesta(models.TextChoices):
    ENVIADA = "enviada", "Enviada a la Secretaría Técnica, por llevar a sesión"
    EN_SESION = "en_sesion", "Acordada por el Comité, por cumplir"
    EJECUTADA = "ejecutada", "Acuerdo cumplido"


class Propuesta(models.Model):
    """Propuesta del área responsable al Comité (reasignación, sustitución, baja, caso especial…). La Secretaría Técnica la
    lleva a una sesión de seguimiento como acuerdo (``dictamen.Acuerdo``) y, al cumplirse el acuerdo, se ejecuta."""

    ejercicio = models.ForeignKey(Ejercicio, on_delete=models.PROTECT, related_name="propuestas_seguimiento")
    tipo = models.CharField(max_length=40, help_text="Clave de datos/seguimiento.json (propuestas.tipos).")
    expedientes = models.ManyToManyField(Expediente, related_name="propuestas_seguimiento",
                                         help_text="Expedientes a los que aplica el acuerdo.")
    descripcion = models.TextField(help_text="Texto que se propone como acuerdo.")
    fundamento = models.CharField(max_length=400, blank=True)
    monto_liberado = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    monto_asignado = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    saldo = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    datos = models.JSONField(default=dict, blank=True, help_text="Renglones de la lista de espera, resolución propuesta, persona sustituta…")
    estado = models.CharField(max_length=20, choices=EstadoPropuesta.choices, default=EstadoPropuesta.ENVIADA)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    unidad = models.ForeignKey(Unidad, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    creada_en = models.DateTimeField(default=timezone.now)
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    acuerdo = models.OneToOneField(Acuerdo, null=True, blank=True, on_delete=models.PROTECT, related_name="propuesta_seguimiento")
    aprobada = models.BooleanField(null=True, help_text="Lo que acordó el Comité (None mientras no se lleve a sesión).")
    ejecutada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creada_en", "-id"]
        verbose_name = "propuesta al Comité"
        verbose_name_plural = "propuestas al Comité"

    def __str__(self):
        return f"{self.nombre_tipo} ({self.creada_en:%d/%m/%Y})"

    @property
    def nombre_tipo(self):
        from ..reasignacion import datos_seguimiento

        return datos_seguimiento()["propuestas"]["tipos"].get(self.tipo, {}).get("nombre", self.tipo)


class MedioSolicitud(models.TextChoices):
    PORTAL = "portal", "Portal de personas beneficiarias"
    VENTANILLA = "ventanilla", "En la Delegación"


def ruta_solicitud(instancia, nombre):
    exp = instancia.expediente
    return f"seguimiento/{exp.ejercicio.anio}/{exp.folio}/solicitudes/{nombre}"


class SolicitudPersona(models.Model):
    """Solicitud de sustitución, desistimiento o aviso de fallecimiento, con su acuse (fecha y hora)."""

    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="solicitudes_seguimiento")
    tipo = models.CharField(max_length=30, help_text="Clave de datos/seguimiento.json (solicitudes.tipos).")
    nombre = models.CharField(max_length=200)
    medio = models.CharField(max_length=20, choices=MedioSolicitud.choices)
    presentada_en = models.DateTimeField(default=timezone.now)
    presentada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+",
                                       help_text="Cuenta del portal o personal de la Delegación que la recibe.")
    persona_presenta = models.CharField(max_length=250, help_text="Nombre de quien la presenta.")
    motivo = models.TextField(blank=True)
    fecha_hecho = models.DateField(null=True, blank=True, help_text="Fecha del fallecimiento.")
    segunda_persona = models.ForeignKey(Persona, null=True, blank=True, on_delete=models.PROTECT, related_name="+",
                                        help_text="Segunda persona beneficiaria que pide continuar.")
    causa = models.CharField(max_length=30, blank=True, help_text="Sustitución: fallecimiento o imposibilidad.")
    archivo = models.FileField(upload_to=ruta_solicitud, max_length=300, blank=True)
    huella = models.CharField(max_length=64, blank=True)
    firmas = models.JSONField(default=list, blank=True, help_text="Puntos de firma y sello verificados (desistimiento).")
    vence = models.DateField(null=True, blank=True)
    en_plazo = models.BooleanField(null=True)
    plazo_texto = models.CharField(max_length=300, blank=True)
    estado_al_presentar = models.CharField(max_length=40, blank=True)
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    propuesta = models.ForeignKey(Propuesta, null=True, blank=True, on_delete=models.SET_NULL, related_name="solicitudes")
    datos = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["presentada_en", "id"]
        verbose_name = "solicitud de sustitución o desistimiento"
        verbose_name_plural = "solicitudes de sustitución o desistimiento"

    def __str__(self):
        return f"{self.expediente.folio} · {self.nombre}"

    @property
    def situacion_plazo(self):
        if self.en_plazo is None:
            return ""
        return "en plazo" if self.en_plazo else "fuera de plazo"

    @property
    def nombre_archivo(self):
        return self.archivo.name.rsplit("/", 1)[-1] if self.archivo else ""


class Prorroga(models.Model):
    """MFS · prórroga por causa externa (flujo G): la solicitud con su acuse y la resolución con el adendum (o negada)."""

    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="prorrogas")
    causa = models.TextField(help_text="Motivo externo a la persona por el que no se cumplió la meta.")
    plazo_original = models.DateField(null=True, blank=True)
    plazo_solicitado = models.DateField(null=True, blank=True)
    solicitada_en = models.DateTimeField(default=timezone.now)
    solicitada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    archivo = models.FileField(upload_to=ruta_solicitud, max_length=300, blank=True)
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    estado_al_solicitar = models.CharField(max_length=40, blank=True)
    autorizada = models.BooleanField(null=True)
    resuelta_en = models.DateTimeField(null=True, blank=True)
    resuelta_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    motivo_resolucion = models.TextField(blank=True)
    adendum = models.ForeignKey("contrato.Adendum", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    acuse_resolucion = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["solicitada_en", "id"]
        verbose_name = "prórroga por causa externa"
        verbose_name_plural = "prórrogas por causa externa"

    def __str__(self):
        return f"{self.expediente.folio} · prórroga ({self.solicitada_en:%d/%m/%Y})"
