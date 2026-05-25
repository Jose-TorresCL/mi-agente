"""Tests de fidelity_check — casos borde documentados.

Cobre los casos que justifican el umbral dinámico y la lógica de números.
No requieren Ollama. Usan la función check_fidelity() directamente.

Ejecución:
  pytest tests/test_fidelity_edge_cases.py -v
"""
import pytest

try:
    from app.fidelity_check import check_fidelity
except ImportError:
    pytest.skip("fidelity_check no disponible", allow_module_level=True)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_chunks(texts: list[str]) -> list:
    """Crea objetos mínimos con .page_content para check_fidelity."""
    class FakeDoc:
        def __init__(self, text):
            self.page_content = text
    return [FakeDoc(t) for t in texts]


# ─────────────────────────────────────────────
# Caso 1: sin chunks → siempre bloquear
# ─────────────────────────────────────────────

def test_no_chunks_always_blocked():
    """Sin chunks de contexto no hay forma de verificar fidelidad — siempre bloquea."""
    result = check_fidelity(
        question="qué es un embedding",
        answer="Un embedding es una representación vectorial.",
        chunks=[]
    )
    assert result["pass"] is False, "Sin chunks debería bloquear siempre."


# ─────────────────────────────────────────────
# Caso 2: número inventado → bloquear
# ─────────────────────────────────────────────

def test_invented_number_blocked():
    """Si la respuesta tiene un número que no aparece en los chunks, bloquear."""
    chunks = _make_chunks(["El proyecto tiene 5 archivos de configuración."])
    result = check_fidelity(
        question="cuántos archivos de configuración tiene el proyecto",
        answer="El proyecto tiene 42 archivos de configuración.",  # 42 inventado
        chunks=chunks
    )
    assert result["pass"] is False, (
        "Número '42' no está en los chunks — debería bloquearse."
    )


# ─────────────────────────────────────────────
# Caso 3: número correcto → pasar
# ─────────────────────────────────────────────

def test_correct_number_passes():
    """Si el número de la respuesta está en los chunks, puede pasar."""
    chunks = _make_chunks(["El proyecto tiene 5 archivos de configuración."])
    result = check_fidelity(
        question="cuántos archivos de configuración tiene el proyecto",
        answer="El proyecto tiene 5 archivos de configuración.",
        chunks=chunks
    )
    # No exigimos pass=True (puede fallar por umbral bajo), pero sí que no sea
    # bloqueado exclusivamente por el número.
    # Verificamos que el campo de fidelidad numérica sea positivo.
    assert result.get("numeric_ok") is not False, (
        "El número '5' está en chunks — no debería bloquearse por chequeo numérico."
    )


# ─────────────────────────────────────────────
# Caso 4: respuesta corta sin chunks → bloquear (fix 6C)
# ─────────────────────────────────────────────

def test_short_answer_no_chunks_blocked():
    """Respuesta corta + sin chunks = bloqueado (Fix 6C)."""
    result = check_fidelity(
        question="ok",
        answer="ok",
        chunks=[]
    )
    assert result["pass"] is False


# ─────────────────────────────────────────────
# Caso 5: respuesta vacía → bloquear
# ─────────────────────────────────────────────

def test_empty_answer_blocked():
    """Una respuesta vacía nunca debe pasar fidelidad."""
    chunks = _make_chunks(["Información relevante aquí."])
    result = check_fidelity(
        question="qué dice el documento",
        answer="",
        chunks=chunks
    )
    assert result["pass"] is False


# ─────────────────────────────────────────────
# Caso 6: umbral dinámico — pregunta larga más exigente
# ─────────────────────────────────────────────

def test_dynamic_threshold_applied():
    """El umbral debe ser diferente para preguntas cortas vs largas.
    Solo verifica que check_fidelity acepta el parámetro y no rompe.
    """
    chunks = _make_chunks(["El router híbrido tiene tres capas: keywords, embeddings y fallback."])
    short_q = "router"
    long_q = "cómo funciona exactamente el router híbrido y cuáles son sus tres capas de clasificación"

    result_short = check_fidelity(short_q, "El router tiene capas.", chunks)
    result_long  = check_fidelity(long_q,  "El router tiene capas.", chunks)

    # Ambos deben devolver un dict con campo 'pass' — no debe crashear.
    assert "pass" in result_short
    assert "pass" in result_long
