"""Genera los documentos de prueba del sprint 2 (contrato firmado, carta compromiso, comprobante de cuenta y documentos de
sesión). Los polígonos, los PDF de requisitos y las fichas de solicitudes son los del sprint 1 (`datos_prueba/sprint_1/`).

Se corre desde la raíz del repositorio con el entorno de la Calculadora (solo necesita matplotlib):

    python datos_prueba/sprint_2/generar_datos_prueba.py

Todo es ficticio y sin validez oficial.
"""
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SALIDA = pathlib.Path(__file__).resolve().parent / "documentos"

DOCUMENTOS = [
    ("contrato_firmado_de_prueba", "Contrato firmado (digitalizado)",
     "Se sube en «Registrar la firma» (Delegación, HU-3.3).\nEn un contrato real llevaría las firmas de las partes y el sello."),
    ("carta_compromiso_de_prueba", "Carta compromiso de la persona beneficiaria",
     "Se sube al entregar un Vale de Planta antes de firmar el contrato (HU-3.4)."),
    ("comprobante_cuenta_bancaria", "Comprobante de la cuenta bancaria",
     "Estado de cuenta ficticio. Se sube en la pestaña «Pagos» (HU-5.1) en CC, PS y RHF."),
    ("documento_de_sesion_casos_de_seguimiento", "Casos para la sesión de seguimiento",
     "Documento de la convocatoria de una sesión de seguimiento (HU-2.4)."),
    ("documento_de_sesion_instruccion_de_pago", "Instrucción de pago del Comité Técnico",
     "Documento de la sesión en la que se acuerda la instrucción de pago de PSAHEM (HU-2.4 y HU-5.1)."),
]


def generar():
    SALIDA.mkdir(exist_ok=True)
    for archivo, titulo, uso in DOCUMENTOS:
        fig = plt.figure(figsize=(8.5, 11))
        fig.text(0.1, 0.9, "PROBOSQUE · DATOS DE PRUEBA · SPRINT 2", fontsize=11, color="#666")
        fig.text(0.1, 0.84, titulo, fontsize=16, weight="bold")
        fig.text(0.1, 0.76, "Documento ficticio para probar el sistema.\nNo tiene validez oficial.\n\n" + uso, fontsize=12,
                 va="top")
        fig.text(0.5, 0.45, "DOCUMENTO DE PRUEBA", fontsize=40, color="#d33", alpha=0.25, rotation=30, ha="center",
                 va="center")
        fig.savefig(SALIDA / f"{archivo}.pdf")
        plt.close(fig)
    return [a for a, _, _ in DOCUMENTOS]


if __name__ == "__main__":
    print(len(generar()), "documentos en", SALIDA)
