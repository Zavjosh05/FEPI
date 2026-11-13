from django import forms
from django.utils import timezone

from nucleo.models import Ejercicio, Modalidad, Municipio, Predio, TipoPersona, TipoPersonaGeneral

from .models import EstadoRevision, LevantadoPor


class Bs:
    """Agrega las clases de Bootstrap a los campos."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            w = campo.widget
            if isinstance(w, (forms.CheckboxInput, forms.RadioSelect)):
                w.attrs.setdefault("class", "form-check-input")
            elif isinstance(w, forms.Select):
                w.attrs.setdefault("class", "form-select")
            else:
                w.attrs.setdefault("class", "form-control")


class RegistroSolicitudForm(Bs, forms.Form):
    ejercicio = forms.ModelChoiceField(
        label="Programa y ejercicio", queryset=Ejercicio.objects.none(), empty_label=None,
        help_text="Solo aparecen los programas con reglas cargadas.",
    )
    tipo_persona = forms.ModelChoiceField(label="Tipo de persona", queryset=TipoPersona.objects.none())
    modalidad = forms.ModelChoiceField(label="Modalidad (tipo de superficie)", queryset=Modalidad.objects.none(),
                                       required=False)
    es_refrendo = forms.BooleanField(label="Es refrendo (persona beneficiaria del ejercicio anterior)", required=False)
    con_representante_legal = forms.BooleanField(label="Se solicita por medio de representante legal", required=False)
    folio_predio = forms.CharField(label="Folio de predio ya registrado (opcional)", required=False, max_length=30,
                                   help_text="Si el predio ya tiene expediente en PROBOSQUE, conserva su folio.")
    municipio = forms.ModelChoiceField(label="Municipio del predio", queryset=Municipio.objects.select_related("delegacion"))
    nombre_predio = forms.CharField(label="Nombre del predio", max_length=200, required=False)
    localidad = forms.CharField(label="Localidad o paraje", max_length=200, required=False)
    superficie_solicitada_ha = forms.DecimalField(label="Superficie solicitada (ha)", max_digits=10, decimal_places=4,
                                                  required=False, min_value=0)
    solicitante_nombre = forms.CharField(label="Nombre de la persona solicitante o razón social", max_length=250,
                                         required=False)
    curp = forms.CharField(label="CURP", max_length=18, required=False)
    rfc = forms.CharField(label="RFC", max_length=13, required=False)
    representante = forms.CharField(label="Representante legal o comisariado", max_length=250, required=False)
    telefono = forms.CharField(label="Teléfono", max_length=40, required=False)
    correo = forms.EmailField(label="Correo electrónico", required=False)
    observaciones = forms.CharField(label="Observaciones de la ventanilla", required=False,
                                    widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ejercicios = Ejercicio.objects.filter(vigente=True, reglas_cargadas__isnull=False).select_related("programa")
        self.fields["ejercicio"].queryset = ejercicios
        self.fields["ejercicio"].label_from_instance = lambda e: f"{e.programa.nombre} {e.anio}"
        ejercicio = None
        valor = self.data.get("ejercicio") if self.is_bound else self.initial.get("ejercicio")
        if valor:
            ejercicio = ejercicios.filter(pk=getattr(valor, "pk", valor)).first()
        ejercicio = ejercicio or ejercicios.first()
        if ejercicio:
            self.fields["ejercicio"].initial = ejercicio.pk
            self.fields["tipo_persona"].queryset = ejercicio.tipos_persona.all()
            self.fields["modalidad"].queryset = ejercicio.modalidades.filter(seleccionable=True)
        self.fields["municipio"].label_from_instance = lambda m: (
            f"{m.nombre} — {m.delegacion.nombre.replace('Delegación Regional Forestal', 'DRF')}" if m.delegacion
            else m.nombre)
        self.fields["ejercicio"].widget.attrs.update({"hx-get": "", "hx-target": "#formulario-registro",
                                                      "hx-select": "#formulario-registro", "hx-swap": "outerHTML",
                                                      "hx-include": "closest form"})

    def clean(self):
        datos = super().clean()
        folio = datos.get("folio_predio", "").strip()
        if folio:
            predio = Predio.objects.filter(folio__iexact=folio).first()
            if predio is None:
                self.add_error("folio_predio", "No existe un predio con ese folio.")
            datos["predio_existente"] = predio
        else:
            datos["predio_existente"] = None
            if not datos.get("nombre_predio"):
                self.add_error("nombre_predio", "Escriba el nombre del predio.")
            if not datos.get("solicitante_nombre"):
                self.add_error("solicitante_nombre", "Escriba el nombre de la persona solicitante.")
        ej, tp = datos.get("ejercicio"), datos.get("tipo_persona")
        if ej and tp and tp.ejercicio_id != ej.pk:
            self.add_error("tipo_persona", "El tipo de persona no corresponde al programa.")
        if ej and ej.modalidades.filter(seleccionable=True).exists() and not datos.get("modalidad"):
            self.add_error("modalidad", "Elija la modalidad.")
        return datos

    @staticmethod
    def tipo_general(tipo_persona):
        claves = {c for c, _ in TipoPersonaGeneral.choices}
        return tipo_persona.clave if tipo_persona.clave in claves else TipoPersonaGeneral.JURIDICA_COLECTIVA


class RevisionForm(forms.Form):
    estado = forms.ChoiceField(choices=[c for c in EstadoRevision.choices if c[0] != EstadoRevision.PENDIENTE])
    archivo = forms.FileField(required=False)
    en_archivo_probosque = forms.BooleanField(required=False)
    fecha_documento = forms.DateField(required=False)
    observaciones = forms.CharField(required=False, max_length=500)


class PoligonoForm(Bs, forms.Form):
    archivo = forms.FileField(label="Archivo del polígono (GeoJSON, KML o Shapefile en .zip)", required=False)
    dibujo = forms.CharField(required=False, widget=forms.HiddenInput)
    levantado_por = forms.ChoiceField(label="Levantado en campo por", choices=LevantadoPor.choices)
    responsable = forms.CharField(label="Nombre de quien lo levantó", max_length=200)
    prestador_rfn = forms.CharField(label="RFN del prestador de servicios forestales", max_length=40, required=False)
    fecha_levantamiento = forms.DateField(label="Fecha del levantamiento", initial=timezone.localdate,
                                          widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    motivo_cambio = forms.CharField(label="Motivo del cambio (si ya había polígono)", max_length=500, required=False)

    def clean(self):
        datos = super().clean()
        if not datos.get("archivo") and not datos.get("dibujo"):
            raise forms.ValidationError("Cargue un archivo o dibuje el polígono en el mapa.")
        if datos.get("levantado_por") == LevantadoPor.PRESTADOR and not datos.get("prestador_rfn"):
            self.add_error("prestador_rfn", "Indique el RFN del prestador de servicios forestales.")
        return datos
