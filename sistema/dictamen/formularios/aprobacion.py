"""HU-2.3 · Formularios de la sesión de aprobación."""
from django import forms

from ..models import ResultadoListado
from .base import Bs


class PropuestaForm(Bs, forms.Form):
    presupuesto = forms.DecimalField(label="Recurso disponible ($)", required=False, max_digits=14, decimal_places=2,
                                     min_value=0, help_text="Vacío = todas las factibles a la Lista de Personas Beneficiarias.")


class AjusteForm(Bs, forms.Form):
    resultado = forms.ChoiceField(label="Listado", choices=ResultadoListado.choices)
    orden = forms.IntegerField(label="Lugar", required=False, min_value=1)
    motivo = forms.CharField(label="Motivo del ajuste del Comité", max_length=500)


class ActaForm(Bs, forms.Form):
    autoriza_publicacion = forms.BooleanField(
        label="El Comité autoriza publicar los listados en las Delegaciones y en la página de PROBOSQUE", required=False)
    observaciones = forms.CharField(label="Observaciones del acta", required=False, widget=forms.Textarea(attrs={"rows": 2}))
