"""P-22: el PDF ligero de las pruebas y el render verdadero con WeasyPrint."""
import pytest

from nucleo import acuses
from pruebas.conftest import pdf_real_forzado

HTML = "<html><head><style>p{color:red}</style></head><body><h1>Acuse AC-2026-000001</h1><p>Texto (con paréntesis)</p></body></html>"


@pytest.mark.skipif(pdf_real_forzado(), reason="con PDF_REAL=1 todo es real")
def test_p_22_por_omision_el_pdf_es_el_ligero_y_conserva_el_texto():
    pdf = acuses._pdf(HTML)
    assert pdf.startswith(b"%PDF") and b"AC-2026-000001" in pdf and b"color:red" not in pdf


@pytest.mark.pdf_real
def test_p_22_con_el_marcador_pdf_real_se_renderiza_con_weasyprint():
    pdf = acuses._pdf(HTML)
    assert pdf.startswith(b"%PDF") and b"AC-2026-000001" not in pdf   # texto comprimido por WeasyPrint
