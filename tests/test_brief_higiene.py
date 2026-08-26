"""Contrato de higiene de escritura en memory_manager (paso 1 del brief).

Verifica que las funciones de limpieza introducidas para resolver:
  - session_goal guardado con el prefijo de comando incluido
  - títulos de tarea con restos de "crea tarea:", "nueva:", "prioridad" colgando
  - next_step trivial ("test") sobrescribiendo sugerencias útiles

No requiere Ollama, Chroma ni storage/ real — son funciones puras de texto.
"""
from app.memory_manager import (
    _clean_goal_text,
    _clean_task_title,
    _is_meaningful_next_step,
    set_session_goal,
    update_state,
)

def test_goal_sin_prefijo():
    assert _clean_goal_text("mi objetivo de hoy es: cerrar bugs") == "cerrar bugs"


def test_goal_sin_prefijo_no_se_toca():
    assert _clean_goal_text("cerrar bugs del router") == "cerrar bugs del router"


def test_task_limpia_comando_y_prioridad():
    title, prio = _clean_task_title("crea tarea: revisar episodio, prioridad media")
    assert title == "revisar episodio"
    assert prio == "medium"


def test_task_prioridad_vacia_no_extrae():
    title, prio = _clean_task_title("nueva: 'verificar tool_update_work_state', prioridad")
    assert title == "verificar tool_update_work_state"
    assert prio is None


def test_next_step_trivial_rechazado():
    assert not _is_meaningful_next_step("test")


def test_next_step_real_aceptado():
    assert _is_meaningful_next_step("escribir intent_examples.json")

def test_update_state_rechaza_trivial(monkeypatch):
    escritas = []
    monkeypatch.setattr("app.memory_manager.update_work_state", lambda f, v: escritas.append((f, v)))
    assert update_state("next_step", "test") is False
    assert escritas == []


def test_update_state_escribe_valor_real(monkeypatch):
    escritas = []
    monkeypatch.setattr("app.memory_manager.update_work_state", lambda f, v: escritas.append((f, v)))
    assert update_state("next_step", "cerrar el paso 1 del brief") is True
    assert escritas == [("next_step", "cerrar el paso 1 del brief")]


def test_set_session_goal_devuelve_texto_limpio(monkeypatch):
    guardados = []
    monkeypatch.setattr("app.memory_manager.update_session_goal", lambda g: guardados.append(g))
    assert set_session_goal("mi objetivo de hoy es: cerrar bugs") == "cerrar bugs"
    assert guardados == ["cerrar bugs"]