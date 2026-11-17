"""HU-4.1 · Formulario del envío de una comprobación (portal) o de su entrega en ventanilla (Delegación)."""
from django import forms

from recepcion.forms import Bs


class EnvioForm(Bs, forms.Form):
    tipo = forms.ChoiceField(label="Qué envía", choices=())
    fecha_hecho = forms.DateField(label="Fecha del hecho", required=False,
                                  widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                                  help_text="Término de las actividades, fecha del siniestro o del depósito, según lo que envíe.")
    periodo = forms.ChoiceField(label="Periodo que reporta", required=False, choices=())
    descripcion = forms.CharField(label="Descripción", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    archivo = forms.FileField(label="Documento (PDF, JPG o PNG)", required=False)
    persona_entrega = forms.CharField(label="Quién lo entrega", required=False, max_length=250,
                                      help_text="Si se deja vacío, la persona beneficiaria.")

    def __init__(self, *args, tipos=(), periodos=(), ventanilla=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].choices = [(t["clave"], t["nombre"]) for t in tipos]
        if any(t.get("pide_periodo") for t in tipos) and periodos:
            self.fields["periodo"].choices = [("", "—")] + [(p["clave"], p.get("nombre", p["clave"])) for p in periodos]
        else:
            del self.fields["periodo"]
        if not any(t.get("fecha_hecho") for t in tipos):
            del self.fields["fecha_hecho"]
        if not ventanilla:
            del self.fields["persona_entrega"]
