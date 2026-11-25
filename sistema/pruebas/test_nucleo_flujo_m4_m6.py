"""Núcleo · estados y transiciones de M4 (Ejecución y verificación) y M6 (Seguimiento y cierre) (S3-02b). Solo la tabla:
las acciones con sus documentos, acuses y plazos las construyen las historias HU-4.x y HU-6.x."""
import pytest

from nucleo.models import Ejercicio, Estado, Expediente, Transicion, TransicionNoPermitida, bandeja

pytestmark = pytest.mark.django_db

ESTADOS_M4 = {"en_ejecucion", "comprobacion_enviada", "verificada", "reporte_entregado", "reportes_evaluados", "concluida"}
ESTADOS_M6 = {"caso_fortuito", "suspendida", "omisiones_por_subsanar", "cancelada", "en_devolucion", "reintegrada",
              "sustitucion", "prorroga_solicitada", "ejercicio_cerrado"}


@pytest.fixture
def en_estado(nueva_solicitud):
    def _crear(programa, estado):
        exp = nueva_solicitud()
        Expediente.objects.filter(pk=exp.pk).update(ejercicio=Ejercicio.objects.get(programa__clave=programa, anio=2026),
                                                    estado=Estado.objects.get(clave=estado))
        return Expediente.objects.get(pk=exp.pk)
    return _crear


def _pasar(exp, destino, usuario, motivo=""):
    exp.cambiar_estado(destino, usuario, motivo=motivo)
    exp.refresh_from_db()
    assert exp.estado.clave == destino
    assert exp.eventos.filter(estado_destino__clave=destino, usuario=usuario).exists()
    return exp


def _atienden(exp, usuarios):
    return {n for n, u in usuarios.items() if u.unidad_id and exp in bandeja(u)}


def test_nucleo_estados_de_m4_y_m6_con_su_unidad_y_flujo_alterno():
    estados = {e.clave: e for e in Estado.objects.all()}
    assert (ESTADOS_M4 | ESTADOS_M6) <= set(estados)
    for clave in (ESTADOS_M4 | ESTADOS_M6) - {"ejercicio_cerrado"}:
        assert estados[clave].tipos_bandeja and not estados[clave].final, clave
        assert estados[clave].orden > 88, clave          # después de los de pago: el monto aprobado sigue valiendo
    assert estados["ejercicio_cerrado"].final
    letras = {c: estados[c].flujo_alterno for c in ESTADOS_M6 - {"ejercicio_cerrado"}}
    assert letras["caso_fortuito"] == "D" and letras["sustitucion"] == "F" and letras["prorroga_solicitada"] == "G"
    assert {letras[c] for c in ("omisiones_por_subsanar", "cancelada", "en_devolucion", "reintegrada", "suspendida")} == {"E"}
    assert estados["sin_firma_en_plazo"].flujo_alterno == "E"   # baja por no firmar: incumplimiento (D es el caso fortuito)


def test_nucleo_cc_ejecucion_comprobacion_verificacion_y_cierre(en_estado, usuarios):
    u = usuarios
    exp = en_estado("CC", "pagada")
    pasos = [
        ("en_ejecucion", "dir_drff", {"del_amecameca"}),
        ("comprobacion_enviada", "del_amecameca", {"del_amecameca", "dir_drff"}),
        ("verificada", "del_amecameca", {"dir_drff"}),
        ("ministracion_solicitada", "dir_drff", {"finanzas"}),   # segunda ministración con la verificación
        ("pagada", "finanzas", {"dir_drff"}),
        ("concluida", "dir_drff", {"dir_drff"}),
        ("ejercicio_cerrado", "dir_drff", set()),
    ]
    for destino, quien, atienden in pasos:
        _pasar(exp, destino, u[quien])
        assert _atienden(exp, u) == atienden, destino
    assert exp.estado.final


def test_nucleo_devolver_la_comprobacion_pide_motivo(en_estado, usuarios):
    from django.core.exceptions import ValidationError

    exp = en_estado("PS", "comprobacion_enviada")
    with pytest.raises(ValidationError):
        exp.cambiar_estado("en_ejecucion", usuarios["dir_drff"])
    _pasar(exp, "en_ejecucion", usuarios["dir_drff"], motivo="Falta el informe firmado")


def test_nucleo_peg_reportes_por_periodo_y_su_evaluacion(en_estado, usuarios):
    u = usuarios
    exp = en_estado("PEG", "contratada")
    pasos = [
        ("en_ejecucion", "dir_dpf", {"del_amecameca"}),           # reporta desde el mes de la firma
        ("reporte_entregado", "del_amecameca", {"dir_dpf"}),
        ("reportes_evaluados", "dir_dpf", {"comite"}),
        ("en_ejecucion", "comite", {"del_amecameca"}),            # el CASPEG valida el periodo
        ("ministracion_solicitada", "dir_dpf", {"finanzas"}),
    ]
    for destino, quien, atienden in pasos:
        _pasar(exp, destino, u[quien])
        assert _atienden(exp, u) == atienden, destino
    cc = en_estado("CC", "en_ejecucion")
    with pytest.raises(TransicionNoPermitida):                    # los reportes mensuales son solo de PEG
        cc.cambiar_estado("reporte_entregado", u["del_amecameca"])


def test_nucleo_caso_fortuito_suspension_cancelacion_y_reintegro(en_estado, usuarios):
    u = usuarios
    exp = en_estado("RHF", "en_ejecucion")
    _pasar(exp, "caso_fortuito", u["del_amecameca"])
    assert _atienden(exp, u) == {"dir_drff"}
    _pasar(exp, "suspendida", u["comite"], motivo="Acuerdo del Comité: suspensión por incendio")
    assert _atienden(exp, u) == {"comite"}
    _pasar(exp, "cancelada", u["comite"], motivo="Acuerdo del Comité: cancelación")
    assert _atienden(exp, u) == {"juridica"}
    _pasar(exp, "en_devolucion", u["juridica"])
    assert _atienden(exp, u) == {"finanzas"}
    _pasar(exp, "reintegrada", u["finanzas"])
    _pasar(exp, "ejercicio_cerrado", u["dir_drff"])
    mfs = en_estado("MFS", "en_ejecucion")
    with pytest.raises(TransicionNoPermitida):                    # MFS no prevé caso fortuito (R-17)
        mfs.cambiar_estado("caso_fortuito", u["del_amecameca"])


def test_nucleo_omisiones_por_subsanar_y_sustitucion(en_estado, usuarios):
    u = usuarios
    exp = en_estado("CC", "verificada")
    _pasar(exp, "omisiones_por_subsanar", u["dir_drff"], motivo="Falta el informe de sobrevivencia")
    assert _atienden(exp, u) == {"del_amecameca", "dir_drff"}
    _pasar(exp, "en_ejecucion", u["dir_drff"])
    _pasar(exp, "sustitucion", u["del_amecameca"])
    assert _atienden(exp, u) == {"dir_drff", "comite"}
    _pasar(exp, "baja", u["comite"], motivo="Desistimiento: el recurso pasa a la lista de espera")
    assert exp.estado.final


def test_nucleo_prorroga_solo_en_mfs(en_estado, usuarios):
    u = usuarios
    exp = en_estado("MFS", "en_ejecucion")
    _pasar(exp, "prorroga_solicitada", u["del_amecameca"])
    assert _atienden(exp, u) == {"dir_drff"}
    _pasar(exp, "en_ejecucion", u["dir_drff"], motivo="Autorizada con adendum: 60 días")
    ps = en_estado("PS", "en_ejecucion")
    with pytest.raises(TransicionNoPermitida):
        ps.cambiar_estado("prorroga_solicitada", u["del_amecameca"])
    assert not Transicion.objects.filter(destino__clave="prorroga_solicitada").exclude(programa__clave="MFS").exists()
