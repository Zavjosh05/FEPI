"""Núcleo · generador de datos con semilla (G-02)."""
import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction

from nucleo import generador
from nucleo.models import Expediente

pytestmark = pytest.mark.django_db


def _huella():
    return [(e.folio, e.predio.nombre, e.predio.municipio.nombre, e.estado.clave, e.modalidad_id and e.modalidad.clave,
             e.tipo_persona.clave, str(e.superficie_solicitada_ha), e.fecha_recepcion.isoformat())
            for e in Expediente.objects.select_related("predio__municipio", "estado", "modalidad", "tipo_persona")
            .order_by("folio")]


def test_nucleo_generar_datos_misma_semilla_mismos_datos_y_estados_variados(catalogos):
    with transaction.atomic():
        generador.generar("CC", 24, 7)
        primera = _huella()
        transaction.set_rollback(True)
    assert Expediente.objects.count() == 0
    with transaction.atomic():
        generador.generar("CC", 24, 7)
        segunda = _huella()
        assert generador.generar("CC", 24, 7) == 0          # repetir la misma corrida no duplica
        transaction.set_rollback(True)
    assert primera == segunda and len(primera) == 24
    estados = {fila[3] for fila in primera}
    assert {"recibida", "enviada_direccion", "faltantes", "validada", "dictaminada", "publicada"} <= estados
    assert len({fila[2] for fila in primera}) > 5 and len({fila[4] for fila in primera}) > 1       # municipios y modalidades
    with transaction.atomic():
        generador.generar("CC", 24, 8)
        assert [f[1:3] for f in _huella()] != [f[1:3] for f in primera]                          # otra semilla, otros datos
        transaction.set_rollback(True)


def test_nucleo_generar_datos_comando_y_fechas_de_la_convocatoria(catalogos):
    salida = io.StringIO()
    call_command("generar_datos", "--programa", "PS", "--n", "12", "--semilla", "3", stdout=salida)
    assert "PS: 12 solicitudes" in salida.getvalue()
    from django.utils import timezone
    for e in Expediente.objects.all():
        assert 1 <= timezone.localdate(e.fecha_recepcion).month <= 3 and timezone.localdate(e.fecha_recepcion).year == 2026
    with pytest.raises(CommandError):
        call_command("generar_datos", "--programa", "XX")
