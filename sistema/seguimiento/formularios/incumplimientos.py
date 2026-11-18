"""HU-6.2 · Formularios: aviso de omisión con su plazo, subsanación, requerimiento de devolución, depósito y cuenta para
reintegros."""
from django import forms

from recepcion.forms import Bs

FECHA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class AvisoOmisionForm(Bs, forms.Form):
    omisiones = forms.CharField(label="Omisiones que la persona debe subsanar", widget=forms.Textarea(attrs={"rows": 2}))
    vence = forms.DateField(label="Fecha límite para subsanar", widget=FECHA,
                            help_text="La fija el área responsable: las reglas no dan días.")
    causa = forms.ChoiceField(label="Causa de incumplimiento de las reglas", required=False, choices=())
    incidencia = forms.IntegerField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, causas=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["causa"].choices = [("", "—")] + [(c, c) for c in causas]


class SubsanarForm(Bs, forms.Form):
    motivo = forms.CharField(label="Cómo se subsanaron", widget=forms.Textarea(attrs={"rows": 2}))


class RequerimientoForm(Bs, forms.Form):
    plantas = forms.IntegerField(label="Plantas no establecidas", required=False, min_value=0, initial=0)
    precio_planta = forms.DecimalField(label="Precio por planta ($)", required=False, min_value=0, max_digits=10, decimal_places=2)
    fuente_precio = forms.CharField(label="Fuente del precio", required=False, max_length=250,
                                    help_text="Listado oficial de la Secretaría de Finanzas o costo de producción.")


class DepositoForm(Bs, forms.Form):
    fecha = forms.DateField(label="Fecha del depósito", widget=FECHA)
    importe = forms.DecimalField(label="Importe depositado ($)", max_digits=14, decimal_places=2, min_value=0)
    referencia = forms.CharField(label="Referencia o folio del depósito", max_length=120)
    archivo = forms.FileField(label="Comprobante (PDF, JPG o PNG)")


class CuentaForm(Bs, forms.Form):
    programa = forms.ChoiceField(label="Programa", choices=())
    titular = forms.CharField(label="Titular de la cuenta", max_length=200)
    banco = forms.CharField(label="Banco", max_length=120)
    cuenta = forms.CharField(label="Cuenta o CLABE", max_length=40)
    referencia = forms.CharField(label="Referencia", required=False, max_length=120)

    def __init__(self, *args, programas=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["programa"].choices = [(p.pk, p.nombre) for p in programas]
