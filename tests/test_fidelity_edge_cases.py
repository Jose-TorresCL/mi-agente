"""
Tests de fidelity_check — casos borde documentados.

Cubre los casos que justifican el umbral dinámico y la validación numérica.
No requiere Ollama activo: los casos que alcanzan embeddings usan mocks.

Ejecución:
    pytest tests/test_fidelity_edge_cases.py -v
"""

from __future__ import annotations

from app import fidelity_check
from app.fidelity_check import _dynamic_threshold, verify_fidelity


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _make_chunks(texts: list[str]) -> list:
    """Crea objetos mínimos con .page_content."""

    class FakeDoc:
        def __init__(self, text: str):
            self.page_content = text

    return [FakeDoc(text) for text in texts]


def _mock_embeddings(monkeypatch) -> None:
    """Evita llamadas HTTP a Ollama y produce similitud máxima."""

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


# ─────────────────────────────────────────────
# Caso 1: sin chunks → siempre bloquear
# ─────────────────────────────────────────────


def test_no_chunks_always_blocked():
    """Sin contexto recuperado no hay evidencia para validar."""
    ok, score = verify_fidelity(
        answer="Un embedding es una representación vectorial.",
        source_docs=[],
        question="¿Qué es un embedding?",
    )

    assert ok is False
    assert score == 0.0


# ─────────────────────────────────────────────
# Caso 2: número inventado → bloquear
# ─────────────────────────────────────────────


def test_invented_number_blocked():
    """Un número que no está en los chunks debe bloquearse."""
    chunks = _make_chunks(
        ["El proyecto tiene 5 archivos de configuración."]
    )

    ok, score = verify_fidelity(
        answer="El proyecto tiene 42 archivos de configuración.",
        source_docs=chunks,
        question="¿Cuántos archivos de configuración tiene el proyecto?",
    )

    assert ok is False
    assert score == 0.0


# ─────────────────────────────────────────────
# Caso 3: número respaldado → pasar
# ─────────────────────────────────────────────


def test_supported_number_passes(monkeypatch):
    """Un número presente en el contexto no debe bloquearse."""
    _mock_embeddings(monkeypatch)

    answer = "El proyecto tiene 5 archivos de configuración."
    chunks = _make_chunks([answer])

    ok, score = verify_fidelity(
        answer=answer,
        source_docs=chunks,
        question="¿Cuántos archivos de configuración tiene el proyecto?",
    )

    assert ok is True
    assert score == 1.0


# ─────────────────────────────────────────────
# Caso 4: respuesta vacía → bloquear
# ─────────────────────────────────────────────


def test_empty_answer_is_blocked():
    """Una respuesta vacía no debe considerarse fiel."""
    chunks = _make_chunks(["Información relevante aquí."])

    ok, score = verify_fidelity(
        answer="",
        source_docs=chunks,
        question="¿Qué dice el documento?",
    )

    assert ok is False
    assert score == 0.0


# ─────────────────────────────────────────────
# Caso 5: umbral dinámico
# ─────────────────────────────────────────────


def test_dynamic_threshold_depends_on_question_length():
    """Preguntas más largas requieren mayor similitud."""

    assert _dynamic_threshold("router") == 0.40

    assert _dynamic_threshold(
        "qué es un router híbrido"
    ) == 0.55

    assert _dynamic_threshold(
        "cómo funciona exactamente el router híbrido y cuáles son "
        "sus tres capas de clasificación"
    ) == 0.60