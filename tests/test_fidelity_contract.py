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


if __name__ == "__main__":
    test_fidelity_returns_tuple_without_docs()
    test_fidelity_returns_tuple_short_answer()
    test_fidelity_contract_unpacking()
    test_fidelity_empty_chunks_content()
    print("\n✨ Todos los tests de contrato verify_fidelity pasaron")
