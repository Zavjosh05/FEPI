"""HU-6.3 · Formularios: recepción del informe anual en la sesión del Comité."""
from django import forms

from recepcion.forms import Bs


class RecepcionInformeForm(Bs, forms.Form):
    sesion = forms.ChoiceField(label="Sesión del Comité en que se presenta", required=False, choices=())
    observaciones = forms.CharField(label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, sesiones=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sesion"].choices = [("", "Sin indicar sesión")] + [
            (s.pk, f"{s.numero} · {s.get_tipo_display()} · {s.fecha_hora:%d/%m/%Y}") for s in sesiones]
