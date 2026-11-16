"""HU-5.3 · Formularios: emisión, entrega y cobro del cheque."""
from django import forms

from .base import Bs

FECHA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
FECHA_HORA = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


class EmisionForm(Bs, forms.Form):
    numero = forms.CharField(label="Número de cheque", max_length=40)
    importe = forms.DecimalField(label="Importe", max_digits=14, decimal_places=2,
                                 help_text="Debe ser igual al solicitado.")
    fecha_emision = forms.DateField(label="Fecha de emisión", widget=FECHA)

    def __init__(self, *args, importe=None, **kwargs):
        super().__init__(*args, **kwargs)
        if importe is not None:
            self.fields["importe"].initial = importe


class EntregaChequeForm(Bs, forms.Form):
    recibe_nombre = forms.CharField(label="Quién recibe el cheque", max_length=250)
    entregado_en = forms.DateTimeField(label="Fecha y hora de la entrega", required=False, widget=FECHA_HORA,
                                       help_text="Si se deja vacía se usa el momento actual.")


class CobroForm(Bs, forms.Form):
    fecha_cobro = forms.DateField(label="Fecha del cobro", required=False, widget=FECHA)
