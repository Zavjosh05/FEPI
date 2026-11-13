"""HU-2.2 · Formularios del dictamen jurídico y de los catálogos de incumplimiento."""
from django import forms

from nucleo.models import Municipio

from ..models import PersonaIncumplida, PredioSancionado, ResultadoJuridico
from .base import Bs


class DictamenJuridicoForm(Bs, forms.Form):
    resultado = forms.ChoiceField(label="Resultado del dictamen jurídico", choices=ResultadoJuridico.choices,
                                  widget=forms.RadioSelect)
    motivo = forms.CharField(label="Motivo", widget=forms.Textarea(attrs={"rows": 3}))


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
