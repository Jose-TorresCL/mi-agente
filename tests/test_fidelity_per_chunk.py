from __future__ import annotations

from unittest.mock import patch
from app.fidelity_check import verify_fidelity


def test_per_chunk_similarity(monkeypatch):
    # Simular get_embedding para respuesta y chunks
    from app import fidelity_check

    def fake_embedding(text):
        # simple mapping: if 'chunk2' in text return vector [0,1], if 'chunk1' -> [1,0], answer -> [0,1]
        if 'chunk2' in text:
            return [0.0, 1.0]
        if 'chunk1' in text:
            return [1.0, 0.0]
        if 'respuesta' in text:
            return [0.0, 1.0]
        return [0.0, 0.0]

    monkeypatch.setattr('app.fidelity_check.get_embedding', fake_embedding)

    class Doc:
        def __init__(self, content):
            self.page_content = content

    chunks = [Doc('chunk1 content'), Doc('chunk2 content')]
    ok, score = verify_fidelity('respuesta similar a chunk2', chunks, question='')
    assert ok is True
    assert score > 0.9
