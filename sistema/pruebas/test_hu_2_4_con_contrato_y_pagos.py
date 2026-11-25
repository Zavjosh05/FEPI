"""HU-2.4 (reasignaciones e incidentes) junto con M3 (publicación y contrato) y M5 (pagos): la persona dada de baja no
firma, no recibe planta ni cobra; el recurso que se libera por no firmar en plazo (HU-3.3) se reasigna igual que el de una
baja; la reasignación se publica (HU-3.1) y la vista de Beneficiarios (HU-2.3) sigue a la persona en todo el trámite."""
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from contrato import contratos, firma, publicacion
from contrato.models import SinFirma
from dictamen import listados, seguimiento, sesiones
from dictamen.models import MovimientoListado, TipoSesion
from nucleo.models import Hito, Notificacion, expedientes_visibles
from pagos import solicitudes

from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de
from .fixtures_m5 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def _seguimiento(usuarios, ejercicio):
    s = sesiones.crear_sesion(usuarios["comite"], ejercicio, TipoSesion.SEGUIMIENTO, fecha_sesion(6), "Sala",
                              "Quórum\nSeguimiento de casos")
    sesiones.agregar_documento(usuarios["comite"], s, documento_sesion(), "Casos")
    sesiones.enviar_convocatoria(usuarios["comite"], s)
    return s


def _baja(usuarios, exp, sesion=None):
    sesion = sesion or _seguimiento(usuarios, exp.ejercicio)
    acuerdo = seguimiento.registrar_acuerdo(usuarios["comite"], sesion, "desistimiento", "Se acepta el desistimiento",
                                            [exp], causa="Escrito de desistimiento")
    exp.refresh_from_db()
    return acuerdo


def _vencer(exp, dias=40):
    Hito.objects.filter(expediente=exp, clave="publicacion_resultados").update(
        fecha_hora=timezone.now() - timedelta(days=dias))
    Notificacion.objects.filter(expediente=exp, tipo="resultados").update(
        notificada_en=timezone.now() - timedelta(days=dias), enviada_en=timezone.now() - timedelta(days=dias + 1))


def test_hu_2_4_la_persona_dada_de_baja_ya_no_firma_el_contrato(en_delegacion, usuarios, pdf):
    _, (exp,) = en_delegacion("PS")
    a = _baja(usuarios, exp)
    assert exp.estado.clave == "baja" and a.monto_liberado and seguimiento.recurso_liberado(exp.ejercicio) == a.monto_liberado
    m = MovimientoListado.objects.get(acuerdo=a)
    assert m.estado_anterior == "contrato_en_delegacion" and m.estado_nuevo == "baja"
    with pytest.raises(ValidationError, match="dada de baja por acuerdo del Comité"):
        firma.registrar_firma(delegado_de(usuarios, exp), exp, None, "persona", exp.solicitante.nombre, pdf("f.pdf"),
                              [p["clave"] for p in firma.puntos_de_verificacion(exp)])


def test_hu_2_4_la_persona_dada_de_baja_con_contrato_firmado_ya_no_cobra(contratadas, usuarios):
    _, (exp,) = contratadas("CC")
    _baja(usuarios, exp)
    assert exp.estado.clave == "baja"
    with pytest.raises(ValidationError, match="dada de baja"):
        solicitudes.emitir_oficio(delegado_de(usuarios, exp), exp)
    puede, motivo = solicitudes.puede_solicitar(exp, 1)
    assert not puede and "dada de baja" in motivo
    assert exp not in [f["exp"] for f in solicitudes.por_solicitar(usuarios["dir_drff"])]


def test_hu_2_4_con_una_ministracion_solicitada_no_hay_baja_sino_reintegro(solicitada, usuarios):
    exp = solicitada("CC")
    with pytest.raises(ValidationError, match="procede el reintegro"):
        _baja(usuarios, exp)
    assert exp.estado.clave == "ministracion_solicitada"


def test_hu_2_4_el_recurso_liberado_por_no_firmar_en_plazo_se_reasigna(notificadas, modelo_validado, usuarios):
    """HU-3.3 + HU-2.4: al confirmar la liberación, el monto queda como recurso liberado; el Comité lo reasigna a la primera
    de la lista de espera, y como los listados ya se publicaron, la reasignación se publica con el acta de seguimiento."""
    sesion, (beneficiaria, espera) = notificadas("CC", cuantas=2, presupuesto=12000)
    assert (beneficiaria.estado.clave, espera.estado.clave) == ("notificada", "lista_espera")
    contratos.enviar_a_delegacion(usuarios["dir_drff"], contratos.elaborar_contrato(
        usuarios["dir_drff"], beneficiaria, modelo_validado(beneficiaria.ejercicio)))
    _vencer(beneficiaria)
    assert firma.revisar_firmas(timezone.localdate()) == 1
    assert seguimiento.recurso_liberado(beneficiaria.ejercicio) == 0
    firma.liberar_recurso(usuarios["dir_drff"], beneficiaria, "La persona no acudió a firmar.")
    liberado = seguimiento.recurso_liberado(beneficiaria.ejercicio)
    mov = MovimientoListado.objects.get(expediente=beneficiaria)
    assert mov.acuerdo is None and mov.monto == liberado > 0 and mov.usuario == usuarios["dir_drff"]
    assert mov.history.get().history_user == usuarios["dir_drff"]

    seg = _seguimiento(usuarios, espera.ejercicio)
    a = seguimiento.registrar_acuerdo(usuarios["comite"], seg, "reasignacion", "Reasignar el recurso liberado", [espera])
    espera.refresh_from_db()
    assert espera.estado.clave == "aprobada" and a.monto_reasignado == liberado
    assert seguimiento.recurso_liberado(espera.ejercicio) == 0
    assert publicacion.sesion_de_expediente(espera) == seg          # el acta de aprobación ya se publicó
    seguimiento.cerrar_sesion(usuarios["comite"], seg, "Cierre", momento=despues_de(seg))
    seg.refresh_from_db()
    assert seg.autoriza_publicacion and seg in publicacion.sesiones_por_publicar(usuarios["dir_drff"])
    pub = publicacion.publicar(usuarios["dir_drff"], seg, momento=seg.acta_fecha + timedelta(minutes=5))
    espera.refresh_from_db()
    assert espera.estado.clave == "publicada" and pub.renglones.get().expediente == espera
    assert espera.notificaciones.filter(tipo="resultados", datos__publicacion=pub.pk).exists()
    assert espera.hitos.filter(clave="publicacion_resultados").count() == 2   # lista de espera y luego reasignación
    publicos = list(publicacion.renglones_publicos(espera.ejercicio))
    assert [r.resultado for r in publicos if r.expediente_id == espera.pk] == ["beneficiaria"]
    with pytest.raises(ValidationError, match="ya se publicaron"):
        publicacion.publicar(usuarios["dir_drff"], seg, momento=seg.acta_fecha + timedelta(minutes=6))


def test_hu_2_4_la_baja_y_la_reasignacion_antes_de_publicar_se_reflejan_en_la_publicacion(aprobadas, usuarios):
    sesion, (beneficiaria, espera) = aprobadas("CC", cuantas=2, presupuesto=12000)
    seg = _seguimiento(usuarios, sesion.ejercicio)
    _baja(usuarios, beneficiaria, seg)
    seguimiento.registrar_acuerdo(usuarios["comite"], seg, "reasignacion", "Reasignar", [espera])
    espera.refresh_from_db()
    assert publicacion.sesion_de_expediente(espera) == sesion      # todavía no se publica el acta de aprobación
    pub = publicacion.publicar(usuarios["dir_drff"], sesion)
    beneficiaria.refresh_from_db()
    espera.refresh_from_db()
    assert {r.expediente: r.resultado for r in pub.renglones.all()} == {espera: "beneficiaria"}
    assert beneficiaria.estado.clave == "baja" and espera.estado.clave == "publicada"
    assert pub.renglones.get().persona == espera.solicitante.nombre

    # La vista de Beneficiarios (HU-2.3) sigue a la persona después de la publicación y muestra la baja.
    vigentes, bajas = listados.beneficiarios(sesion.ejercicio, expedientes_visibles(usuarios["dir_drff"]))
    assert [f["expediente"] for f in vigentes] == [espera]
    assert vigentes[0]["reasignada"] and vigentes[0]["publicada_en"] == pub.publicada_en
    assert vigentes[0]["situacion"] == espera.estado.nombre
    assert [b["expediente"] for b in bajas] == [beneficiaria]


def test_hu_2_4_la_baja_desde_sin_firma_en_plazo_cierra_el_pendiente_de_liberar(en_delegacion, usuarios):
    _, (exp,) = en_delegacion("PS")
    _vencer(exp)
    firma.revisar_firmas(timezone.localdate())
    exp.refresh_from_db()
    assert exp.estado.clave == "sin_firma_en_plazo" and SinFirma.objects.filter(expediente=exp).exists()
    assert firma.sin_firma(usuarios["dir_drff"]).filter(expediente=exp).exists()
    _baja(usuarios, exp)
    assert exp.estado.clave == "baja" and not firma.sin_firma(usuarios["dir_drff"]).filter(expediente=exp).exists()
    with pytest.raises(ValidationError, match="Solo se libera"):
        firma.liberar_recurso(usuarios["dir_drff"], exp, "Motivo")
