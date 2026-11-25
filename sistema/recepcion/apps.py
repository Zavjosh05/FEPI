from django.apps import AppConfig


class RecepcionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "recepcion"
    verbose_name = "M1 · Recepción y expediente"

    def ready(self):
        from nucleo import extensiones

        if fuentes_trazabilidad not in extensiones.TRAZABILIDAD:
            extensiones.TRAZABILIDAD.append(fuentes_trazabilidad)


def fuentes_trazabilidad(expediente):
    """Registros del módulo M1 en la pestaña «Trazabilidad»."""
    from .models import ObservacionValidacion, Poligono, RevisionRequisito, Validacion

    return [
        ("Revisión de requisito", RevisionRequisito.history.filter(expediente_id=expediente.pk)),
        ("Polígono", Poligono.history.filter(expediente_id=expediente.pk)),
        ("Validación", Validacion.history.filter(expediente_id=expediente.pk)),
        ("Observación de la validación", ObservacionValidacion.history.filter(
            validacion_id__in=list(Validacion.objects.filter(expediente=expediente).values_list("pk", flat=True)))),
    ]
