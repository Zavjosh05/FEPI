"""Núcleo y M1–M5 con Manejo Forestal Sustentable y Guardabosques (S3-02a): lo que cambia al generalizar con sus
reglas reales (R-17 y R-18)."""
from datetime import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from contrato import firma
from dictamen import sesiones
from dictamen.models import CaracterSesion, TipoSesion
from nucleo import plazos, reglas
from nucleo.models import Ejercicio, Municipio
from pagos import solicitudes
from recepcion import servicios as recepcion
from recepcion.forms import RegistroSolicitudForm

from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m2 import registrar_peg, registrar_validada
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m5 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def _datos_peg(peg, **kw):
    base = dict(ejercicio=peg, municipio=Municipio.objects.get(nombre="Amecameca"), nombre_predio="Ejido San Juan",
                tipo_persona=peg.tipos_persona.get(clave="nucleo_agrario"),
                modalidad=peg.modalidades.get(clave="apoyo_monetario_guardabosque"), solicitante_nombre="Ejido San Juan",
                solicitante_tipo="nucleo_agrario", beneficiaria_nombre="Margarito Sánchez Ruiz",
                beneficiaria_curp="sarm800101hmcnzr09")
    base.update(kw)
    return recepcion.DatosSolicitud(**base)


# ----------------------------------------------------------------------------- PEG: quién solicita y quién recibe
def test_peg_solicita_el_nucleo_agrario_y_el_guardabosque_es_la_persona_beneficiaria(peg, usuarios):
    exp = recepcion.registrar_solicitud(usuarios["del_amecameca"], _datos_peg(peg))
    assert exp.solicitante.nombre == "Ejido San Juan" and exp.beneficiaria.nombre == "Margarito Sánchez Ruiz"
    assert exp.persona_beneficiaria.tipo == "guardabosque" and exp.persona_beneficiaria.curp == "SARM800101HMCNZR09"
    # Los requisitos del núcleo agrario (8.1.1.2 a) y del Guardabosque (8.1.1.2 b) están en el mismo expediente.
    claves = set(exp.revisiones.values_list("requisito__clave", flat=True))
    assert {"PEG-REQ-01", "PEG-REQ-07", "PEG-REQ-09"} <= claves
    assert "Margarito Sánchez Ruiz" in str(exp.acuses.get(tipo="recepcion").contenido)


def test_peg_el_guardabosque_no_registra_la_solicitud_y_sin_el_no_se_recibe(peg, usuarios):
    deleg = usuarios["del_amecameca"]
    with pytest.raises(ValidationError, match="no presenta la solicitud"):
        recepcion.registrar_solicitud(deleg, _datos_peg(peg, tipo_persona=peg.tipos_persona.get(clave="guardabosque")))
    with pytest.raises(ValidationError, match="Guardabosque designado"):
        recepcion.registrar_solicitud(deleg, _datos_peg(peg, beneficiaria_nombre=""))
    form = RegistroSolicitudForm(initial={"ejercicio": peg.pk})
    assert list(form.fields["tipo_persona"].queryset.values_list("clave", flat=True)) == ["nucleo_agrario"]
    assert form.beneficiaria["tipo_persona"] == "guardabosque"
    cc = Ejercicio.objects.get(programa__clave="CC", anio=2026)
    assert RegistroSolicitudForm(initial={"ejercicio": cc.pk}).beneficiaria is None


def test_peg_pantalla_de_registro_pide_al_guardabosque(peg, usuarios, client, contrasena):
    client.login(username="del_amecameca", password=contrasena)
    html = client.get(f"/recepcion/registrar/?ejercicio={peg.pk}", HTTP_HX_REQUEST="true").content.decode()
    assert 'data-prueba="persona-beneficiaria"' in html and "Guardabosque designado por la Asamblea" in html


def test_peg_faltantes_sin_plazo_en_las_reglas_y_10_dias_naturales_para_notificar(peg, usuarios):
    exp = recepcion.registrar_solicitud(usuarios["del_amecameca"], _datos_peg(peg))
    v = plazos.vencimiento(exp, "faltantes_ventanilla")
    assert v.vencimiento is None and v.estado() == plazos.SIN_PLAZO and v.texto.startswith(plazos.SIN_PLAZO)
    n = plazos.vencimiento(exp, "notificacion_faltantes")
    assert n.plazo.cantidad == 10 and n.plazo.unidad == "dias_naturales" and n.decision_propia
    assert (n.vencimiento - timezone.localtime(exp.fecha_recepcion).date()).days >= 10
    cc = Ejercicio.objects.get(programa__clave="CC", anio=2026)
    assert "notificacion_faltantes" not in plazos.usos_configurados(cc.programa.clave)


def test_peg_firma_corre_desde_la_aprobacion_del_caspeg(peg, usuarios):
    exp = registrar_peg(usuarios, peg)
    assert plazos.vencimiento(exp, "firma_programada").vencimiento is None   # aún no aprueba el CASPEG
    aprobada = timezone.make_aware(datetime(2026, 7, 14, 12, 0))
    plazos.registrar_hito(exp, "aprobacion_comite", usuarios["comite"], aprobada)
    for uso in ("firma_programada", "firma_liberacion"):
        v = plazos.vencimiento(exp, uso)
        assert v.evento == "aprobacion_comite" and str(v.vencimiento) == "2026-07-28"   # 10 días hábiles
        assert "la aprobación del Comité" in v.texto


def test_peg_caspeg_convoca_con_5_dias_habiles_o_1_dia_si_es_extraordinaria(peg, usuarios):
    s = sesiones.crear_sesion(usuarios["comite"], peg, TipoSesion.SEGUIMIENTO,
                              timezone.make_aware(datetime(2026, 7, 17, 11, 0)), "Sala", "Quórum")
    texto, limite = sesiones.anticipacion_requerida(s)
    assert "5 días hábiles" in texto and str(timezone.localtime(limite).date()) == "2026-07-10"
    e = sesiones.crear_sesion(usuarios["comite"], peg, TipoSesion.SEGUIMIENTO,
                              timezone.make_aware(datetime(2026, 7, 17, 11, 0)), "Sala", "Quórum",
                              caracter=CaracterSesion.EXTRAORDINARIA)
    texto, limite = sesiones.anticipacion_requerida(e)
    assert texto.startswith("1 día hábil") and str(timezone.localtime(limite).date()) == "2026-07-16"
    integrantes = sesiones.integrantes_comite(peg)
    assert "CASPEG" in integrantes["nombre"] and "Órgano Interno de Control" in integrantes["invitados"]
    assert all(len(i) > 3 for i in integrantes["invitados"])   # textos completos, no letras sueltas


def test_peg_firma_del_guardabosque_y_del_nucleo_agrario(peg, contrato_manual):
    exp = contrato_manual(peg, direccion="dir_dpf", **PEG_SOLICITUD)
    claves = [p["clave"] for p in firma.puntos_de_verificacion(exp)]
    assert claves[0] == "firma_guardabosque" and "sello_nucleo" in claves


def test_peg_la_evaluacion_de_reportes_validada_condiciona_cada_ministracion(peg_contratado, usuarios):
    exp = peg_contratado()                      # con un periodo validado por el CASPEG
    assert all(s["cumple"] for s in solicitudes.soportes(exp, 1))
    segunda = {s["clave"]: s for s in solicitudes.soportes(exp, 2)}["evaluacion_reportes"]
    assert not segunda["cumple"] and "HU-4.3" in segunda["detalle"] + segunda["responsable"]


# ----------------------------------------------------------------------------- MFS
def test_mfs_rango_de_superficie_por_modalidad_de_sus_reglas(mfs):
    r = reglas.rango_superficie(mfs, mfs.modalidades.get(clave="etf_pmf_maderable_7_95"))
    assert r["minima_ha"] == 7 and r["maxima_ha"] == 95 and reglas.en_rango(r, 40) and not reglas.en_rango(r, 7)
    assert reglas.en_rango(r, 95) and not reglas.en_rango(r, 96) and "mayor de 7" in r["texto"]
    r = reglas.rango_superficie(mfs, mfs.modalidades.get(clave="etf_pmf_maderable_mayor_250"))
    assert reglas.en_rango(r, 300) and not reglas.en_rango(r, 250)
    r = reglas.rango_superficie(mfs, mfs.modalidades.get(clave="fsc_certificacion_cadena_custodia"))
    assert reglas.en_rango(r, 1) is None        # las certificaciones no tienen rango en las reglas


def test_mfs_firma_programada_sin_pasar_del_15_de_julio(mfs, usuarios):
    exp = registrar_validada(usuarios, mfs, modalidad="etf_pmf_maderable_7_95", ha=40)
    v = plazos.vencimiento(exp, "firma_programada", fecha_evento=timezone.make_aware(datetime(2026, 7, 10, 10)))
    assert v.topado and str(v.vencimiento) == "2026-07-15"
    libre = plazos.vencimiento(exp, "firma_liberacion", fecha_evento=timezone.make_aware(datetime(2026, 7, 10, 10)))
    assert not libre.topado and libre.vencimiento > v.vencimiento     # la baja: 10 días hábiles (8.1.9.2 e)


def test_mfs_segunda_ministracion_contra_bitacora_o_auditoria_segun_el_regimen(mfs, usuarios):
    etf = registrar_validada(usuarios, mfs, modalidad="etf_pmf_maderable_7_95", ha=40, nombre="ETF")
    fsc = registrar_validada(usuarios, mfs, modalidad="fsc_certificacion_cadena_custodia", ha=12, nombre="FSC")
    assert [s["clave"] for s in solicitudes.soportes_requeridos(etf, 2)][-1] == "entregable_etf"
    assert [s["clave"] for s in solicitudes.soportes_requeridos(fsc, 2)][-1] == "entregable_fsc"
    assert "auditoría" in solicitudes.soportes_requeridos(fsc, 2)[-1]["nombre"]
    falta = solicitudes.soportes(etf, 2)[-1]
    assert not falta["cumple"] and "HU-4.1" in falta["detalle"]
    assert "comprobante_cuenta" in [s["clave"] for s in solicitudes.soportes_requeridos(etf, 1)]


def test_mfs_y_peg_el_contrato_dice_su_base_de_monto(en_delegacion):
    _, (mfs_exp,) = en_delegacion("MFS")
    _, (peg_exp,) = en_delegacion("PEG")
    m = mfs_exp.contrato.datos
    assert m["base_del_monto"] == "$30,000.00 por apoyo" and m["superficie_texto"] == ""
    assert "por hectárea" not in mfs_exp.contrato.texto
    p = peg_exp.contrato.datos
    assert p["persona"] == "Margarito Sánchez Ruiz" and "Ejido San Juan" in p["tipo_persona"]
    assert p["monto_total"] == "$25,550.00" and "25 %" in p["ministraciones"]
    assert Decimal(p["superficie_ha"]) == 0
