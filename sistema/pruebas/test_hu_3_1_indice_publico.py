"""HU-3.1 · Índice público de resultados: cada programa aparece una sola vez, con su última publicación."""
from datetime import datetime
from types import SimpleNamespace

from contrato.vistas.publicacion import ultima_por_programa


def _publicacion(ejercicio_id, programa, anio, dia):
    ejercicio = SimpleNamespace(programa=SimpleNamespace(nombre=programa), anio=anio)
    return SimpleNamespace(ejercicio_id=ejercicio_id, ejercicio=ejercicio, publicada_en=datetime(2026, 11, dia))


def test_hu_3_1_el_indice_publico_muestra_cada_programa_una_vez_con_su_ultima_publicacion():
    # Como las entrega el servicio: de la más reciente a la más antigua, con los programas intercalados.
    publicaciones = [
        _publicacion(2, "Restauración Hidrológico-Forestal", 2026, 6),
        _publicacion(1, "Plantaciones Sustentables", 2026, 5),
        _publicacion(2, "Restauración Hidrológico-Forestal", 2026, 3),
        _publicacion(1, "Plantaciones Sustentables", 2026, 2),
        _publicacion(3, "Capturando Carbono", 2026, 1),
    ]
    indice = ultima_por_programa(publicaciones)
    assert [p.ejercicio.programa.nombre for p in indice] == [
        "Capturando Carbono", "Plantaciones Sustentables", "Restauración Hidrológico-Forestal"]
    assert [p.publicada_en.day for p in indice] == [1, 5, 6]


def test_hu_3_1_el_indice_publico_sin_publicaciones_queda_vacio():
    assert ultima_por_programa([]) == []
