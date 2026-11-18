"""HU-4.3 · Formularios: revisión de la Delegación y evaluación de la Dirección de Protección Forestal."""
from django import forms

from recepcion.forms import Bs

from ..models import ResultadoEvaluacion, ResultadoRevision


class RevisionForm(Bs, forms.Form):
    resultado = forms.ChoiceField(label="Resultado de la revisión", choices=ResultadoRevision.choices)
    observaciones = forms.CharField(label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 2}),
                                    help_text="Obligatorias si tiene observaciones o se devuelve para corregir.")


class EvaluacionForm(Bs, forms.Form):
    resultado = forms.ChoiceField(label="Evaluación", choices=[(ResultadoEvaluacion.CUMPLE, "Cumple"),
                                                             (ResultadoEvaluacion.NO_CUMPLE, "No cumple")])
    motivo = forms.CharField(label="Motivo", required=False, widget=forms.Textarea(attrs={"rows": 2}),
                             help_text="Obligatorio si no cumple.")
