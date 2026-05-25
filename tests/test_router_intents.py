"""Tests de clasificación de router — Capa 1 (keywords).

Cubre los tres grupos de frases que fallaron en producción (Telegram 2026-05-24):
  1. Frases de salida  → carril 'exit'
  2. Frases de identidad → carril 'identity'
  3. Preguntas de conceptos técnicos → carril 'rag'

Ejecución:
  pytest tests/test_router_intents.py -v
"""
import pytest
from app.router import route_query


# ─────────────────────────────────────────────
# 1. Salida — todas las variantes usadas en Telegram
# ─────────────────────────────────────────────

@pytest.mark.parametrize("phrase", [
    "salir",
    "exit",
    "quit",
    "bye",
    "chao",
    "chau",
    "Chao",
    "CHAO",
    "adios",
    "Adiós",
    "ADIÓS",
    "nos vemos",
    "Nos vemos",
    "hasta luego",
    "hasta pronto",
    "me voy",
    "cierro",
])
def test_exit_phrases_route_to_exit(phrase):
    """Toda frase de salida debe ir al carril 'exit', sin excepción."""
    result = route_query(phrase)
    assert result == "exit", (
        f"'{phrase}' debería routear a 'exit' pero fue '{result}'. "
        "Revisar _EXIT_WORDS en router.py."
    )


# ─────────────────────────────────────────────
# 2. Identidad — NO deben disparar exit ni rag
# ─────────────────────────────────────────────

@pytest.mark.parametrize("phrase", [
    "quien eres",
    "quién eres tú",
    "qué puedes hacer",
    "qué eres",
    "para que sirves",
    "cuáles son tus capacidades",
    "qué herramientas tienes",
    "tus límites",
    "qué no puedes hacer",
])
def test_identity_phrases_route_to_identity(phrase):
    """Preguntas sobre identidad del agente deben ir al carril 'identity'."""
    result = route_query(phrase)
    assert result == "identity", (
        f"'{phrase}' debería routear a 'identity' pero fue '{result}'."
    )


# ─────────────────────────────────────────────
# 3. Conceptos técnicos — deben ir a RAG (docs)
# ─────────────────────────────────────────────

@pytest.mark.parametrize("phrase", [
    "qué es un embedding",
    "que es un embedding",
    "qué es un retriever",
    "qué es un vector store",
    "qué es Chroma",
    "qué es LangChain",
    "qué es un retriever en LangChain",
    "como funciona Chroma",
    "para que sirve fidelity_check",
    "cómo funciona el RAG",
    "qué es la memoria episódica",
])
def test_technical_concepts_route_to_rag(phrase):
    """Preguntas de concepto técnico deben llegar al carril 'rag'."""
    result = route_query(phrase)
    assert result == "rag", (
        f"'{phrase}' debería routear a 'rag' pero fue '{result}'. "
        "Puede ser que RAG_HINTS no cubre este patrón o que memory/identity lo intercepta."
    )


# ─────────────────────────────────────────────
# 4. Salida NO debe confundirse con identidad
# ─────────────────────────────────────────────

def test_exit_not_identity():
    """'cerrar sesión' es una frase ambigua — debe resolverse como exit, no identity."""
    # Si no está en _EXIT_WORDS, al menos NO debe ir a identity.
    result = route_query("cerrar sesion")
    assert result != "identity", (
        "'cerrar sesion' no debería routear a 'identity'. "
        "Agregar 'cerrar sesion' a _EXIT_WORDS o manejarlo en chat_core."
    )


def test_exit_not_rag():
    """'adiós' no debe ir a rag."""
    result = route_query("adiós")
    assert result != "rag", "'adiós' llegó a rag — revisar normalización de tildes en _EXIT_WORDS."
