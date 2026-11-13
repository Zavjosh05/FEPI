"""HU-2.1 · Formulario del dictamen técnico."""
from django import forms

from ..models import ResultadoTecnico
from .base import Bs


class DictamenTecnicoForm(Bs, forms.Form):
    resultado = forms.ChoiceField(label="Resultado del dictamen técnico", choices=ResultadoTecnico.choices,
                                  widget=forms.RadioSelect)
    motivo = forms.CharField(label="Motivo", widget=forms.Textarea(attrs={"rows": 3}))
    superficie_factible_ha = forms.DecimalField(label="Superficie factible (ha)", required=False, max_digits=12,
                                                decimal_places=4, min_value=0,
                                                help_text="Vacío = la del polígono vigente.")
