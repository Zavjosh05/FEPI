"""HU-2.2 · Formularios del dictamen jurídico y de los catálogos de incumplimiento."""
from django import forms

from nucleo.models import Municipio

from ..models import PersonaIncumplida, PredioSancionado, ResultadoJuridico
from .base import Bs


SI_NO = [("si", "Sí"), ("no", "No")]


class DictamenJuridicoForm(Bs, forms.Form):
    # Propiedad o legal posesión del predio (CC 8.1.1.2 fr. VII)
    tipo_documento = forms.ChoiceField(label="Documento con el que se acredita la propiedad o legal posesión")
    numero_documento = forms.CharField(label="Número del documento (escritura, certificado, inscripción…)", required=False,
                                       max_length=120)
    fecha_documento = forms.DateField(label="Fecha del documento", required=False,
                                      widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    titular_documento = forms.CharField(label="A nombre de", max_length=250)
    titular_coincide = forms.ChoiceField(label="¿Está a nombre del titular de la solicitud?", choices=SI_NO,
                                         widget=forms.RadioSelect)
    superficie_documento_ha = forms.DecimalField(label="Superficie que ampara el documento (ha)", required=False,
                                                 min_value=0, decimal_places=4, max_digits=12)
    vigente_hasta = forms.DateField(label="Vigente hasta (constancia de posesión, usufructo o arrendamiento)",
                                    required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    sin_conflicto = forms.ChoiceField(label="¿Hay evidencia de conflicto de propiedad, posesión o representación?",
                                      choices=[("si", "No hay evidencia"), ("no", "Sí hay evidencia (inelegible)")],
                                      widget=forms.RadioSelect)
    observaciones_propiedad = forms.CharField(label="Observaciones sobre la propiedad", required=False,
                                              widget=forms.Textarea(attrs={"rows": 2}))
    # Resultado
    resultado = forms.ChoiceField(label="Resultado del dictamen jurídico", choices=ResultadoJuridico.choices,
                                  widget=forms.RadioSelect)
    motivo = forms.CharField(label="Motivo", widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, tipos_documento=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo_documento"].choices = [("", "— Elija —")] + [(t["clave"], t["nombre"]) for t in tipos_documento]

    def propiedad(self):
        d = self.cleaned_data
        return {"tipo_documento": d["tipo_documento"], "numero_documento": d.get("numero_documento", ""),
                "fecha_documento": d.get("fecha_documento"), "titular_documento": d["titular_documento"],
                "titular_coincide": d["titular_coincide"] == "si", "superficie_documento_ha": d.get("superficie_documento_ha"),
                "vigente_hasta": d.get("vigente_hasta"), "sin_conflicto": d["sin_conflicto"] == "si",
                "observaciones": d.get("observaciones_propiedad", "")}


class PersonaIncumplidaForm(Bs, forms.ModelForm):
    class Meta:
        model = PersonaIncumplida
        fields = ["nombre", "curp", "rfc", "programa", "motivo", "acuerdo", "fecha_inscripcion"]
        widgets = {"motivo": forms.Textarea(attrs={"rows": 2}), "fecha_inscripcion": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}


class PredioSancionadoForm(Bs, forms.ModelForm):
    folio_predio = forms.CharField(label="Folio del predio (si ya está registrado)", required=False)

    class Meta:
        model = PredioSancionado
        fields = ["descripcion_predio", "municipio", "tipo", "descripcion", "autoridad", "fecha"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 2}), "fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["municipio"].queryset = Municipio.objects.all()
        self.fields["municipio"].required = False
