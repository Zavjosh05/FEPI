"""HU-4.1 · Envío de comprobaciones: avisos, informes, bitácoras, solicitudes de auditoría, reportes mensuales y acuses de
depósito que la persona beneficiaria (o el Guardabosque) envía desde el portal o entrega en la Delegación. Es el mismo
registro en los dos medios: fecha y hora, acuse, quién lo envió y, en ventanilla, quién lo recibió."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from nucleo.models import Acuse, Expediente


class MedioEnvio(models.TextChoices):
    PORTAL = "portal", "Portal de personas beneficiarias"
    VENTANILLA = "ventanilla", "En persona, en la Delegación"


def ruta_comprobacion(instancia, nombre):
    exp = instancia.expediente
    return f"ejecucion/{exp.ejercicio.anio}/{exp.folio}/{nombre}"


class Comprobacion(models.Model):
    """Un envío o una entrega de la persona: el tipo (``datos/ejecucion.json`` → ``tipos_envio``) con el fundamento de las
    ROP, el medio, la fecha y la hora, su acuse y, si el tipo tiene plazo, si llegó en plazo (se registra igual si no)."""

    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="comprobaciones")
    tipo = models.CharField(max_length=40, help_text="Clave de datos/ejecucion.json (tipos_envio).")
    nombre = models.CharField(max_length=200, help_text="Nombre del tipo al registrarse.")
    fundamento = models.CharField(max_length=400, blank=True)
    medio = models.CharField(max_length=15, choices=MedioEnvio.choices)
    enviada_en = models.DateTimeField(default=timezone.now, help_text="Fecha y hora del envío o de la entrega.")
    enviada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+",
                                    help_text="Quien la registró: la cuenta del portal o el personal de la Delegación.")
    persona_entrega = models.CharField(max_length=250, blank=True, help_text="Quién la entregó (en ventanilla).")
    recibida_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name="+", help_text="Personal de la Delegación que la recibió (ventanilla).")
    descripcion = models.TextField(blank=True)
    fecha_hecho = models.DateField(null=True, blank=True, help_text="Término de las actividades, siniestro o depósito.")
    periodo = models.CharField(max_length=20, blank=True, help_text="PEG: periodo que reporta (clave de periodos_reportes).")
    archivo = models.FileField(upload_to=ruta_comprobacion, max_length=300, blank=True)
    huella = models.CharField(max_length=64, blank=True, help_text="SHA-256 del archivo.")
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    plazo_uso = models.CharField(max_length=60, blank=True)
    vence = models.DateField(null=True, blank=True)
    en_plazo = models.BooleanField(null=True, help_text="None: el tipo no tiene plazo o las reglas no dan fecha.")
    plazo_texto = models.CharField(max_length=300, blank=True)
    estado_al_enviar = models.CharField(max_length=40, blank=True)
    cambio_estado = models.CharField(max_length=40, blank=True, help_text="Estado al que pasó el expediente (si cambió).")
    revisada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name="+", help_text="La Delegación revisó lo recibido por el portal.")
    revisada_en = models.DateTimeField(null=True, blank=True)
    datos = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-enviada_en", "-id"]
        verbose_name = "comprobación"
        verbose_name_plural = "comprobaciones"

    def __str__(self):
        return f"{self.expediente.folio} · {self.nombre} ({self.enviada_en:%d/%m/%Y})"

    @property
    def por_portal(self):
        return self.medio == MedioEnvio.PORTAL

    @property
    def nombre_archivo(self):
        return self.archivo.name.rsplit("/", 1)[-1] if self.archivo else ""

    @property
    def nombre_cambio_estado(self):
        from nucleo.models import Estado

        return Estado.objects.filter(clave=self.cambio_estado).values_list("nombre", flat=True).first() or self.cambio_estado

    @property
    def situacion_plazo(self):
        if self.en_plazo is None:
            return "sin plazo que calificar"
        return "en plazo" if self.en_plazo else "fuera de plazo"
