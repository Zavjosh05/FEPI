"""Núcleo · reloj simulado y demostración con el calendario de la convocatoria (G-03, P-03)."""
from datetime import date, datetime, timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from nucleo import demo_calendario, reloj
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
    assert fecha_corte() == date(2026, 11, 19)                # la de las pruebas (conftest)
    monkeypatch.setenv("DEMO_FECHA_CORTE", "2026-12-01")
    assert fecha_corte() == date(2026, 12, 1)
    for fuera in ("2026-10-01", "2027-01-04"):                # fuera del ejercicio de la demostración
        monkeypatch.setenv("DEMO_FECHA_CORTE", fuera)
        with pytest.raises(ValueError):
            fecha_corte()


def test_demo_fecha_de_corte_es_hoy_con_topes(catalogos, monkeypatch):
    """D-32: sin DEMO_FECHA_CORTE, la fecha de corte es el día de la carga, sin bajar del 19-nov ni pasar del 31-dic-2026."""
    monkeypatch.delenv("DEMO_FECHA_CORTE")
    for hoy, corte in (("2026-11-25", "2026-11-25"), ("2026-12-15", "2026-12-15"), ("2026-11-28", "2026-11-28"),
                       ("2026-06-01", "2026-11-19"), ("2027-02-10", "2026-12-31"), ("2031-07-07", "2026-12-31")):
        with reloj.en(f"{hoy} 08:00"):
            assert fecha_corte() == date.fromisoformat(corte), hoy
    # Durante la carga la fecha de corte no cambia aunque el reloj simulado se mueva a otros días
    with reloj.en("2026-12-15 08:00"):
        with demo_calendario.carga() as corte:
            with reloj.en("2026-03-02 10:00"):
                assert fecha_corte() == corte == date(2026, 12, 15)
    # Sábado: la fecha de corte es hoy y los pasos recientes se cuentan desde el lunes (ancla)
    with reloj.en("2026-11-28 08:00"), demo_calendario.carga():
        assert demo_calendario.ancla() == date(2026, 11, 30)
        assert demo_calendario.reciente("2026-11-19") == date(2026, 11, 28)
        assert demo_calendario.reciente("2026-11-18") == date(2026, 11, 27)


def test_demo_calendario_reciente_conserva_la_referencia_y_el_cheque_por_vencer(catalogos, monkeypatch):
    """Con el corte de referencia, ``reciente`` deja cada fecha igual; con cualquier otro, el cheque de Loma Verde vence a 1-5 días
    hábiles de la fecha de corte (por vencer) y no antes."""
    from nucleo import dias_habiles

    fechas = ["2026-10-06", "2026-10-12", "2026-10-14", "2026-10-20", "2026-10-22", "2026-11-03", "2026-11-04", "2026-11-05",
              "2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13", "2026-11-17", "2026-11-19",
              "2026-11-24"]
    assert all(demo_calendario.reciente(f) == date.fromisoformat(f) for f in fechas)
    assert demo_calendario.entrega_cheque_por_vencer() == date(2026, 8, 21)
    dia = date(2026, 11, 19)
    while dia <= date(2026, 12, 31):
        monkeypatch.setenv("DEMO_FECHA_CORTE", dia.isoformat())
        entrega = demo_calendario.entrega_cheque_por_vencer()
        vence = dias_habiles.siguiente_habil(dias_habiles.sumar_meses(entrega, 3))
        assert dias_habiles.es_habil(entrega) and 1 <= dias_habiles.dias_habiles_entre(dia, vence) <= 5, dia
        assert [demo_calendario.reciente(f) for f in fechas] == sorted(demo_calendario.reciente(f) for f in fechas), dia
        dia += timedelta(days=1)


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


def _estado_clave(nombre):
    return Expediente.objects.get(predio__nombre=nombre).estado.clave


@pytest.mark.parametrize("hoy", ["2026-12-15", "2026-11-28", "2027-02-10"])     # martes; sábado; 2027 (tope: 31-dic-2026)
def test_demo_fecha_de_corte_es_hoy_y_los_casos_quedan_en_su_punto(catalogos, monkeypatch, hoy):
    """D-32: cargada otro día, la demostración arma sus casos recientes desde ese día: Los Pinos por firmar y en plazo, a un
    día hábil de vencer; Cañada Seca señalada sin firma; el cheque de Loma Verde por vencer; el vale de Mirador de los Pinos
    vigente y el de Ladera Verde vencido; y nada ocurre después de la fecha de corte."""
    from contrato.models import SinFirma, ValePlanta
    from nucleo import dias_habiles, plazos
    from pagos import cheques
    from pagos.models import Cheque

    monkeypatch.delenv("DEMO_FECHA_CORTE")
    with reloj.en(f"{hoy} 07:30"):
        call_command("cargar_demo")
        corte = demo_calendario.corte_para(timezone.localdate())
    ancla = dias_habiles.siguiente_habil(corte)
    assert not Evento.objects.filter(fecha_hora__gt=cuando(corte, 23, 59)).exists()
    assert not Evento.objects.filter(fecha_hora__year__gt=2026).exists()
    # Recepción y dictamen siguen en el calendario de la Convocatoria
    from dictamen.models import SesionComite
    assert timezone.localdate(SesionComite.objects.get(numero="SO-CC-2026-01").fecha_hora) == date(2026, 7, 14)
    # Contratos: Los Pinos en la Delegación, por firmar, a un día hábil (desde el ancla) de vencer; Barranca Honda por enviar
    los_pinos = Expediente.objects.get(predio__nombre="Plantación Los Pinos")
    assert los_pinos.estado.clave == "contrato_en_delegacion"
    v = plazos.vencimiento(los_pinos, "firma_liberacion")
    assert v.estado(corte) == "por vencer" and dias_habiles.dias_habiles_entre(ancla, v.vencimiento) == 1
    assert _estado_clave("Barranca Honda") == "contrato_elaborado" and _estado_clave("Ojo de Agua") == "notificada"
    assert not SinFirma.objects.filter(expediente__predio__nombre__in=["Plantación Los Pinos", "Barranca Honda",
                                                                         "Rancho La Huerta", "Ojo de Agua"]).exists()
    # El contrato vencido sin firma, señalado
    assert _estado_clave("Cañada Seca") == "sin_firma_en_plazo" and SinFirma.objects.count() == 1
    # Vales: vigentes (Mirador de los Pinos, Arroyo Claro), vencido (Ladera Verde) y repuesto (Cerro Gordo)
    vale = {v.expediente.predio.nombre: v.situacion(corte) for v in ValePlanta.objects.filter(repone__isnull=True)
            if not v.surtido}                                   # los surtidos son los del lote de pagos de PS
    assert vale == {"Mirador de los Pinos": "vigente", "Arroyo Claro": "vigente", "Ladera Verde": "vencido",
                    "Cerro Gordo": "repuesto"}
    assert ValePlanta.objects.get(repone__isnull=False).situacion(corte) == "vigente"
    # Cheque por vencer (Loma Verde) con su aviso; los de noviembre, en plazo
    loma = Cheque.objects.get(expediente__predio__nombre="Loma Verde")
    assert cheques.vencimiento_cobro(loma).estado(corte) == "por vencer"
    assert loma.expediente.eventos.filter(tipo="cheque_por_vencer").count() == 1
    venado = Cheque.objects.get(expediente__predio__nombre="Cerro del Venado")
    assert cheques.vencimiento_cobro(venado).estado(corte) == "en plazo"
    assert _estado_clave("Monte Alto") == "cheque_enviado" and _estado_clave("Paraje Las Ánimas") == "cheque_emitido"
    # La sesión de seguimiento de CC se convocó antes de la fecha de corte y se celebra después
    seg = SesionComite.objects.get(ejercicio__programa__clave="CC", tipo="seguimiento")
    assert timezone.localdate(seg.convocatoria_enviada) <= corte < timezone.localdate(seg.fecha_hora)
