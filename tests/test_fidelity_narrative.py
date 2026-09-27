"""
Tests de marcos narrativos no soportados en fidelity_check.

Estas frases atribuyen recuerdos, experiencias o decisiones al usuario.
Deben bloquearse si no están presentes como evidencia en los chunks.

Ejecución:
    pytest tests/test_fidelity_narrative.py -v
"""

from __future__ import annotations

import pytest

from app import fidelity_check
from app.fidelity_check import verify_fidelity


class Doc:
    """Documento mínimo compatible con verify_fidelity."""

    def __init__(self, content: str):
        self.page_content = content


@pytest.mark.parametrize(
    "answer",
    [
        (
            "Como mencionaste que el router fallaba, "
            "el router híbrido usa keywords y embeddings."
        ),
        (
            "Según tu experiencia con el proyecto, "
            "el router híbrido usa keywords y embeddings."
        ),
        (
            "Tuviste problemas con el router, por eso "
            "se usa un fallback basado en LLM."
        ),
        (
            "Acordamos que el router híbrido combina "
            "keywords, embeddings y fallback."
        ),
        (
            "En la sesión anterior dijiste que había "
            "problemas con el routing."
        ),
        (
            "Como hablamos antes, el proyecto usa "
            "embeddings para la recuperación semántica."
        ),
    ],
)
def test_blocks_unsupported_narrative_attribution(answer: str):
    """Las atribuciones al usuario sin soporte deben bloquearse."""
    chunks = [
        Doc(
            "El router híbrido usa keywords, embeddings "
            "y fallback LLM."
        )
    ]

    ok, score = verify_fidelity(
        answer=answer,
        source_docs=chunks,
        question="¿Cómo funciona el router híbrido?",
    )

    assert ok is False
    assert score == 0.0


def test_allows_supported_technical_answer_without_narrative_frame(
    monkeypatch,
):
    """La explicación técnica normal debe poder pasar."""

    def fake_get_embedding(
        text: str,
        timeout=None,
        retry_delays=None,
        max_attempts=None,
    ) -> list[float]:
        return [1.0, 0.0]

    monkeypatch.setattr(
        fidelity_check,
        "get_embedding",
        fake_get_embedding,
    )

    answer = "El router híbrido usa keywords, embeddings y fallback LLM."
    chunks = [Doc(answer)]

    ok, score = verify_fidelity(
        answer=answer,
        source_docs=chunks,
        question="¿Cómo funciona el router híbrido?",
    )

    assert ok is True
    assert score == 1.0