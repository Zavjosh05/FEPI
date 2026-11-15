"""HU-3.1 · Formularios de la publicación y de la entrega de notificaciones."""
from django import forms

from nucleo.models import MedioNotificacion

from .base import Bs


class PublicarForm(Bs, forms.Form):
    lugares = forms.CharField(
        label="Dónde se publica", required=False, widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Si se deja vacío: página de PROBOSQUE, Oficinas Centrales y Delegaciones Regionales Forestales.")


class EntregaForm(Bs, forms.Form):
    medio = forms.ChoiceField(label="Medio", choices=MedioNotificacion.choices, initial=MedioNotificacion.PERSONAL)
    fecha_hora = forms.DateTimeField(
        label="Fecha y hora de la notificación", required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        help_text="Si se deja vacía se usa el momento actual; no puede ser futura ni anterior al envío.")
    observaciones = forms.CharField(label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 2}))
