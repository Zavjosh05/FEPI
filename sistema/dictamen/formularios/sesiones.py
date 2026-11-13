"""Formularios comunes de las sesiones del Comité (convocatoria y documentos)."""
from django import forms

from nucleo.models import Ejercicio

from ..models import CaracterSesion, TipoSesion
from .base import Bs


class SesionForm(Bs, forms.Form):
    ejercicio = forms.ModelChoiceField(label="Programa y ejercicio", queryset=Ejercicio.objects.none(), empty_label=None)
    tipo = forms.ChoiceField(label="Tipo de sesión", choices=TipoSesion.choices)
    caracter = forms.ChoiceField(label="Carácter", choices=CaracterSesion.choices)
    fecha_hora = forms.DateTimeField(label="Fecha y hora de la sesión",
                                     widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                                     input_formats=["%Y-%m-%dT%H:%M"])
    lugar = forms.CharField(label="Lugar o plataforma digital", max_length=250)
    orden_del_dia = forms.CharField(label="Orden del día (un punto por renglón)", widget=forms.Textarea(attrs={"rows": 5}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ejercicio"].queryset = Ejercicio.objects.filter(vigente=True).select_related("programa")
        self.fields["ejercicio"].label_from_instance = lambda e: f"{e.programa.nombre} {e.anio}"


class DocumentoSesionForm(Bs, forms.Form):
    nombre = forms.CharField(label="Nombre del documento", max_length=250, required=False)
    archivo = forms.FileField(label="Archivo")
