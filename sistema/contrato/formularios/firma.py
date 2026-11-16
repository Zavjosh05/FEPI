"""HU-3.3 · Formularios del registro de la firma y de la liberación del recurso."""
from django import forms

from ..models import Firmante
from .base import Bs

FECHA_HORA = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


class FirmaForm(Bs, forms.Form):
    """Los puntos de verificación y los elementos de formalización cambian por tipo de persona y por programa
    (``datos/contrato.json``): se agregan como campos dinámicos."""

    firmado_en = forms.DateTimeField(
        label="Fecha y hora de la firma", required=False, widget=FECHA_HORA,
        help_text="Si se deja vacía se usa el momento actual; no puede ser futura ni anterior al envío del contrato.")
    firmante = forms.ChoiceField(label="Firma", choices=Firmante.choices, initial=Firmante.PERSONA,
                                 widget=forms.RadioSelect)
    firmante_nombre = forms.CharField(label="Nombre de quien firma", max_length=250)
    archivo = forms.FileField(label="Contrato firmado, digitalizado (PDF, JPG o PNG)", required=False)
    observaciones = forms.CharField(label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, puntos=(), elementos=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.puntos, self.elementos = list(puntos), list(elementos)
        for p in self.puntos:
            self.fields[f"v_{p['clave']}"] = forms.BooleanField(label=p["texto"], required=False)
            self.fields[f"v_{p['clave']}"].widget.attrs["class"] = "form-check-input"
        for e in self.elementos:
            self.fields[f"e_{e['clave']}_archivo"] = forms.FileField(label=e["nombre"], required=False)
            self.fields[f"e_{e['clave']}_archivo"].widget.attrs["class"] = "form-control"
            if e.get("dato"):
                self.fields[f"e_{e['clave']}_dato"] = forms.CharField(label=e["dato"]["etiqueta"], required=False,
                                                                       max_length=120)
                self.fields[f"e_{e['clave']}_dato"].widget.attrs["class"] = "form-control"

    def campos_verificacion(self):
        return [self[f"v_{p['clave']}"] for p in self.puntos]

    def campos_formalizacion(self):
        return [(e, self[f"e_{e['clave']}_archivo"], self[f"e_{e['clave']}_dato"] if e.get("dato") else None)
                for e in self.elementos]

    def verificadas(self):
        return [p["clave"] for p in self.puntos if self.cleaned_data.get(f"v_{p['clave']}")]

    def datos_elementos(self):
        return {e["clave"]: {"archivo": self.cleaned_data.get(f"e_{e['clave']}_archivo"),
                             "dato": self.cleaned_data.get(f"e_{e['clave']}_dato", "")} for e in self.elementos}


class LiberarForm(Bs, forms.Form):
    motivo = forms.CharField(label="Motivo de la liberación del recurso", widget=forms.Textarea(attrs={"rows": 2}))
