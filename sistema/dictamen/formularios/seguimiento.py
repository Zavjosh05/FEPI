"""HU-2.4 · Formulario de acuerdos de seguimiento."""
from django import forms

from nucleo.models import Expediente, Unidad

from .base import Bs


class AcuerdoForm(Bs, forms.Form):
    tipo = forms.ChoiceField(label="Tipo de acuerdo")
    descripcion = forms.CharField(label="Acuerdo", widget=forms.Textarea(attrs={"rows": 2}))
    expedientes = forms.ModelMultipleChoiceField(label="Expedientes a los que aplica", queryset=Expediente.objects.none(),
                                                 widget=forms.SelectMultiple(attrs={"size": 6}))
    unidad_responsable = forms.ModelChoiceField(label="Área que debe cumplirlo", queryset=Unidad.objects.filter(activa=True),
                                                required=False, help_text="Vacío = la que corresponde al tipo de acuerdo.")
    ministracion = forms.IntegerField(label="Ministración (PSAHEM)", required=False, min_value=1)
    periodo = forms.CharField(label="Periodo de reportes (PEG)", required=False, max_length=40)

    def __init__(self, *args, sesion=None, tipos=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].choices = [(t["clave"], t["nombre"]) for t in tipos]
        if sesion is not None:
            self.fields["expedientes"].queryset = (Expediente.objects.filter(ejercicio=sesion.ejercicio)
                                                   .exclude(estado__clave__in=["recibida", "faltantes", "desechada"])
                                                   .select_related("predio"))
            self.fields["expedientes"].label_from_instance = lambda e: f"{e.folio} · {e.predio.nombre} ({e.estado})"
