"""HU-5.1 · Formularios: comprobante de la cuenta bancaria y envío de la solicitud."""
from django import forms

from .base import Bs


class ComprobanteForm(Bs, forms.Form):
    archivo = forms.FileField(label="Comprobante de la cuenta bancaria (PDF, JPG o PNG)", required=False)
    descripcion = forms.CharField(label="Descripción", required=False, max_length=250,
                                  help_text="Opcional: banco o nota (un cambio de cuenta se registra con un comprobante nuevo).")


class EnvioForm(Bs, forms.Form):
    observaciones = forms.CharField(label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 2}))
