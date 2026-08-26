"""Tests unitarios para verify_fidelity — Bug 1: retorno correcto tuple[bool, float]

Objetivo: Garantizar que verify_fidelity SIEMPRE retorna (bool, float) nunca solo bool.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.fidelity_check import verify_fidelity


def test_fidelity_returns_tuple_without_docs():
    """Caso sin chunks: debe retornar (False, 0.0) como tupla."""
    result = verify_fidelity("Respuesta sin soportar", [])
    
    # Verificar que es un tuple
    assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
    assert len(result) == 2, f"Expected 2-tuple, got {len(result)}-tuple"
    
    # Verificar tipos
    ok, score = result
    assert isinstance(ok, bool), f"First element should be bool, got {type(ok)}"
    assert isinstance(score, float), f"Second element should be float, got {type(score)}"
    
    # Verificar valores
    assert ok is False
    assert score == 0.0
    print("✓ test_fidelity_returns_tuple_without_docs: PASS")


def test_fidelity_returns_tuple_short_answer():
    """Caso respuesta corta con chunks: debe retornar (True, 1.0) como tupla."""
    class MockDoc:
        page_content = "El router usa keywords y embeddings"
    
    result = verify_fidelity("Sí", [MockDoc()])
    
    # Verificar que es un tuple
    assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
    assert len(result) == 2, f"Expected 2-tuple, got {len(result)}-tuple"
    
    # Verificar tipos
    ok, score = result
    assert isinstance(ok, bool), f"First element should be bool, got {type(ok)}"
    assert isinstance(score, float), f"Second element should be float, got {type(score)}"
    
    # Verificar valores
    assert ok is True
    assert score == 1.0
    print("✓ test_fidelity_returns_tuple_short_answer: PASS")


def test_fidelity_contract_unpacking():
    """Contrato: debe ser desempaqueable como `ok, score = verify_fidelity(...)`"""
    class MockDoc:
        page_content = "El router usa keywords y embeddings"
    
    try:
        ok, score = verify_fidelity("El router usa keywords", [MockDoc()])
        assert isinstance(ok, bool)
        assert isinstance(score, float)
        print("✓ test_fidelity_contract_unpacking: PASS")
    except TypeError as e:
        raise AssertionError(f"Cannot unpack verify_fidelity result: {e}")


def test_fidelity_empty_chunks_content():
    """Caso chunks sin contenido real: debe retornar (False, 0.0)."""
    class MockDoc:
        page_content = ""
    
    ok, score = verify_fidelity("Respuesta", [MockDoc()])
    assert ok is False
    assert score == 0.0
    print("✓ test_fidelity_empty_chunks_content: PASS")


def test_fidelity_stats_has_method_breakdown():
    """Debe exponer un desglose por tipo de resultado para observabilidad."""
    from app.fidelity_check import fidelity_stats

    stats = fidelity_stats()
    assert isinstance(stats, dict)
    assert "by_method" in stats
    for key in ["short_bypass", "semantic_ok", "semantic_fail", "unverified", "blocked_no_docs"]:
        assert key in stats["by_method"]


def test_get_embedding_uses_api_embed_and_embeddings_array(monkeypatch):
    """El endpoint actual debe usar /api/embed y leer embeddings[0]."""
    from app import semantic_cache

    class Response:
        def __init__(self, payload):
            self._payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self._payload

    calls = []

    def fake_post(url, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return Response({"embeddings": [[0.1, 0.2]]})

    monkeypatch.setattr(semantic_cache.requests, "post", fake_post)
    result = semantic_cache.get_embedding("hola", timeout=1.0, retry_delays=[0.0], max_attempts=1)
    assert result == [0.1, 0.2]
    assert calls[0]["url"].endswith("/api/embed")
    assert calls[0]["json"] == {"model": semantic_cache.EMBEDDING_MODEL, "input": "hola", "keep_alive": -1,}


def test_embedding_model_constants_are_distinct():
    """MODEL_NAME es para texto y EMBEDDING_MODEL para vectores."""
    from app import config

    assert config.MODEL_NAME != config.EMBEDDING_MODEL


def test_get_embedding_handles_http_500_without_raising(monkeypatch):
    """Errores HTTP deben devolver None sin propagarse."""
    from app import semantic_cache

    class Response:
        def raise_for_status(self):
            raise Exception("HTTP 500")
        def json(self):
            return {}

    monkeypatch.setattr(semantic_cache.requests, "post", lambda *a, **k: Response())
    assert semantic_cache.get_embedding("hola", retry_delays=[0.0], max_attempts=1) is None


def test_fidelity_uses_one_internal_attempt_per_backoff_step(monkeypatch):
    """La capa de fidelity debe ser el único dueño del backoff corto."""
    from app import fidelity_check

    calls = []

    def fake_get_embedding(text, timeout=None, retry_delays=None, max_attempts=None):
        calls.append({
            "text": text,
            "timeout": timeout,
            "retry_delays": retry_delays,
            "max_attempts": max_attempts,
        })
        return [0.0, 1.0]

    monkeypatch.setattr(fidelity_check, "get_embedding", fake_get_embedding)

    class Doc:
        page_content = "El sistema usa embeddings para medir similitud." \
            " La respuesta debe estar respaldada por el contexto."

    ok, score = fidelity_check.verify_fidelity(
        "La respuesta usa embeddings para medir similitud respaldada por el contexto.",
        [Doc()],
        question="",
    )
    assert ok is True
    assert len(calls) == 2
    assert all(call["retry_delays"] == [0.0] for call in calls)
    assert all(call["max_attempts"] == 1 for call in calls)


if __name__ == "__main__":
    test_fidelity_returns_tuple_without_docs()
    test_fidelity_returns_tuple_short_answer()
    test_fidelity_contract_unpacking()
    test_fidelity_empty_chunks_content()
    print("\n✨ Todos los tests de contrato verify_fidelity pasaron")
