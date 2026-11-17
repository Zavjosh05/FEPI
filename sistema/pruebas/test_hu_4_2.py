"""HU-4.2 · Verificación en campo (resultado con superficie y ajuste dentro del plazo de entrega; incidencias con su tipo y
documento) y su efecto en la segunda ministración."""
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from ejecucion import comprobaciones, verificacion
from ejecucion.models import Verificacion
from nucleo import extensiones, montos, reloj
from nucleo.models import Hito
from pagos import solicitudes

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de
from .fixtures_m4 import *  # noqa: F401,F403
from .fixtures_m5 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db
CONTRATO = "2026-08-03 10:00"


def _por_verificar(pagada, usuarios, programa, cuando="2026-09-25 10:00", termino=date(2026, 9, 24), **kw):
    """Expediente con la primera ministración pagada y su comprobación entregada en ventanilla (por verificar)."""
    with reloj.en(CONTRATO):
        exps = pagada(programa, **kw)
    lista = exps if isinstance(exps, list) else [exps]
    with reloj.en(cuando):
        for exp in lista:
            tipos = [t["clave"] for t in comprobaciones.tipos_de_envio(exp)]
            tipo = next(t for t in ("aviso_termino", "informe_final", "bitacora_etf") if t in tipos)
            comprobaciones.registrar_envio(delegado_de(usuarios, exp), exp, tipo, archivo=_archivo(f"{tipo}.pdf"),
                                           fecha_hecho=termino if tipo == "aviso_termino" else None)
            exp.refresh_from_db()
            assert exp.estado.clave == "comprobacion_enviada"
    return exps


def _archivo(nombre):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from nucleo.demo import _pdf_demo
    return SimpleUploadedFile(nombre, _pdf_demo(nombre), content_type="application/pdf")


def test_hu_4_2_criterios_y_necesidades_vienen_del_modelo(modelo, necesidades):
    hu = historia(modelo, "HU-4.2")
    assert hu["criterios"] == ["Existe el resultado de la verificación con la superficie verificada y su ajuste, dentro del "
                               "plazo del programa.", "Cada incidencia tiene su tipo y el documento que la avala."]
    funcion = next(f for m in modelo["modulos"] for f in m["funciones"] if f["id"] == "M4.2")
    assert {"CC-DRF-03", "CC-DRF-04", "MFS-DRF-03", "PS-DRF-04", "PS-DRF-05", "RHF-DRF-04", "PSA-DRF-04"} == set(funcion["necesidades"])
    assert "15 días hábiles" in necesidades["CC-DRF-03"]["texto"] and "10 días hábiles" in necesidades["RHF-DRF-04"]["texto"]


# ----------------------------------------------------------------------------- criterio 1
def test_hu_4_2_resultado_con_superficie_verificada_y_ajuste_dentro_del_plazo(pagada, usuarios):
    """Criterio 1 (CC, 6 ha). La Delegación entrega el Informe Final firmado con 5.4 ha verificadas: ajuste del 90 %, en
    plazo (15 días hábiles desde el 13-nov, 7-dic), acuse, hito y estado «verificada». La segunda ministración es la parte
    proporcional: 5.4 ha × $2,000 = $10,800 menos los $8,400 ya ministrados = $2,400 (ROP CC 7.2, líneas 4098 a 4100)."""
    exp = _por_verificar(pagada, usuarios, "CC", "2026-11-12 10:00", date(2026, 11, 11))
    deleg = delegado_de(usuarios, exp)
    with reloj.en("2026-11-20 13:00"):
        v = verificacion.registrar_verificacion(deleg, exp, "informe_final_firmado", _archivo("informe_firmado.pdf"),
                                                fecha_visita=date(2026, 11, 18), superficie_verificada="5.4")
    assert v.superficie_aprobada_ha == 6 and v.superficie_verificada_ha == Decimal("5.4") and v.ajuste_pct == Decimal("90.00")
    assert v.resultado == "ajuste" and v.en_plazo is True and v.vence == date(2026, 12, 7)
    assert v.importe_ajustado == Decimal("2400.00") and v.ministracion_ajustada == 2 and v.excedente_ministrado == 0
    renglones = dict(v.acuse.contenido["renglones"])
    assert renglones["Ajuste respecto de la aprobada"] == "90 %" and renglones["Fecha y hora de entrega"].startswith("20/11/2026 13:00")
    assert v.acuse.tipo == "verificacion_campo" and Hito.objects.filter(expediente=exp, clave="verificacion_campo").exists()
    exp.refresh_from_db()
    assert exp.estado.clave == "verificada" and exp.eventos.filter(estado_destino__clave="verificada", usuario=deleg).exists()
    m = montos.monto_aprobado(exp)
    assert [x.importe for x in m.ministraciones] == [Decimal("8400.00"), Decimal("2400.00")] and m.ajuste["proporcional"]
    assert montos.monto_aprobado(exp, superficie=6).ministraciones[1].importe == Decimal("3600.00")   # lo aprobado no cambia
    soporte = next(s for s in solicitudes.soportes(exp, 2) if s["clave"] == "verificacion_campo")
    assert soporte["cumple"] and soporte["referencia"] == v.acuse.folio
    with reloj.en("2026-11-23 10:00"):
        sol = solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 2)
    assert sol.importe == Decimal("2400.00") and sol.porcentaje == 30


def test_hu_4_2_fuera_de_plazo_se_registra_y_queda_senalado(pagada, usuarios):
    exp = _por_verificar(pagada, usuarios, "PS")
    assert verificacion.vigente(exp) is None
    with reloj.en("2026-11-25 10:00"):   # PS: 30 días hábiles desde el 30-sep vencen el 12-nov
        v = verificacion.registrar_verificacion(delegado_de(usuarios, exp), exp, "formato_verificacion", _archivo("f.pdf"),
                                                superficie_verificada="4")
    assert v.en_plazo is False and v.vence == date(2026, 11, 12) and v.resultado == "cumple"
    assert "Fuera de plazo" in v.acuse.contenido["nota"] and v.importe_ajustado == montos.monto_aprobado(exp).ministraciones[1].importe


def test_hu_4_2_rhf_modalidad_uno_entrega_en_plazo_desde_octubre(pagada, usuarios, monkeypatch):
    monkeypatch.setitem(SOLICITUDES_M3, "RHF", [("del_amecameca", "Ozumba", "Cañada Uno", "Raquel Montes Alba", "rfi_modalidad_uno", 3)])
    exp = _por_verificar(pagada, usuarios, "RHF", "2026-10-28 10:00", date(2026, 10, 27))
    with reloj.en("2026-11-13 10:00"):
        v = verificacion.registrar_verificacion(delegado_de(usuarios, exp), exp, "formato_verificacion", _archivo("f.pdf"),
                                                superficie_verificada="3", sobrevivencia="85")
    assert v.en_plazo is True and v.vence == date(2026, 11, 17) and v.sobrevivencia_pct == 85


def test_hu_4_2_un_ajuste_menor_al_70_por_ciento_es_incumplimiento_y_bloquea_el_pago(pagada, usuarios):
    exp = _por_verificar(pagada, usuarios, "RHF")
    with reloj.en("2026-10-05 10:00"):
        v = verificacion.registrar_verificacion(delegado_de(usuarios, exp), exp, "formato_verificacion", _archivo("f.pdf"),
                                                superficie_verificada="1.5")     # 1.5 de 3 ha: 50 %
    assert v.resultado == "incumplimiento" and "menor al 70 %" in v.datos["motivos_incumplimiento"][0]
    assert v.importe_ajustado == 0 and v.excedente_ministrado > 0                 # lo ministrado de más: HU-6.2
    cumple, detalle, *_ = verificacion.fuente_verificacion(exp, 2)
    assert not cumple and "HU-6.2" in detalle
    with pytest.raises(ValidationError, match="incumplimiento"):
        solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 2)


def test_hu_4_2_ps_mantenimiento_pide_la_sobrevivencia_minima_del_50(pagada, usuarios, monkeypatch):
    monkeypatch.setitem(SOLICITUDES_M3, "PS", [SOLICITUDES_M3["PS"][1]])     # Rancho La Huerta: mantenimiento
    exp = _por_verificar(pagada, usuarios, "PS")
    deleg = delegado_de(usuarios, exp)
    with reloj.en("2026-10-05 10:00"):
        with pytest.raises(ValidationError, match="Falta la sobrevivencia"):
            verificacion.registrar_verificacion(deleg, exp, "formato_verificacion", _archivo("f.pdf"), superficie_verificada="2.5")
        v = verificacion.registrar_verificacion(deleg, exp, "formato_verificacion", _archivo("f.pdf"),
                                                superficie_verificada="2.5", sobrevivencia="40")
    assert v.resultado == "incumplimiento" and "sobrevivencia" in v.datos["motivos_incumplimiento"][0]


# ----------------------------------------------------------------------------- criterio 2
def test_hu_4_2_cada_incidencia_tiene_su_tipo_y_el_documento_que_la_avala(pagada, usuarios, monkeypatch):
    """Criterio 2. Sin documento la incidencia no se registra; cada una queda con su tipo, su descripción y su documento,
    en el acuse; la de incumplimiento corre el gancho de HU-6.2 y la verificación queda en incumplimiento."""
    exp = _por_verificar(pagada, usuarios, "PS")
    deleg = delegado_de(usuarios, exp)
    avisadas = []
    monkeypatch.setattr(extensiones, "AL_INCIDENCIA", [avisadas.append])
    with reloj.en("2026-10-05 10:00"):
        with pytest.raises(ValidationError, match="necesita el documento"):
            verificacion.registrar_verificacion(deleg, exp, "formato_verificacion", _archivo("f.pdf"), superficie_verificada="3.6",
                                                incidencias=[{"tipo": "caso_fortuito", "descripcion": "Helada"}])
        with pytest.raises(ValidationError, match="no válido"):
            verificacion.registrar_verificacion(deleg, exp, "formato_verificacion", _archivo("f.pdf"), superficie_verificada="3.6",
                                                incidencias=[{"tipo": "causa_externa", "descripcion": "x", "archivo": _archivo("x.pdf")}])
        v = verificacion.registrar_verificacion(
            deleg, exp, "formato_verificacion", _archivo("f.pdf"), superficie_verificada="3.6", incidencias=[
                {"tipo": "caso_fortuito", "descripcion": "Helada en 0.4 ha", "archivo": _archivo("acta_helada.pdf")},
                {"tipo": "incumplimiento", "descripcion": "Planta concentrada en una fracción", "archivo": _archivo("fotos.pdf")}])
    incs = list(v.incidencias.order_by("id"))
    assert [(i.tipo, bool(i.archivo), len(i.huella)) for i in incs] == [("caso_fortuito", True, 64), ("incumplimiento", True, 64)]
    assert incs[0].nombre_tipo.startswith("Caso fortuito") and incs[0].expediente == exp
    assert [d["clave"] for d in v.acuse.contenido["detalle"]] == [i.nombre_tipo for i in incs]
    assert avisadas == incs and v.resultado == "incumplimiento"


# ----------------------------------------------------------------------------- otros programas
def test_hu_4_2_psahem_no_es_proporcional_y_paga_el_30_por_ciento(pagada, usuarios):
    exp = _por_verificar(pagada, usuarios, "PSA")
    with reloj.en("2026-10-05 10:00"):
        v = verificacion.registrar_verificacion(delegado_de(usuarios, exp), exp, "minuta_verificacion", _archivo("minuta.pdf"),
                                                superficie_verificada="27")      # 27 de 30 ha: 90 %
    assert v.resultado == "ajuste" and v.importe_ajustado is None and v.en_plazo is None    # sin plazo en las reglas
    m = montos.monto_aprobado(exp)
    assert m.ministraciones[1].importe == Decimal("31500.00") and "PSAHEM" in m.nota       # 30 % de $105,000


def test_hu_4_2_mfs_el_area_responsable_revisa_la_bitacora_y_paga_la_segunda(pagada, usuarios):
    exp = _por_verificar(pagada, usuarios, "MFS")
    with pytest.raises(PermissionDenied):
        verificacion.registrar_verificacion(delegado_de(usuarios, exp), exp, "revision_entregable", _archivo("r.pdf"))
    with reloj.en("2026-10-01 10:00"):
        v = verificacion.registrar_verificacion(usuarios["dir_drff"], exp, "revision_entregable", _archivo("revision.pdf"))
    assert v.superficie_verificada_ha is None and v.resultado == "cumple" and v.importe_ajustado is None
    exp.refresh_from_db()
    assert exp.estado.clave == "verificada"
    with reloj.en("2026-10-02 10:00"):
        sol = solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 2)
    assert sol.importe == Decimal("9000.00") and {s["clave"] for s in sol.soportes} >= {"entregable_etf"}


def test_hu_4_2_peg_no_tiene_verificacion_en_campo(peg_contratado, usuarios):
    with reloj.en("2026-06-16 10:00"):
        exp = peg_contratado()
    assert verificacion.config(exp) is None
    assert not verificacion.puede_registrar(usuarios["dir_dpf"], exp)[0]


# ----------------------------------------------------------------------------- permisos, devolución y conclusión
def test_hu_4_2_solo_la_delegacion_del_expediente_o_el_area_y_con_la_comprobacion_entregada(pagada, usuarios):
    with reloj.en(CONTRATO):
        exp, sin_comprobacion = pagada("CC", cuantas=2)
    with pytest.raises(ValidationError, match="comprobación enviada"):
        verificacion.registrar_verificacion(delegado_de(usuarios, sin_comprobacion), sin_comprobacion, "minuta_verificacion",
                                            _archivo("m.pdf"), superficie_verificada="6")
    with reloj.en("2026-11-12 10:00"):
        comprobaciones.registrar_envio(delegado_de(usuarios, exp), exp, "aviso_termino", fecha_hecho=date(2026, 11, 11))
    for quien in ("del_valle", "finanzas", "juridica", "comite"):
        with pytest.raises(PermissionDenied):
            verificacion.registrar_verificacion(usuarios[quien], exp, "minuta_verificacion", _archivo("m.pdf"), superficie_verificada="6")
    with pytest.raises(ValidationError, match="mayor que la aprobada"):
        verificacion.registrar_verificacion(delegado_de(usuarios, exp), exp, "minuta_verificacion", _archivo("m.pdf"),
                                            superficie_verificada="7")
    with pytest.raises(ValidationError, match="se documenta con"):
        verificacion.registrar_verificacion(delegado_de(usuarios, exp), exp, "formato_verificacion", _archivo("m.pdf"),
                                            superficie_verificada="6")
    assert not Verificacion.objects.filter(expediente=exp).exists()


def test_hu_4_2_el_area_devuelve_la_comprobacion_con_motivo(pagada, usuarios):
    exp = _por_verificar(pagada, usuarios, "CC", "2026-11-12 10:00", date(2026, 11, 11))
    with pytest.raises(ValidationError, match="motivo"):
        verificacion.devolver_comprobacion(usuarios["dir_drff"], exp, " ")
    with pytest.raises(PermissionDenied):
        verificacion.devolver_comprobacion(delegado_de(usuarios, exp), exp, "No")
    verificacion.devolver_comprobacion(usuarios["dir_drff"], exp, "Falta la firma del técnico en el informe.")
    exp.refresh_from_db()
    assert exp.estado.clave == "en_ejecucion" and exp.notificaciones.filter(tipo="otro", notificada_en__isnull=True).exists()


def test_hu_4_2_pago_unico_verificado_se_da_por_concluido(pagada, usuarios):
    exp = _por_verificar(pagada, usuarios, "CC", "2026-11-12 10:00", date(2026, 11, 11), ha=4)   # 100 % en un solo pago
    with reloj.en("2026-11-20 10:00"):
        verificacion.registrar_verificacion(delegado_de(usuarios, exp), exp, "informe_final_firmado", _archivo("i.pdf"),
                                            superficie_verificada="4")
    with pytest.raises(PermissionDenied):
        verificacion.dar_por_concluida(delegado_de(usuarios, exp), exp)
    verificacion.dar_por_concluida(usuarios["dir_drff"], exp)
    exp.refresh_from_db()
    assert exp.estado.clave == "concluida"


def test_hu_4_2_con_la_segunda_por_pagar_no_se_concluye(pagada, usuarios):
    exp = _por_verificar(pagada, usuarios, "PS")
    with reloj.en("2026-10-05 10:00"):
        verificacion.registrar_verificacion(delegado_de(usuarios, exp), exp, "formato_verificacion", _archivo("f.pdf"),
                                            superficie_verificada="4")
    with pytest.raises(ValidationError, match="ministración 2"):
        verificacion.dar_por_concluida(usuarios["dir_drff"], exp)


def test_hu_4_2_pestana_con_el_formulario_y_el_resultado(pagada, usuarios, client, contrasena):
    exp = _por_verificar(pagada, usuarios, "PS")
    deleg = delegado_de(usuarios, exp)
    client.login(username=deleg.username, password=contrasena)
    url = reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=ejecucion"
    html = client.get(url).content.decode()
    assert 'id="form-verificacion"' in html and "Registrar el resultado de la verificación en campo" in html
    assert "HU-4.2 Verificación en campo" not in html                       # ya no está «por construir»
    r = client.post(reverse("ejecucion:verificar", args=[exp.folio]), {
        "tipo_documento": "formato_verificacion", "archivo": _archivo("formato.pdf"), "superficie_verificada": "3.2",
        "incidencia_1_tipo": "caso_fortuito", "incidencia_1_descripcion": "Granizo", "incidencia_1_archivo": _archivo("acta.pdf")})
    assert r.status_code == 302
    html = client.get(url).content.decode()
    v = exp.verificaciones.get()
    assert 'data-prueba="verificacion"' in html and v.acuse.folio in html and "80 %" in html and 'data-incidencia="caso_fortuito"' in html
    assert client.get(reverse("ejecucion:verificacion_archivo", args=[v.pk])).status_code == 200
    assert client.get(reverse("ejecucion:incidencia_archivo", args=[v.incidencias.get().pk])).status_code == 200
    assert client.get(reverse("ejecucion:comprobaciones")).status_code == 200
