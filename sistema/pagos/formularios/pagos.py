"""HU-5.2 · Formularios: revisión de la solicitud, pago de la ministración y remisión a la Fiduciaria."""
from django import forms

from .base import Bs


class RevisionForm(Bs, forms.Form):
    observaciones = forms.CharField(label="Observaciones para el área responsable", required=False,
                                    widget=forms.Textarea(attrs={"rows": 2}),
                                    help_text="Obligatorias al devolver la solicitud.")


class PagoForm(Bs, forms.Form):
    tipo = forms.ChoiceField(label="Forma de pago", choices=())
    referencia = forms.CharField(label="Referencia del pago", max_length=120,
                                 help_text="De la transferencia o depósito; en el cheque, su número.")
    fecha_pago = forms.DateField(label="Fecha del pago", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    importe = forms.DecimalField(label="Importe pagado", max_digits=14, decimal_places=2,
                                 help_text="Debe ser igual al importe solicitado.")
    motivo_cheque = forms.CharField(label="Motivo del cheque (caso excepcional)", required=False, max_length=500)

    def __init__(self, *args, tipos=(), nombres=None, importe=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].choices = [(t, (nombres or {}).get(t, t)) for t in tipos]
        if importe is not None:
            self.fields["importe"].initial = importe


class RemisionForm(Bs, forms.Form):
    oficio = forms.CharField(label="Oficio o referencia de la remisión", required=False, max_length=120)
    observaciones = forms.CharField(label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 2}))
