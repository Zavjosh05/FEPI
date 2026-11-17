"""HU-4.2 · Formularios: resultado de la verificación en campo (con hasta dos incidencias) y devolución de la comprobación."""
from django import forms

from recepcion.forms import Bs

FECHA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class VerificacionForm(Bs, forms.Form):
    tipo_documento = forms.ChoiceField(label="Documento del resultado", choices=())
    archivo = forms.FileField(label="Documento firmado (PDF, JPG o PNG)", required=False)
    fecha_visita = forms.DateField(label="Fecha de la visita", required=False, widget=FECHA)
    superficie_verificada = forms.DecimalField(label="Superficie verificada (ha)", required=False, max_digits=10,
                                               decimal_places=4, min_value=0)
    sobrevivencia = forms.DecimalField(label="Sobrevivencia (%)", required=False, max_digits=5, decimal_places=2,
                                       min_value=0, max_value=100)
    observaciones = forms.CharField(label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    incidencia_1_tipo = forms.ChoiceField(label="Incidencia", required=False, choices=())
    incidencia_1_descripcion = forms.CharField(label="Descripción de la incidencia", required=False)
    incidencia_1_archivo = forms.FileField(label="Documento que la avala", required=False)
    incidencia_2_tipo = forms.ChoiceField(label="Otra incidencia", required=False, choices=())
    incidencia_2_descripcion = forms.CharField(label="Descripción", required=False)
    incidencia_2_archivo = forms.FileField(label="Documento que la avala", required=False)

    def __init__(self, *args, documentos=(), incidencias=(), superficie=True, sobrevivencia=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo_documento"].choices = list(documentos)
        for n in (1, 2):
            self.fields[f"incidencia_{n}_tipo"].choices = [("", "—")] + list(incidencias)
        if not superficie:
            del self.fields["superficie_verificada"]
        if not sobrevivencia:
            del self.fields["sobrevivencia"]

    def incidencias(self):
        d = self.cleaned_data
        return [{"tipo": d[f"incidencia_{n}_tipo"], "descripcion": d.get(f"incidencia_{n}_descripcion", ""),
                 "archivo": d.get(f"incidencia_{n}_archivo")} for n in (1, 2) if d.get(f"incidencia_{n}_tipo")]


class DevolucionForm(Bs, forms.Form):
    motivo = forms.CharField(label="Observaciones para la persona beneficiaria", widget=forms.Textarea(attrs={"rows": 2}))
