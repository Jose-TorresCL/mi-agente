from __future__ import annotations

from app.fidelity_check import verify_fidelity

class Doc:
    def __init__(self, content):
        self.page_content = content


def test_numeric_variant_thousand_separator():
    chunks = [Doc('El total fue 10456 archivos en el índice.')]
    ok, score = verify_fidelity('Hay 10.456 archivos', chunks, question='')
    assert ok is True


def test_numeric_variant_k_suffix():
    ok, score = verify_fidelity('Tenemos 10k registros', [Doc('Tenemos 10000 registros')], question='')
    assert ok is True


def test_numeric_variant_percent_format():
    ok, score = verify_fidelity('La tasa fue 98,3% en el informe', [Doc('La tasa fue 98.3% en el informe')], question='')
    assert ok is True
