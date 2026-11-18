"""HU-6.1 · Formularios: solicitud de sustitución, desistimiento o aviso de fallecimiento; propuesta al Comité; acuerdo de la
Secretaría Técnica; prórroga por causa externa (MFS)."""
from django import forms

from recepcion.forms import Bs

FECHA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class SolicitudForm(Bs, forms.Form):
    tipo = forms.ChoiceField(label="Solicitud", choices=())
    archivo = forms.FileField(label="Escrito o documento (PDF, JPG o PNG)", required=False)
    persona_presenta = forms.CharField(label="Quién la presenta", required=False, max_length=250)
    fecha_hecho = forms.DateField(label="Fecha del fallecimiento", required=False, widget=FECHA)
    motivo = forms.CharField(label="Motivos o causa justificada", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    causa = forms.ChoiceField(label="Causa de la sustitución", required=False,
                              choices=[("", "—"), ("fallecimiento", "Fallecimiento de la persona titular"),
                                       ("imposibilidad", "Imposibilidad de la persona titular (causa justificada)")])
    segunda_nombre = forms.CharField(label="Nombre de la segunda persona beneficiaria", required=False, max_length=250)
    segunda_curp = forms.CharField(label="CURP", required=False, max_length=18)
    segunda_telefono = forms.CharField(label="Teléfono", required=False, max_length=40)
    segunda_parentesco = forms.CharField(label="Parentesco o relación", required=False, max_length=100)
    firmas = forms.MultipleChoiceField(label="Firmas y sello verificados en el escrito", required=False,
                                       widget=forms.CheckboxSelectMultiple, choices=())

    def __init__(self, *args, tipos=(), puntos=(), portal=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].choices = [(t["clave"], t["nombre"]) for t in tipos if not portal or t.get("portal")]
        self.fields["firmas"].choices = [(p, p) for p in puntos]
        if portal:
            del self.fields["persona_presenta"]

    def segunda(self):
        d = self.cleaned_data
        return {"nombre": d.get("segunda_nombre", ""), "curp": d.get("segunda_curp", ""),
                "telefono": d.get("segunda_telefono", ""), "parentesco": d.get("segunda_parentesco", "")}


class PropuestaForm(Bs, forms.Form):
    tipo = forms.ChoiceField(label="Propuesta", choices=())
    resolucion = forms.ChoiceField(label="Qué se propone (caso fortuito)", required=False, choices=())
    base = forms.ChoiceField(label="Qué se requiere devolver (cancelación o baja)", required=False, choices=())
    descripcion = forms.CharField(label="Texto del acuerdo que se propone (opcional: si se deja vacío, lo arma el sistema)",
                                  required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, tipos=(), resoluciones=None, bases=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].choices = list(tipos)
        self.fields["resolucion"].choices = [("", "—")] + list((resoluciones or {}).items())
        self.fields["base"].choices = list((bases or {"ministrado": "Lo ministrado"}).items())


class ReasignacionForm(Bs, forms.Form):
    observaciones = forms.CharField(label="Observaciones para el Comité", required=False,
                                    widget=forms.Textarea(attrs={"rows": 2}))


class AcuerdoPropuestaForm(Bs, forms.Form):
    sesion = forms.ChoiceField(label="Sesión de seguimiento", choices=())
    aprueba = forms.ChoiceField(label="Lo que acordó el Comité", choices=[("si", "Aprueba la propuesta"),
                                                                          ("no", "No aprueba la propuesta")])
    descripcion = forms.CharField(label="Texto del acuerdo (opcional)", required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, sesiones=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sesion"].choices = [(s.pk, f"{s.numero} · {s.fecha_hora:%d/%m/%Y %H:%M}") for s in sesiones]


class ProrrogaForm(Bs, forms.Form):
    causa = forms.CharField(label="Causa externa por la que no se cumplió la meta", widget=forms.Textarea(attrs={"rows": 2}))
    plazo_original = forms.DateField(label="Término del contrato", required=False, widget=FECHA)
    plazo_solicitado = forms.DateField(label="Plazo que se solicita", required=False, widget=FECHA)
    archivo = forms.FileField(label="Escrito de la persona (PDF, JPG o PNG)", required=False)


class ResolucionProrrogaForm(Bs, forms.Form):
    autorizada = forms.ChoiceField(label="Resolución", choices=[("si", "Autorizada con adendum"), ("no", "Negada")])
    plazo_nuevo = forms.DateField(label="Plazo nuevo (adendum)", required=False, widget=FECHA)
    archivo = forms.FileField(label="Adendum firmado (PDF, JPG o PNG)", required=False)
    motivo = forms.CharField(label="Motivo", widget=forms.Textarea(attrs={"rows": 2}))
