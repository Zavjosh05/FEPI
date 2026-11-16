"""Núcleo común del Sistema de programas de PROBOSQUE.

Contiene lo que comparten todos los módulos (M1 a M6):

- Catálogos: Programa, Ejercicio y sus reglas como datos (TipoPersona, Modalidad, Requisito,
  Plazo, Formato, MontoApoyo, Ministracion), Unidad, Municipio, DiaInhabil.
- Trámite: Persona, Predio, Expediente, Documento.
- Estados: Estado y Transicion (tabla de transiciones permitidas). El único punto que cambia el
  estado es ``Expediente.cambiar_estado``; valida contra la tabla y escribe la bitácora.
- Bitácora y acuses: Evento y Acuse (PDF con folio).
"""
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.gis.db import models
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from simple_history.models import HistoricalRecords


# ----------------------------------------------------------------------------- unidades y usuarios
class TipoUnidad(models.TextChoices):
    DELEGACION = "delegacion", "Delegación Regional Forestal"
    DIRECCION = "direccion", "Dirección (área responsable del programa)"
    JURIDICA = "juridica", "Unidad Jurídica"
    SECRETARIA_COMITE = "secretaria_comite", "Secretaría Técnica del Comité"
    ADMIN_FINANZAS = "admin_finanzas", "Administración y Finanzas"
    VIVERO = "vivero", "Vivero"
    FIDUCIARIA = "fiduciaria", "Fiduciaria"
    OTRA = "otra", "Otra unidad"


class Unidad(models.Model):
    """Unidad administrativa. Cada usuario pertenece a una; su tipo define su grupo de permisos."""

    clave = models.CharField(max_length=40, unique=True)
    nombre = models.CharField(max_length=200)
    tipo = models.CharField(max_length=30, choices=TipoUnidad.choices)
    sede = models.CharField(max_length=120, blank=True)
    domicilio = models.CharField(max_length=300, blank=True)
    telefono = models.CharField(max_length=40, blank=True)
    programas = models.ManyToManyField(
        "Programa", blank=True, related_name="unidades_responsables",
        help_text="Para una Dirección: programas de los que es Instancia Ejecutora.",
    )
    asignacion_confirmada = models.BooleanField(
        default=False,
        help_text="Para una Delegación: si los municipios que atiende ya los confirmó el cliente.",
    )
    fuente_asignacion = models.CharField(max_length=300, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "unidad"
        verbose_name_plural = "unidades"
        ordering = ["tipo", "nombre"]

    def __str__(self):
        return self.nombre

    @property
    def es_delegacion(self):
        return self.tipo == TipoUnidad.DELEGACION

    @property
    def es_direccion(self):
        return self.tipo == TipoUnidad.DIRECCION


class Usuario(AbstractUser):
    unidad = models.ForeignKey(Unidad, null=True, blank=True, on_delete=models.PROTECT, related_name="usuarios")
    cargo = models.CharField(max_length=120, blank=True)

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def tipo_unidad(self):
        return self.unidad.tipo if self.unidad_id else None

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.sincronizar_grupo()

    def sincronizar_grupo(self):
        """El grupo de Django del usuario es el del tipo de su unidad (un grupo por tipo de unidad)."""
        from django.contrib.auth.models import Group

        nombres = dict(TipoUnidad.choices)
        propios = self.groups.filter(name__in=nombres.values())
        deseado = nombres.get(self.tipo_unidad)
        for g in propios:
            if g.name != deseado:
                self.groups.remove(g)
        if deseado:
            grupo, _ = Group.objects.get_or_create(name=deseado)
            self.groups.add(grupo)


class Municipio(models.Model):
    clave = models.CharField(max_length=10, unique=True, help_text="Clave interna (la capa de IDEFOR no trae la clave INEGI).")
    nombre = models.CharField(max_length=120, unique=True)
    geom = models.MultiPolygonField(srid=4326)
    delegacion = models.ForeignKey(
        Unidad, null=True, blank=True, on_delete=models.PROTECT, related_name="municipios",
        limit_choices_to={"tipo": TipoUnidad.DELEGACION},
    )

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class DiaInhabil(models.Model):
    fecha = models.DateField(unique=True)
    descripcion = models.CharField(max_length=200)
    fuente = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "día inhábil"
        verbose_name_plural = "días inhábiles"
        ordering = ["fecha"]

    def __str__(self):
        return f"{self.fecha:%d/%m/%Y} {self.descripcion}"


# ----------------------------------------------------------------------------- programas y reglas
class Programa(models.Model):
    clave = models.CharField(max_length=10, unique=True)
    nombre = models.CharField(max_length=200)
    usa_poligono = models.BooleanField(default=True, help_text="Guardabosques (PEG) no usa polígono.")
    descripcion = models.TextField(blank=True)

    class Meta:
        ordering = ["clave"]

    def __str__(self):
        return f"{self.clave} · {self.nombre}"


class Ejercicio(models.Model):
    """Un programa en un año fiscal, con sus reglas (requisitos, plazos, formatos, montos)."""

    programa = models.ForeignKey(Programa, on_delete=models.PROTECT, related_name="ejercicios")
    anio = models.PositiveIntegerField()
    vigente = models.BooleanField(default=True)
    fuente = models.TextField(blank=True, help_text="Documento del que se tomaron las reglas.")
    archivo_reglas = models.CharField(max_length=200, blank=True)
    reglas_cargadas = models.DateTimeField(null=True, blank=True)
    datos = models.JSONField(default=dict, blank=True, help_text="Resto del archivo de reglas (consulta).")

    class Meta:
        unique_together = [("programa", "anio")]
        ordering = ["programa__clave", "-anio"]

    def __str__(self):
        return f"{self.programa.clave} {self.anio}"

    @property
    def tiene_reglas(self):
        return self.reglas_cargadas is not None

    def plazo(self, clave):
        return self.plazos.filter(clave=clave).first()


class TipoPersona(models.Model):
    ejercicio = models.ForeignKey(Ejercicio, on_delete=models.CASCADE, related_name="tipos_persona")
    clave = models.CharField(max_length=40)
    nombre = models.CharField(max_length=300)
    fundamento = models.CharField(max_length=200, blank=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("ejercicio", "clave")]
        ordering = ["orden"]
        verbose_name = "tipo de persona"
        verbose_name_plural = "tipos de persona"

    def __str__(self):
        return self.nombre


class Modalidad(models.Model):
    ejercicio = models.ForeignKey(Ejercicio, on_delete=models.CASCADE, related_name="modalidades")
    clave = models.CharField(max_length=40)
    nombre = models.CharField(max_length=300)
    descripcion = models.TextField(blank=True)
    fundamento = models.CharField(max_length=200, blank=True)
    seleccionable = models.BooleanField(
        default=True, help_text="Si se elige al registrar la solicitud (no lo es un régimen de pago, por ejemplo).",
    )
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("ejercicio", "clave")]
        ordering = ["orden"]
        verbose_name_plural = "modalidades"

    def __str__(self):
        return self.nombre


class Requisito(models.Model):
    ejercicio = models.ForeignKey(Ejercicio, on_delete=models.CASCADE, related_name="requisitos")
    clave = models.CharField(max_length=40)
    texto = models.TextField()
    tipos_persona = models.ManyToManyField(TipoPersona, blank=True, help_text="Vacío = todos.")
    modalidades = models.ManyToManyField(Modalidad, blank=True, help_text="Vacío = todas.")
    aplica_en_refrendo = models.BooleanField(
        null=True, blank=True,
        help_text="Sí: se pide también en refrendo. No: en refrendo vale la documentación que obra en PROBOSQUE "
                  "si está vigente. Vacío: las ROP no lo dicen (se pide).",
    )
    es_documento_legal = models.BooleanField(default=False)
    requiere_documento = models.BooleanField(
        default=True,
        help_text="No: es una condición que se revisa (por ejemplo, la nacionalidad), no un documento que se digitaliza.",
    )
    opcional = models.BooleanField(default=False)
    condicion = models.CharField(max_length=300, blank=True, help_text="Cuándo aplica, si no siempre.")
    nota_refrendo = models.CharField(max_length=300, blank=True)
    formato = models.CharField(max_length=80, blank=True)
    fundamento = models.CharField(max_length=200, blank=True)
    linea_rop = models.PositiveIntegerField(null=True, blank=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("ejercicio", "clave")]
        ordering = ["orden"]

    def __str__(self):
        return f"{self.clave} {self.texto[:60]}"

    @property
    def es_condicional(self):
        """Puede marcarse «no aplica» en la revisión (opcional o con condición)."""
        return self.opcional or bool(self.condicion)

    @property
    def titulo(self):
        """Primera frase del texto, para listas."""
        texto = self.texto.split(":")[0] if len(self.texto.split(":")[0]) < 140 else self.texto
        return texto if len(texto) <= 160 else texto[:157] + "…"


class UnidadPlazo(models.TextChoices):
    DIAS_HABILES = "dias_habiles", "días hábiles"
    DIAS_NATURALES = "dias_naturales", "días naturales"
    MESES = "meses", "meses"
    ANIOS = "anios", "años"
    FECHA_LIMITE = "fecha_limite", "fecha límite"
    OTRO = "otro", "otro (ver descripción)"


class Plazo(models.Model):
    ejercicio = models.ForeignKey(Ejercicio, on_delete=models.CASCADE, related_name="plazos")
    clave = models.CharField(max_length=60)
    descripcion = models.TextField()
    cantidad = models.PositiveIntegerField(null=True, blank=True)
    unidad = models.CharField(max_length=60, help_text="dias_habiles, dias_naturales, meses, anios, fecha_limite u otra.")
    fecha_fin = models.DateField(null=True, blank=True)
    corre_desde = models.CharField(max_length=300, blank=True)
    responsable = models.CharField(max_length=200, blank=True)
    fundamento = models.CharField(max_length=200, blank=True)
    linea_rop = models.PositiveIntegerField(null=True, blank=True)
    datos = models.JSONField(default=dict, blank=True, help_text="Campos adicionales del archivo de reglas.")

    class Meta:
        unique_together = [("ejercicio", "clave")]
        ordering = ["clave"]

    def __str__(self):
        return f"{self.clave}: {self.texto_plazo}"

    @property
    def es_calculable(self):
        return self.cantidad is not None and self.unidad in {
            UnidadPlazo.DIAS_HABILES, UnidadPlazo.DIAS_NATURALES, UnidadPlazo.MESES, UnidadPlazo.ANIOS,
        }

    @property
    def texto_plazo(self):
        if self.cantidad is None:
            return dict(UnidadPlazo.choices).get(self.unidad, self.unidad.replace("_", " "))
        return f"{self.cantidad} {dict(UnidadPlazo.choices).get(self.unidad, self.unidad.replace('_', ' '))}"


class Formato(models.Model):
    ejercicio = models.ForeignKey(Ejercicio, on_delete=models.CASCADE, related_name="formatos")
    clave = models.CharField(max_length=40, blank=True)
    nombre = models.CharField(max_length=300)
    uso = models.TextField(blank=True)
    linea_rop = models.PositiveIntegerField(null=True, blank=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["orden"]

    def __str__(self):
        return f"{self.clave or 's/c'} {self.nombre[:60]}"


class MontoApoyo(models.Model):
    """Monto de un concepto de apoyo. Modalidad vacía = vale para todas las modalidades del ejercicio.
    El cálculo del monto de un expediente está en ``nucleo.montos``."""

    ejercicio = models.ForeignKey(Ejercicio, on_delete=models.CASCADE, related_name="montos")
    concepto = models.TextField()
    monto = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    unidad = models.CharField(max_length=120, blank=True)
    modalidad = models.ForeignKey(Modalidad, null=True, blank=True, on_delete=models.SET_NULL)
    fundamento = models.CharField(max_length=200, blank=True)
    datos = models.JSONField(default=dict, blank=True,
                             help_text="Campos adicionales del archivo de reglas (requiere, superficie mínima…).")

    class Meta:
        verbose_name = "monto de apoyo"
        verbose_name_plural = "montos de apoyo"


class Ministracion(models.Model):
    """Porcentaje de cada ministración por régimen (sprint 2)."""

    ejercicio = models.ForeignKey(Ejercicio, on_delete=models.CASCADE, related_name="ministraciones")
    numero = models.PositiveIntegerField()
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2)
    regimen = models.CharField(max_length=60, blank=True)
    condicion = models.TextField(blank=True)
    fundamento = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "ministración (regla)"
        verbose_name_plural = "ministraciones (reglas)"
        ordering = ["regimen", "numero"]


# ----------------------------------------------------------------------------- estados y transiciones
class Estado(models.Model):
    """Estado del trámite.

    ``tipo_unidad_bandeja``: tipos de unidad (separados por coma) que lo atienden, o sea, en cuya bandeja
    aparece. ``visible_para``: otros tipos de unidad que pueden consultar el expediente en ese estado.
    """

    clave = models.CharField(max_length=40, unique=True)
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)
    tipo_unidad_bandeja = models.CharField(max_length=200, blank=True,
                                           help_text="Tipos de unidad separados por coma (delegacion, direccion…).")
    visible_para = models.CharField(max_length=200, blank=True,
                                    help_text="Otros tipos de unidad que consultan el expediente en este estado.")
    flujo_alterno = models.CharField(max_length=2, blank=True, help_text="A, B, … si es parte de un flujo alterno.")
    final = models.BooleanField(default=False)
    color = models.CharField(max_length=20, default="secondary", help_text="Clase de color de Bootstrap.")
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["orden"]

    def __str__(self):
        return self.nombre

    @property
    def tipos_bandeja(self):
        return [t.strip() for t in self.tipo_unidad_bandeja.split(",") if t.strip()]


class Transicion(models.Model):
    """Transición permitida. Programa vacío = vale para todos los programas."""

    programa = models.ForeignKey(Programa, null=True, blank=True, on_delete=models.CASCADE)
    origen = models.ForeignKey(Estado, on_delete=models.CASCADE, related_name="salidas")
    destino = models.ForeignKey(Estado, on_delete=models.CASCADE, related_name="entradas")
    tipo_unidad = models.CharField(max_length=30, choices=TipoUnidad.choices)
    accion = models.CharField(max_length=120, help_text="Nombre de la acción en pantalla.")
    requiere_motivo = models.BooleanField(default=False)

    class Meta:
        verbose_name = "transición"
        verbose_name_plural = "transiciones"
        unique_together = [("programa", "origen", "destino", "tipo_unidad")]

    def __str__(self):
        return f"{self.origen.clave} → {self.destino.clave} ({self.get_tipo_unidad_display()})"


class TransicionNoPermitida(PermissionDenied):
    pass


# ----------------------------------------------------------------------------- trámite
class TipoPersonaGeneral(models.TextChoices):
    FISICA = "fisica", "Persona física"
    JURIDICA_COLECTIVA = "juridica_colectiva", "Persona jurídico colectiva"
    NUCLEO_AGRARIO = "nucleo_agrario", "Núcleo agrario"
    PRESTADOR = "prestador", "Prestador de servicios forestales"


class Persona(models.Model):
    """Persona solicitante o beneficiaria, núcleo agrario, Guardabosque o prestador (RFN)."""

    tipo = models.CharField(max_length=30, choices=TipoPersonaGeneral.choices)
    nombre = models.CharField(max_length=250, help_text="Nombre completo o razón social / nombre del núcleo agrario.")
    curp = models.CharField("CURP", max_length=18, blank=True)
    rfc = models.CharField("RFC", max_length=13, blank=True)
    rfn = models.CharField("RFN", max_length=40, blank=True, help_text="Registro Forestal Nacional (prestador).")
    representante = models.CharField(max_length=250, blank=True)
    telefono = models.CharField(max_length=40, blank=True)
    correo = models.EmailField(blank=True)
    domicilio = models.CharField(max_length=300, blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Consecutivo(models.Model):
    """Contador para folios (se incrementa con bloqueo de fila)."""

    clave = models.CharField(max_length=60, unique=True)
    ultimo = models.PositiveIntegerField(default=0)

    @classmethod
    def siguiente(cls, clave):
        with transaction.atomic():
            fila, _ = cls.objects.select_for_update().get_or_create(clave=clave)
            fila.ultimo += 1
            fila.save(update_fields=["ultimo"])
            return fila.ultimo


class Predio(models.Model):
    """Predio: el expediente único cuelga de aquí (todas sus solicitudes en todos los programas)."""

    folio = models.CharField(max_length=30, unique=True, editable=False,
                             help_text="Folio del expediente del predio; se conserva entre programas (ROP CC 8.1.1.2 fr. XVII).")
    nombre = models.CharField(max_length=200)
    municipio = models.ForeignKey(Municipio, on_delete=models.PROTECT, related_name="predios")
    localidad = models.CharField(max_length=200, blank=True)
    titular = models.ForeignKey(Persona, on_delete=models.PROTECT, related_name="predios")
    superficie_declarada_ha = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["folio"]

    def __str__(self):
        return f"{self.folio} · {self.nombre}"

    def save(self, *args, **kwargs):
        if not self.folio:
            self.folio = f"PRED-{Consecutivo.siguiente('predio'):06d}"
        super().save(*args, **kwargs)


class Expediente(models.Model):
    """Solicitud de un predio a un programa-ejercicio. Todo el trámite cuelga de aquí."""

    folio = models.CharField(max_length=40, unique=True, editable=False)
    ejercicio = models.ForeignKey(Ejercicio, on_delete=models.PROTECT, related_name="expedientes")
    predio = models.ForeignKey(Predio, on_delete=models.PROTECT, related_name="expedientes")
    solicitante = models.ForeignKey(Persona, on_delete=models.PROTECT, related_name="solicitudes")
    tipo_persona = models.ForeignKey(TipoPersona, on_delete=models.PROTECT)
    modalidad = models.ForeignKey(Modalidad, null=True, blank=True, on_delete=models.PROTECT)
    es_refrendo = models.BooleanField(default=False)
    con_representante_legal = models.BooleanField(default=False)
    superficie_solicitada_ha = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    delegacion = models.ForeignKey(Unidad, on_delete=models.PROTECT, related_name="expedientes",
                                   limit_choices_to={"tipo": TipoUnidad.DELEGACION})
    estado = models.ForeignKey(Estado, on_delete=models.PROTECT, related_name="expedientes")
    fecha_recepcion = models.DateTimeField()
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    enviado_direccion = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(blank=True)
    actualizado = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-fecha_recepcion"]

    def __str__(self):
        return self.folio

    @property
    def programa(self):
        return self.ejercicio.programa

    def save(self, *args, **kwargs):
        if not self.folio:
            prog = self.ejercicio.programa.clave
            n = Consecutivo.siguiente(f"expediente-{prog}-{self.ejercicio.anio}")
            self.folio = f"{prog}-{self.ejercicio.anio}-{self.delegacion.clave[:3]}-{n:04d}"
        super().save(*args, **kwargs)

    # --- estados -------------------------------------------------------------------------------
    def transiciones_posibles(self, usuario):
        """Transiciones que ``usuario`` puede hacer desde el estado actual."""
        if not puede_ver_expediente(usuario, self):
            return Transicion.objects.none()
        return (
            Transicion.objects.filter(origen=self.estado, tipo_unidad=usuario.tipo_unidad)
            .filter(models.Q(programa__isnull=True) | models.Q(programa=self.programa))
            .select_related("destino")
        )

    def cambiar_estado(self, destino, usuario, motivo="", tipo_evento="cambio_estado", descripcion="",
                       acuse=None, datos=None, por_sistema=False):
        """Único punto que cambia el estado: valida la transición y escribe la bitácora.

        ``destino`` puede ser la clave o el objeto Estado. Lanza ``TransicionNoPermitida``.
        ``por_sistema=True`` (sin usuario) es para lo que hace solo el sistema, como el señalamiento de un contrato
        sin firma en plazo: exige que exista la transición en la tabla (de cualquier unidad) y queda en la bitácora
        sin persona.
        """
        if isinstance(destino, str):
            destino = Estado.objects.get(clave=destino)
        with transaction.atomic():
            actual = Expediente.objects.select_for_update().get(pk=self.pk)
            if por_sistema and usuario is None:
                transicion = (Transicion.objects.filter(origen=actual.estado, destino=destino)
                              .filter(models.Q(programa__isnull=True) | models.Q(programa=actual.programa)).first())
                if transicion is None:
                    raise TransicionNoPermitida(f"No existe la transición de «{actual.estado}» a «{destino}».")
            else:
                if not puede_ver_expediente(usuario, actual):
                    raise TransicionNoPermitida("El expediente no pertenece a su unidad.")
                transicion = actual.transiciones_posibles(usuario).filter(destino=destino).first()
                if transicion is None:
                    raise TransicionNoPermitida(
                        f"No se permite pasar de «{actual.estado}» a «{destino}» desde "
                        f"{usuario.unidad or 'un usuario sin unidad'}."
                    )
            if transicion.requiere_motivo and not motivo.strip():
                raise ValidationError("Esta acción requiere un motivo.")
            origen = actual.estado
            self.estado = destino
            if destino.clave == "enviada_direccion":
                self.enviado_direccion = timezone.now()
            self._change_reason = transicion.accion
            self.save()
            Evento.registrar(
                self, usuario, tipo_evento, descripcion or transicion.accion,
                estado_origen=origen, estado_destino=destino, motivo=motivo, acuse=acuse, datos=datos,
            )
        return transicion


class TipoDocumento(models.TextChoices):
    REQUISITO = "requisito", "Requisito"
    ACUSE = "acuse", "Acuse"
    POLIGONO = "poligono", "Archivo del polígono"
    OTRO = "otro", "Otro"


def ruta_documento(instancia, nombre):
    exp = instancia.expediente
    return f"expedientes/{exp.ejercicio.anio}/{exp.folio}/{nombre}"


class Documento(models.Model):
    expediente = models.ForeignKey(Expediente, on_delete=models.CASCADE, related_name="documentos")
    tipo = models.CharField(max_length=20, choices=TipoDocumento.choices, default=TipoDocumento.REQUISITO)
    requisito = models.ForeignKey(Requisito, null=True, blank=True, on_delete=models.PROTECT)
    nombre = models.CharField(max_length=250)
    archivo = models.FileField(upload_to=ruta_documento, max_length=300)
    fecha_entrega = models.DateTimeField(default=timezone.now)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    unidad = models.ForeignKey(Unidad, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    history = HistoricalRecords()

    class Meta:
        ordering = ["-fecha_entrega"]

    def __str__(self):
        return self.nombre


class Acuse(models.Model):
    """Acuse en PDF de un envío o entrega, con folio, fecha y hora."""

    folio = models.CharField(max_length=30, unique=True, editable=False)
    expediente = models.ForeignKey(Expediente, null=True, blank=True, on_delete=models.CASCADE, related_name="acuses",
                                   help_text="Vacío en los acuses de una sesión del Comité (varios expedientes).")
    referencia = models.CharField(max_length=120, blank=True, help_text="Sesión u otro objeto al que se refiere.")
    tipo = models.CharField(max_length=40)
    titulo = models.CharField(max_length=200)
    fecha_hora = models.DateTimeField(default=timezone.now)
    emitido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    unidad = models.ForeignKey(Unidad, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    destinatario = models.CharField(max_length=250, blank=True)
    contenido = models.JSONField(default=dict)
    archivo = models.FileField(upload_to="acuses/%Y/", max_length=300, blank=True)
    huella = models.CharField(max_length=64, blank=True, help_text="SHA-256 del PDF.")

    class Meta:
        ordering = ["-fecha_hora"]

    def __str__(self):
        return f"{self.folio} {self.titulo}"

    def save(self, *args, **kwargs):
        if not self.folio:
            anio = timezone.localtime(self.fecha_hora).year
            self.folio = f"AC-{anio}-{Consecutivo.siguiente(f'acuse-{anio}'):06d}"
        super().save(*args, **kwargs)


class Evento(models.Model):
    """Bitácora del expediente: quién, qué, fecha y hora."""

    expediente = models.ForeignKey(Expediente, on_delete=models.CASCADE, related_name="eventos")
    fecha_hora = models.DateTimeField(default=timezone.now)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")
    unidad = models.ForeignKey(Unidad, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    tipo = models.CharField(max_length=40)
    descripcion = models.TextField()
    estado_origen = models.ForeignKey(Estado, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    estado_destino = models.ForeignKey(Estado, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    motivo = models.TextField(blank=True)
    acuse = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="eventos")
    datos = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-fecha_hora", "-id"]
        verbose_name = "evento de bitácora"
        verbose_name_plural = "bitácora"

    def __str__(self):
        return f"{self.fecha_hora:%Y-%m-%d %H:%M} {self.tipo}"

    @classmethod
    def registrar(cls, expediente, usuario, tipo, descripcion, **campos):
        return cls.objects.create(
            expediente=expediente, usuario=usuario,
            unidad=getattr(usuario, "unidad", None) if usuario else None,
            tipo=tipo, descripcion=descripcion,
            **{k: (v if v is not None else ({} if k == "datos" else None)) for k, v in campos.items()},
        )


# ----------------------------------------------------------------------------- notificaciones
class TipoNotificacion(models.TextChoices):
    """Qué se notifica a la persona. Los módulos usan estas claves; agregar aquí las nuevas."""

    FALTANTES = "faltantes", "Aviso de faltantes"
    RESULTADOS = "resultados", "Resultados (persona beneficiaria)"
    CITA_FIRMA = "cita_firma", "Cita a firma del contrato"
    OMISION = "omision", "Omisión o incumplimiento"
    DEVOLUCION = "devolucion", "Devolución o reintegro"
    PAGO = "pago", "Aviso de pago (ministración)"
    OTRO = "otro", "Otra notificación"


class MedioNotificacion(models.TextChoices):
    PERSONAL = "personal", "En persona, en la Delegación o en el predio"
    CORREO = "correo", "Correo electrónico"
    TELEFONO = "telefono", "Teléfono"
    ESTRADOS = "estrados", "Estrados o publicación"
    OTRO = "otro", "Otro medio"


class Notificacion(models.Model):
    """Notificación a la persona solicitante o beneficiaria por conducto de la Delegación.

    Tiene dos momentos, cada uno con su fecha, hora y acuse: el **envío** (la unidad que emite el
    aviso lo manda a la Delegación) y la **notificación** a la persona (la Delegación la registra con
    el medio usado). Los módulos guardan una referencia a la suya (por ejemplo,
    ``recepcion.Validacion.notificacion``); los plazos que corren «desde la notificación» la leen aquí.
    """

    expediente = models.ForeignKey(Expediente, on_delete=models.CASCADE, related_name="notificaciones")
    tipo = models.CharField(max_length=30, choices=TipoNotificacion.choices)
    asunto = models.CharField(max_length=250)
    destinatario = models.ForeignKey(Persona, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    enviada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    unidad_origen = models.ForeignKey(Unidad, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    delegacion = models.ForeignKey(Unidad, on_delete=models.PROTECT, related_name="notificaciones",
                                   limit_choices_to={"tipo": TipoUnidad.DELEGACION},
                                   help_text="Delegación por cuyo conducto se notifica.")
    enviada_en = models.DateTimeField(default=timezone.now)
    acuse_envio = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notificada_en = models.DateTimeField(null=True, blank=True, help_text="Fecha y hora en que se notificó a la persona.")
    notificada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                       related_name="+")
    medio = models.CharField(max_length=20, choices=MedioNotificacion.choices, blank=True)
    acuse_notificacion = models.ForeignKey(Acuse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    observaciones = models.TextField(blank=True)
    datos = models.JSONField(default=dict, blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-enviada_en", "-id"]
        verbose_name = "notificación"
        verbose_name_plural = "notificaciones"

    def __str__(self):
        return f"{self.expediente.folio} · {self.get_tipo_display()} ({'notificada' if self.notificada_en else 'por notificar'})"

    @property
    def notificada(self):
        return self.notificada_en is not None


# ----------------------------------------------------------------------------- hitos del trámite
class Hito(models.Model):
    """Evento fechado del trámite que puede arrancar un plazo (publicación de resultados, firma del
    contrato, entrega del Vale o del cheque…). Lo registra cada módulo con ``nucleo.plazos.registrar_hito``;
    el servicio de plazos lo lee sin conocer al módulo."""

    expediente = models.ForeignKey(Expediente, on_delete=models.CASCADE, related_name="hitos")
    clave = models.CharField(max_length=60)
    fecha_hora = models.DateTimeField()
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                related_name="+")
    referencia = models.CharField(max_length=120, blank=True)
    datos = models.JSONField(default=dict, blank=True)
    registrado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_hora", "-id"]
        verbose_name = "hito del trámite"
        verbose_name_plural = "hitos del trámite"

    def __str__(self):
        return f"{self.expediente.folio} · {self.clave} {self.fecha_hora:%Y-%m-%d}"


# ----------------------------------------------------------------------------- permisos por unidad
def expedientes_visibles(usuario):
    """Expedientes que ve el usuario: una Delegación solo los suyos; una Dirección los de sus programas."""
    qs = Expediente.objects.select_related(
        "ejercicio__programa", "predio__municipio", "solicitante", "estado", "delegacion", "tipo_persona",
    )
    if not usuario.is_authenticated:
        return qs.none()
    if usuario.is_superuser:
        return qs
    unidad = usuario.unidad
    if unidad is None:
        return qs.none()
    if unidad.tipo == TipoUnidad.DELEGACION:
        return qs.filter(delegacion=unidad)
    if unidad.tipo == TipoUnidad.DIRECCION:
        return qs.filter(ejercicio__programa__in=unidad.programas.all())
    # Las demás unidades ven los estados que atienden o que pueden consultar (datos del flujo).
    return qs.filter(_q_tipo("estado__tipo_unidad_bandeja", unidad.tipo) | _q_tipo("estado__visible_para", unidad.tipo))


def _q_tipo(campo, tipo):
    """El campo (lista separada por comas) contiene el tipo de unidad."""
    return models.Q(**{f"{campo}__regex": rf"(^|,)\s*{tipo}\s*(,|$)"})


def puede_ver_expediente(usuario, expediente):
    return expedientes_visibles(usuario).filter(pk=expediente.pk).exists()


def bandeja(usuario):
    """Expedientes cuyo estado le toca atender a la unidad del usuario."""
    if usuario.is_superuser and not usuario.unidad_id:
        return expedientes_visibles(usuario).filter(estado__final=False)
    if not usuario.unidad_id:
        return Expediente.objects.none()
    from .extensiones import EXTRAS_BANDEJA, FILTROS_BANDEJA

    condicion = _q_tipo("estado__tipo_unidad_bandeja", usuario.unidad.tipo)
    for extra in EXTRAS_BANDEJA:
        q = extra(usuario)
        if q is not None:
            condicion |= q
    qs = expedientes_visibles(usuario).filter(condicion)
    for filtro in FILTROS_BANDEJA:
        qs = filtro(usuario, qs)
    return qs
