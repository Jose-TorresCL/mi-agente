from __future__ import annotations

from app.fidelity_check import verify_fidelity

class Doc:
    def __init__(self, content):
        self.page_content = content


def test_numeric_variants_acceptance():
    chunks = [Doc('El total fue 10456 archivos en el índice.')]
    ok, score = verify_fidelity('Hay 10.456 archivos', chunks, question='')
    assert ok is True

    ok2, _ = verify_fidelity('Tenemos 10k registros', [Doc('Tenemos 10000 registros')], question='')
    assert ok2 is True
