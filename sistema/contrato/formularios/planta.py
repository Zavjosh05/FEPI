"""HU-3.4 · Formularios del Vale de Planta y de la salida de planta del vivero."""
from django import forms

from ..models import Especie, Vivero
from .base import Bs
from .firma import FECHA_HORA


class ValeForm(Bs, forms.Form):
    """Emisión del vale: vivero, cantidad por especie (campos dinámicos, uno por especie del catálogo), carta compromiso
    si es antes de la firma y motivo si la cantidad se aparta de la propuesta."""

    vivero = forms.ModelChoiceField(label="Vivero que entrega la planta", queryset=Vivero.objects.none(), empty_label=None)
    fecha_hora = forms.DateTimeField(
        label="Fecha y hora de entrega del vale", required=False, widget=FECHA_HORA,
        help_text="Si se deja vacía se usa el momento actual; no puede ser futura.")
    carta_compromiso = forms.FileField(label="Carta compromiso (archivo)", required=False)
    planta_disponible = forms.BooleanField(
        label="El vivero confirma que hay planta disponible", required=False,
        help_text="Solo en reposición: el vale nuevo se expide siempre que haya disponibilidad de planta.")
    motivo_ajuste = forms.CharField(label="Motivo del ajuste a la propuesta", required=False,
                                    widget=forms.Textarea(attrs={"rows": 2}),
                                    help_text="Obligatorio si la cantidad total no es la propuesta.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vivero"].queryset = Vivero.objects.filter(activo=True)
        self.especies = list(Especie.objects.filter(activa=True))
        for e in self.especies:
            self.fields[f"esp_{e.pk}"] = forms.IntegerField(label=str(e), required=False, min_value=0)
            self.fields[f"esp_{e.pk}"].widget.attrs["class"] = "form-control"

    def campos_especies(self):
        return [self[f"esp_{e.pk}"] for e in self.especies]

    def renglones(self):
        return [(e, self.cleaned_data.get(f"esp_{e.pk}")) for e in self.especies if self.cleaned_data.get(f"esp_{e.pk}")]


class SalidaForm(Bs, forms.Form):
    especie = forms.ModelChoiceField(label="Especie", queryset=Especie.objects.none(), empty_label=None)
    cantidad = forms.IntegerField(label="Cantidad (piezas)", min_value=1)
    fecha_hora = forms.DateTimeField(
        label="Fecha y hora de la salida", required=False, widget=FECHA_HORA,
        help_text="Si se deja vacía se usa el momento actual; no puede ser futura ni anterior a la entrega del vale.")
    observaciones = forms.CharField(label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 1}))

    def __init__(self, *args, vale=None, **kwargs):
        super().__init__(*args, **kwargs)
        if vale is not None:
            self.fields["especie"].queryset = Especie.objects.filter(pk__in=[r.especie_id for r in vale.renglones.all()])
