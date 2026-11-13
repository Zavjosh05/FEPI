"""Revisión diaria de plazos (servicio «plazos» de Docker Compose).

Sprint 1: señala en la bitácora (una sola vez) los expedientes cuyo plazo para completar la
documentación ya venció, para que la unidad que los atiende decida si se tiene por desechada la
solicitud. No cambia estados por sí mismo.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from nucleo.models import Evento, Expediente
from recepcion.models import EstadoRevision, ResultadoValidacion, Validacion
from recepcion.servicios import plazo_recepcion


class Command(BaseCommand):
    help = "Señala los plazos vencidos (faltantes sin entregar) en la bitácora de cada expediente."

    def add_arguments(self, parser):
        parser.add_argument("--fecha", help="Fecha de revisión AAAA-MM-DD (por defecto, hoy).")

    def handle(self, *args, **opciones):
        hoy = timezone.localdate()
        if opciones.get("fecha"):
            from datetime import date
            hoy = date.fromisoformat(opciones["fecha"])
        avisos = 0
        # 1) Avisos de faltantes de la Dirección vencidos.
        for v in Validacion.objects.filter(resultado=ResultadoValidacion.FALTANTES, vencimiento_avisado=False,
                                           fecha_limite__lt=hoy, expediente__estado__clave="faltantes"):
            Evento.registrar(v.expediente, None, "plazo_vencido",
                             f"Venció el {v.fecha_limite:%d/%m/%Y} el plazo del aviso de faltantes sin que se "
                             "reenviara el expediente.", datos={"validacion": v.pk})
            v.vencimiento_avisado = True
            v.save(update_fields=["vencimiento_avisado"])
            avisos += 1
        # 2) Solicitudes en la Delegación con faltantes desde la recepción.
        for exp in Expediente.objects.filter(estado__clave="recibida",
                                             revisiones__estado=EstadoRevision.FALTANTE).distinct():
            limite = plazo_recepcion(exp)
            if limite and limite < hoy and not exp.eventos.filter(tipo="plazo_vencido").exists():
                Evento.registrar(exp, None, "plazo_vencido",
                                 f"Venció el {limite:%d/%m/%Y} el plazo para completar la documentación "
                                 "desde la recepción.", datos={"fecha_limite": limite.isoformat()})
                avisos += 1
        # 3) Revisiones que registran los demás módulos (por ejemplo, el plazo del dictamen).
        from nucleo.extensiones import REVISIONES_PLAZO

        for revisar in REVISIONES_PLAZO:
            avisos += revisar(hoy)
        self.stdout.write(self.style.SUCCESS(f"Plazos revisados al {hoy:%d/%m/%Y}: {avisos} vencimientos señalados."))
