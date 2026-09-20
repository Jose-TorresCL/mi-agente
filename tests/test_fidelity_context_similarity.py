"""
Tests de similitud semántica de fidelity_check.

Verifica que verify_fidelity compare la respuesta contra el contexto
concatenado recuperado, sin necesitar Ollama activo.

Ejecución:
    pytest tests/test_fidelity_context_similarity.py -v
"""

from __future__ import annotations

from app import fidelity_check
from app.fidelity_check import verify_fidelity


class Doc:
    """Documento mínimo compatible con verify_fidelity."""

    def __init__(self, content: str):
        self.page_content = content


def test_context_similarity_uses_answer_and_concatenated_chunks(monkeypatch):
    """
    La respuesta y el contexto concatenado reciben el mismo vector.

    Se espera score 1.0 y aprobación. El mock también verifica que fidelity
    solicite exactamente dos embeddings: uno para respuesta y otro para contexto.
    """
    calls: list[dict] = []

    def fake_get_embedding(
        text: str,
        timeout=None,
        retry_delays=None,
        max_attempts=None,
    ) -> list[float]:
        calls.append(
            {
                "text": text,
                "timeout": timeout,
                "retry_delays": retry_delays,
                "max_attempts": max_attempts,
            }
        )
        return [1.0, 0.0]

    monkeypatch.setattr(
        fidelity_check,
        "get_embedding",
        fake_get_embedding,
    )

    answer = "El router híbrido combina keywords y embeddings."
    chunks = [
        Doc("El router híbrido combina keywords."),
        Doc("También usa embeddings como segunda capa."),
    ]

    ok, score = verify_fidelity(
        answer=answer,
        source_docs=chunks,
        question="¿Cómo funciona el router híbrido?",
    )

    assert ok is True
    assert score == 1.0

    assert len(calls) == 2

    assert calls[0]["text"] == answer

    assert "El router híbrido combina keywords." in calls[1]["text"]
    assert "También usa embeddings como segunda capa." in calls[1]["text"]

    assert calls[0]["retry_delays"] == [0.0]
    assert calls[1]["retry_delays"] == [0.0]

    assert calls[0]["max_attempts"] == 1
    assert calls[1]["max_attempts"] == 1