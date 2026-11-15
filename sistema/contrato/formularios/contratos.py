"""HU-3.2 · Formularios de los modelos de contrato y de la elaboración."""
from django import forms

from nucleo.models import Ejercicio

from ..models import ModeloContrato, TipoModelo
from .base import Bs


class ModeloForm(Bs, forms.Form):
    ejercicio = forms.ModelChoiceField(label="Programa y ejercicio", queryset=Ejercicio.objects.none())
    tipo = forms.ChoiceField(label="Tipo de modelo", choices=TipoModelo.choices)
    nombre = forms.CharField(label="Nombre del modelo", max_length=200)
    texto = forms.CharField(label="Texto de la plantilla", widget=forms.Textarea(attrs={"rows": 12}),
                            help_text="Los campos «{{campo}}» se llenan con los datos del expediente.")

    def __init__(self, *args, programas=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Ejercicio.objects.filter(reglas_cargadas__isnull=False).select_related("programa")
        if programas is not None:
            qs = qs.filter(programa__in=programas)
        self.fields["ejercicio"].queryset = qs.order_by("programa__clave", "-anio")
        self.fields["ejercicio"].label_from_instance = lambda e: f"{e.programa.nombre} {e.anio}"


class TextoModeloForm(Bs, forms.Form):
    texto = forms.CharField(label="Texto de la nueva versión", widget=forms.Textarea(attrs={"rows": 14}))


class RevisionForm(Bs, forms.Form):
    decision = forms.ChoiceField(label="Resultado de la revisión", widget=forms.RadioSelect,
                                 choices=[("validar", "Validar el modelo"), ("devolver", "Devolver con observaciones")])
    observaciones = forms.CharField(label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 3}),
                                    help_text="Obligatorias al devolver.")


class ElaborarForm(Bs, forms.Form):
    modelo = forms.ModelChoiceField(label="Modelo validado", queryset=ModeloContrato.objects.none(), empty_label=None)

    def __init__(self, *args, modelos=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["modelo"].queryset = ModeloContrato.objects.filter(pk__in=[m.pk for m in modelos])
        self.fields["modelo"].label_from_instance = lambda m: f"{m.nombre} (versión {m.vigente.numero})"
