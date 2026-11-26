"""D-38 · Detalles de la interfaz que salieron al grabar el video del sprint 2 (HU-3.1, HU-3.2, HU-3.3 y HU-5.2)."""
import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command

from contrato import contratos
from nucleo import plazos
from nucleo.demo_calendario import fecha_corte
from nucleo.models import Expediente, Notificacion, TipoNotificacion
from pagos.models import EstadoSolicitud, SolicitudPago

from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def test_hu_3_2_la_plantilla_base_validada_ya_no_lleva_la_marca_de_borrador(usuarios, cc, client, contrasena):
    m = contratos.crear_plantilla_base(usuarios["dir_drff"], cc)
    assert m.por_validar_base
    with pytest.raises(ValidationError, match="todavía lleva la marca"):
        contratos.validar_version(usuarios["juridica"], m.vigente, "Conforme")
    contratos.modificar_modelo(usuarios["dir_drff"], m, m.vigente.texto.replace(contratos.MARCA_BORRADOR, "").strip())
    contratos.validar_version(usuarios["juridica"], m.vigente, "Conforme")
    m.refresh_from_db()
    assert m.validado and not m.por_validar_base and contratos.MARCA_BORRADOR not in m.nombre
    client.login(username="dir_drff", password=contrasena)
    assert contratos.MARCA_BORRADOR not in client.get(f"/contrato/modelos/{m.pk}/").content.decode()
    # Un texto nuevo vuelve a quedar por validar, pero ya sin la marca en el nombre
    contratos.modificar_modelo(usuarios["dir_drff"], m, m.vigente.texto + "\nCláusula adicional.")
    assert m.por_validar_base and contratos.MARCA_BORRADOR not in m.nombre


@pytest.fixture
def demo(catalogos):
    call_command("cargar_demo")


def test_hu_3_3_en_la_demo_la_firma_programada_no_pasa_del_vencimiento_para_liberar(demo):
    revisados = 0
    for exp in Expediente.objects.filter(contrato__isnull=False).select_related("ejercicio__programa"):
        programada = plazos.vencimiento(exp, "firma_programada")
        liberacion = plazos.vencimiento(exp, "firma_liberacion")
        if programada and liberacion and programada.tiene_fecha and liberacion.tiene_fecha:
            assert programada.vencimiento <= liberacion.vencimiento, exp.folio
            revisados += 1
    pinos = Expediente.objects.get(predio__nombre="Plantación Los Pinos")
    assert plazos.vencimiento(pinos, "firma_programada").vencimiento >= fecha_corte() and revisados >= 5


def test_hu_5_2_en_la_demo_las_solicitudes_psahem_por_remitir_siguen_en_plazo(demo):
    pendientes = SolicitudPago.objects.filter(expediente__ejercicio__programa__clave="PSA",
                                              estado__in=[EstadoSolicitud.ENVIADA, EstadoSolicitud.ACEPTADA])
    assert {s.expediente.predio.nombre for s in pendientes} >= {"Rancho El Pedregal", "Ejido La Joya"}
    for sol in pendientes:
        venc = plazos.vencimiento(sol.expediente, "instruccion_pago_fiduciaria", fecha_evento=sol.enviada_en)
        assert venc.vencimiento > fecha_corte(), sol.expediente.predio.nombre


def test_hu_3_1_el_aviso_de_resultados_dice_cual_fue_el_resultado(demo):
    avisos = Notificacion.objects.filter(tipo=TipoNotificacion.RESULTADOS)
    textos = {n.datos.get("resultado"): n.tipo_texto for n in avisos}
    assert textos["beneficiaria"] == "Resultados (persona beneficiaria)"
    assert all(n.tipo_texto in str(n) for n in avisos[:3])
    aviso = avisos.first()                               # el mismo aviso con otro resultado publicado (sin guardar)
    for resultado, titulo in (("lista_espera", "Resultados (lista de espera)"), ("no_factible", "Resultados (no factible)")):
        aviso.datos = {**aviso.datos, "resultado": resultado}
        assert aviso.tipo_texto == titulo
