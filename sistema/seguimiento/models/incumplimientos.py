"""HU-6.2 · Incumplimientos y reintegros: el aviso de omisión con su plazo, lo que el sistema señala para que una persona lo
confirme (P-08), la cuenta para reintegros que registra Administración y Finanzas y el requerimiento de devolución con su monto,
su cuenta y la comprobación del depósito."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from dictamen.models import Acuerdo
from nucleo.models import Acuse, Expediente, Notificacion, Programa

from .reasignacion import Propuesta


class CuentaReintegro(models.Model):
    """Cuenta bancaria en la que se depositan los reintegros de un programa (la registra Administración y Finanzas)."""

    programa = models.ForeignKey(Programa, on_delete=models.PROTECT, related_name="cuentas_reintegro")
    titular = models.CharField(max_length=200)
    banco = models.CharField(max_length=120)
    cuenta = models.CharField(max_length=40, help_text="Número de cuenta o CLABE.")
    referencia = models.CharField(max_length=120, blank=True, help_text="Referencia o convenio para identificar el depósito.")
    nota = models.TextField(blank=True)
    vigente = models.BooleanField(default=True)
    registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    registrada_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["programa", "-registrada_en"]
        verbose_name = "cuenta para reintegros"
        verbose_name_plural = "cuentas para reintegros"

    def __str__(self):
        return f"{self.programa.clave} · {self.titular} · {self.banco} {self.cuenta}"

    @property
    def texto(self):
        return f"{self.titular}, {self.banco}, cuenta {self.cuenta}" + (f", referencia {self.referencia}" if self.referencia else "")


class AvisoOmision(models.Model):
    """Aviso de las omisiones por subsanar, con la fecha límite que fija el área responsable, notificado por la Delegación."""

    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="avisos_omision")
    omisiones = models.TextField()
    causa = models.CharField(max_length=300, blank=True, help_text="Causa de incumplimiento de las reglas (numeral).")
    vence = models.DateField(help_text="Fecha límite para subsanar (la fija el área: las reglas no dan días).")
    plazo_texto = models.CharField(max_length=400, blank=True)
    incidencia = models.ForeignKey("ejecucion.Incidencia", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    estado_al_avisar = models.CharField(max_length=40, blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(default=timezone.now)
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notificacion = models.ForeignKey(Notificacion, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    subsanada_en = models.DateTimeField(null=True, blank=True)
    subsanada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    motivo_subsanacion = models.TextField(blank=True)

    class Meta:
        ordering = ["-creado_en", "-id"]
        verbose_name = "aviso de omisión"
        verbose_name_plural = "avisos de omisión"

    def __str__(self):
        return f"{self.expediente.folio} · omisión (vence {self.vence:%d/%m/%Y})"

    def situacion(self, hoy=None):
        if self.subsanada_en:
            return "subsanada"
        return "vencida" if (hoy or timezone.localdate()) > self.vence else "en plazo"


class Senalamiento(models.Model):
    """Lo que el sistema señala y prepara (omisión vencida, cheque vencido, reportes incumplidos, faltantes vencidos, incidencia)
    para que una persona lo confirme con un clic (P-08: nada se ejecuta solo)."""

    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="senalamientos")
    tipo = models.CharField(max_length=30, help_text="Clave de datos/seguimiento.json (incumplimientos.senalamientos).")
    clave = models.CharField(max_length=80, help_text="Evita repetir el mismo señalamiento (aviso, cheque, periodo…).")
    descripcion = models.TextField()
    fundamento = models.CharField(max_length=400, blank=True)
    datos = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(default=timezone.now)
    atendido_en = models.DateTimeField(null=True, blank=True)
    atendido_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    resultado = models.CharField(max_length=300, blank=True)
    propuesta = models.ForeignKey(Propuesta, null=True, blank=True, on_delete=models.SET_NULL, related_name="senalamientos")

    class Meta:
        ordering = ["creado_en", "id"]
        constraints = [models.UniqueConstraint(fields=["expediente", "tipo", "clave"], name="un_senalamiento_por_situacion")]
        verbose_name = "señalamiento"
        verbose_name_plural = "señalamientos"

    def __str__(self):
        return f"{self.expediente.folio} · {self.tipo}"

    @property
    def config(self):
        from ..incumplimientos import datos_incumplimientos

        return datos_incumplimientos()["senalamientos"].get(self.tipo, {})


def ruta_deposito(instancia, nombre):
    exp = instancia.expediente
    return f"seguimiento/{exp.ejercicio.anio}/{exp.folio}/reintegro/{nombre}"


class EstadoRequerimiento(models.TextChoices):
    POR_EMITIR = "por_emitir", "Por emitir (Unidad Jurídica)"
    EMITIDO = "emitido", "Emitido y notificado: por depositar"
    DEPOSITADO = "depositado", "Depósito comprobado"
    SIN_MONTO = "sin_monto", "Sin recurso por devolver"


class Requerimiento(models.Model):
    """Requerimiento de devolución de un apoyo cancelado: monto (lo ministrado o lo ministrado de más, más el valor de la planta
    no establecida donde las reglas lo piden), la cuenta para el depósito y la comprobación del depósito."""

    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="requerimientos")
    propuesta = models.ForeignKey(Propuesta, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    acuerdo = models.ForeignKey(Acuerdo, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    motivo = models.CharField(max_length=300)
    base = models.CharField(max_length=20, default="ministrado")
    monto_ministrado = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    monto_base = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    plantas_no_establecidas = models.PositiveIntegerField(default=0)
    precio_planta = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fuente_precio = models.CharField(max_length=250, blank=True)
    monto_planta = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    monto_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cuenta = models.ForeignKey(CuentaReintegro, null=True, blank=True, on_delete=models.PROTECT, related_name="requerimientos")
    estado = models.CharField(max_length=20, choices=EstadoRequerimiento.choices, default=EstadoRequerimiento.POR_EMITIR)
    preparado_en = models.DateTimeField(default=timezone.now)
    emitido_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    emitido_en = models.DateTimeField(null=True, blank=True)
    plazo_texto = models.CharField(max_length=400, blank=True)
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notificacion = models.ForeignKey(Notificacion, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    deposito_fecha = models.DateField(null=True, blank=True)
    deposito_importe = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    deposito_referencia = models.CharField(max_length=120, blank=True)
    deposito_archivo = models.FileField(upload_to=ruta_deposito, max_length=300, blank=True)
    deposito_huella = models.CharField(max_length=64, blank=True)
    comprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    comprobado_en = models.DateTimeField(null=True, blank=True)
    acuse_deposito = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-preparado_en", "-id"]
        verbose_name = "requerimiento de devolución"
        verbose_name_plural = "requerimientos de devolución"

    def __str__(self):
        return f"{self.expediente.folio} · requerimiento {self.monto_total}"
