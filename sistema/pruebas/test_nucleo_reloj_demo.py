"""Núcleo · reloj simulado y demostración con el calendario de la convocatoria (G-03, P-03)."""
from datetime import date, datetime, timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from nucleo import reloj
from nucleo.demo_calendario import cuando, fecha_corte, habil, habil_antes
from nucleo.models import Acuse, Evento, Expediente

pytestmark = pytest.mark.django_db


def test_reloj_todo_el_sistema_ve_el_momento_simulado(nueva_solicitud):
    antes = timezone.now()
    with reloj.en("2026-03-02 10:30") as r:
        assert timezone.localtime(timezone.now()).replace(microsecond=0) == cuando("2026-03-02", 10, 30)
        assert timezone.localdate() == date(2026, 3, 2)
        exp = nueva_solicitud()                      # default=timezone.now, folios con año, acuse y bitácora
        assert timezone.localdate(exp.fecha_recepcion) == date(2026, 3, 2)
        assert Acuse.objects.filter(expediente=exp).first().fecha_hora == cuando("2026-03-02", 10, 30)
        assert all(e.fecha_hora == cuando("2026-03-02", 10, 30) for e in exp.eventos.all())
        r.avanzar(days=1, hours=1)
        assert timezone.localdate() == date(2026, 3, 3)
    assert abs((timezone.now() - antes).total_seconds()) < 60 and not reloj.activo()
    nueva = Evento.registrar(exp, None, "x", "real")
    assert nueva.fecha_hora.year >= 2026 and nueva.fecha_hora > antes - timedelta(seconds=1)


def test_reloj_anidado_y_con_tic():
    with reloj.en("2026-05-04 09:00") as externo:
        with reloj.en("2026-06-01 12:00", tic=5) as interno:
            a, b = timezone.now(), timezone.now()
            assert b - a == timedelta(seconds=5) and timezone.localdate() == date(2026, 6, 1)
        assert timezone.localdate() == date(2026, 5, 4) and externo.momento == cuando("2026-05-04", 9)
    with pytest.raises(TypeError):
        reloj.en(3.5).__enter__()


def test_calendario_habil_y_fecha_de_corte(catalogos, monkeypatch):
    assert habil("2026-03-14") == date(2026, 3, 17)          # sábado → el 16 es inhábil (Benito Juárez)
    assert habil("2026-02-02") == date(2026, 2, 3)
    assert habil_antes("2026-03-17", 1) == date(2026, 3, 13)
    assert fecha_corte() == date(2026, 11, 19)
    monkeypatch.setenv("DEMO_FECHA_CORTE", "2026-10-01")
    assert fecha_corte() == date(2026, 10, 1)


def test_demo_ocurre_en_el_calendario_de_la_convocatoria_sin_importar_el_dia_de_la_carga(catalogos):
    with reloj.en("2031-07-07 08:00"):                       # el día de la carga no cuenta
        call_command("cargar_demo")
        call_command("cargar_demo")                          # idempotente
    corte = cuando(fecha_corte(), 23, 59)
    eventos = Evento.objects.all()
    assert eventos.exists() and not eventos.filter(fecha_hora__gt=corte).exists()
    assert not eventos.filter(fecha_hora__year__gt=2026).exists() and not Acuse.objects.filter(fecha_hora__year__gt=2026).exists()
    # Recepción dentro del periodo de la Convocatoria (28-ene a 27-mar) y ningún plazo «sin sentido»
    for exp in Expediente.objects.all():
        assert date(2026, 1, 28) <= timezone.localdate(exp.fecha_recepcion) <= date(2026, 3, 27), exp.folio
    # El día de la sesión de aprobación de CC (14-jul) y el acta el mismo día; la publicación de PS, después de su acta
    from dictamen.models import SesionComite
    cc = SesionComite.objects.get(numero="SO-CC-2026-01")
    assert timezone.localdate(cc.fecha_hora) == date(2026, 7, 14) and timezone.localdate(cc.acta_fecha) == date(2026, 7, 14)
    assert cc.convocatoria_enviada < cc.fecha_hora - timedelta(days=5)
    # Casos fuera de plazo a propósito: contrato sin firma, dictamen vencido, cheque por vencer
    from nucleo import plazos
    ocotal = Expediente.objects.get(predio__nombre="El Ocotal")
    from dictamen import tecnico
    assert tecnico.situacion_plazo(ocotal, fecha_corte())["situacion"] == "vencido"
    assert tecnico.situacion_plazo(Expediente.objects.get(predio__nombre="Potrero Viejo"))["situacion"] == "fuera_de_plazo"
    assert tecnico.situacion_plazo(Expediente.objects.get(predio__nombre="La Joya Alta"))["situacion"] == "cumplido"
    assert Expediente.objects.get(predio__nombre="Cañada Seca").estado.clave == "sin_firma_en_plazo"
    from pagos.models import Cheque
    loma = Cheque.objects.get(expediente__predio__nombre="Loma Verde")
    assert timezone.localdate(loma.entregado_en) == date(2026, 8, 21) and loma.expediente.eventos.filter(tipo="cheque_por_vencer").exists()
    # Los contratos en plazo siguen en plazo en la fecha de corte
    los_pinos = Expediente.objects.get(predio__nombre="Plantación Los Pinos")
    assert los_pinos.estado.clave == "contrato_en_delegacion"
    assert plazos.vencimiento(los_pinos, "firma_liberacion").estado(fecha_corte()) in ("en plazo", "por vencer")
