"""Tests unitarios para tool_update_work_state — Bug 2: firma correcta con kwargs

Objetivo: Garantizar que tool_update_work_state SIEMPRE acepta kwargs:
  - next_step
  - current_focus
  - last_completed_step
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools import tool_update_work_state
from app.schemas import ToolResult


def test_tool_update_work_state_kwarg_next_step():
    """Contrato: tool_update_work_state(next_step='valor') debe funcionar."""
    try:
        result = tool_update_work_state(next_step="implementar tests")
        
        # Verificar que retorna ToolResult
        assert isinstance(result, dict)
        assert result.get("ok") is True
        assert "next_step" in result.get("data", {}).get("cambios", [""])[0]
        print("✓ test_tool_update_work_state_kwarg_next_step: PASS")
    except TypeError as e:
        raise AssertionError(f"tool_update_work_state should accept next_step kwarg: {e}")


def test_tool_update_work_state_kwarg_current_focus():
    """Contrato: tool_update_work_state(current_focus='valor') debe funcionar."""
    try:
        result = tool_update_work_state(current_focus="fase 5")
        
        # Verificar que retorna ToolResult
        assert isinstance(result, dict)
        assert result.get("ok") is True
        assert "current_focus" in result.get("data", {}).get("cambios", [""])[0]
        print("✓ test_tool_update_work_state_kwarg_current_focus: PASS")
    except TypeError as e:
        raise AssertionError(f"tool_update_work_state should accept current_focus kwarg: {e}")


def test_tool_update_work_state_kwarg_last_completed():
    """Contrato: tool_update_work_state(last_completed_step='valor') debe funcionar."""
    try:
        result = tool_update_work_state(last_completed_step="corregir fidelity_check")
        
        # Verificar que retorna ToolResult
        assert isinstance(result, dict)
        assert result.get("ok") is True
        assert "last_completed" in result.get("data", {}).get("cambios", [""])[0]
        print("✓ test_tool_update_work_state_kwarg_last_completed: PASS")
    except TypeError as e:
        raise AssertionError(f"tool_update_work_state should accept last_completed_step kwarg: {e}")


def test_tool_update_work_state_multiple_kwargs():
    """Contrato: tool_update_work_state puede recibir múltiples kwargs a la vez."""
    try:
        result = tool_update_work_state(
            current_focus="memoria automática",
            next_step="implementar inyección",
            last_completed_step="fix del logger"
        )
        
        # Verificar que retorna ToolResult
        assert isinstance(result, dict)
        assert result.get("ok") is True
        cambios = result.get("data", {}).get("cambios", [])
        assert len(cambios) >= 3, f"Expected at least 3 cambios, got {len(cambios)}"
        print("✓ test_tool_update_work_state_multiple_kwargs: PASS")
    except TypeError as e:
        raise AssertionError(f"tool_update_work_state should accept multiple kwargs: {e}")


def test_tool_update_work_state_returns_tool_result():
    """Contrato R6-A: siempre retorna ToolResult dict con {ok, message, data, side_effect}."""
    result = tool_update_work_state(next_step="test")
    
    assert isinstance(result, dict)
    assert "ok" in result
    assert "message" in result
    assert "data" in result
    assert "side_effect" in result
    assert "tool_name" in result
    print("✓ test_tool_update_work_state_returns_tool_result: PASS")


def test_tool_update_work_state_empty_input():
    """Contrato: tool_update_work_state sin kwargs (solo texto="") no explota."""
    result = tool_update_work_state()
    
    # Debe ser falso porque no hay cambios que hacer
    assert isinstance(result, dict)
    assert "ok" in result
    print("✓ test_tool_update_work_state_empty_input: PASS")


if __name__ == "__main__":
    test_tool_update_work_state_kwarg_next_step()
    test_tool_update_work_state_kwarg_current_focus()
    test_tool_update_work_state_kwarg_last_completed()
    test_tool_update_work_state_multiple_kwargs()
    test_tool_update_work_state_returns_tool_result()
    test_tool_update_work_state_empty_input()
    print("\n✨ Todos los tests de contrato tool_update_work_state pasaron")
