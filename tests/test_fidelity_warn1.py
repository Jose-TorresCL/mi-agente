"""Tests para el fix 6C: bypass de respuestas cortas en fidelity_check.

Cubre el WARN 1 documentado: respuestas cortas sin evidencia ya no pasan
con score 1.0. Solo pasan si hay chunks con contenido real.

Estos tests NO requieren Ollama activo — usan solo lógica de texto puro
(el paso semántico no se alcanza porque word_count < SHORT_ANSWER_WORDS).
"""
import pytest
from unittest.mock import patch
from langchain_core.documents import Document

from app.fidelity_check import verify_fidelity


class TestFidelityShortAnswerFix6C:
    """Fix 6C: respuesta corta sin chunks → bloqueo."""

    def test_short_answer_no_docs_is_blocked(self):
        """Respuesta corta sin source_docs → bloqueada (score 0.0).

        Antes del fix: pasaba con (True, 1.0).
        Después del fix: source_docs vacío → bloqueo en el Paso 1.
        """
        ok, score = verify_fidelity(
            answer="No lo sé.",
            source_docs=[],
            question="¿Cuál es la fase actual?",
        )
        assert ok is False, "Respuesta corta sin docs debe ser bloqueada"
        assert score == 0.0

    def test_short_answer_with_valid_chunks_passes(self):
        """Respuesta corta con chunks válidos → pasa (score 1.0).

        El bypass de cortas sigue funcionando cuando hay evidencia.
        """
        doc = Document(
            page_content="La fase actual del proyecto es la Fase 6.",
            metadata={"source": "estado_proyecto.md"},
        )
        ok, score = verify_fidelity(
            answer="Fase 6.",
            source_docs=[doc],
            question="¿Cuál es la fase?",
        )
        assert ok is True, "Respuesta corta con chunks válidos debe pasar"
        assert score == 1.0

    def test_short_answer_empty_content_chunks_is_blocked(self):
        """Chunks presentes pero con contenido vacío → bloqueado.

        source_docs tiene documentos, pero todos tienen page_content vacío
        o solo espacios. chunks_texts queda vacío → bloqueo en Paso 1b.
        """
        doc_empty = Document(page_content="   ", metadata={})
        ok, score = verify_fidelity(
            answer="No sé.",
            source_docs=[doc_empty],
            question="¿Qué pasa?",
        )
        assert ok is False
        assert score == 0.0
