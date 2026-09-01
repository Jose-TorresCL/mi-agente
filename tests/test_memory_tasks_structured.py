"""Contrato: consultas mecánicas sobre tareas responden por código, sin LLM."""
from app import intelligence

_FAKE_TASKS = {"tasks": [
    {"id": "T-1", "title": "cerrar brief", "status": "pending", "priority": "high"},
]}


def test_tasks_estructurada_no_llama_llm(monkeypatch):
    monkeypatch.setattr(intelligence, "get_tasks", lambda: _FAKE_TASKS)
    monkeypatch.setattr(intelligence, "format_tasks_answer",
                        lambda t, question="": "T-1 cerrar brief (high)")
    llamadas = {"n": 0}
    monkeypatch.setattr(intelligence, "generate_raw",
                        lambda *a, **k: llamadas.update(n=llamadas["n"] + 1) or "LLM")
    answer = intelligence._decide_memory(
        "lista las tareas mas importantes por hacer", ["tasks"])
    assert llamadas["n"] == 0
    assert "cerrar brief" in answer


def test_tasks_reasoning_si_usa_llm(monkeypatch):
    monkeypatch.setattr(intelligence, "get_tasks", lambda: _FAKE_TASKS)
    monkeypatch.setattr(intelligence, "format_tasks_answer",
                        lambda t, question="": "T-1 cerrar brief (high)")
    monkeypatch.setattr(intelligence, "generate_raw", lambda *a, **k: "síntesis LLM")
    answer = intelligence._decide_memory(
        "qué me recomiendas atacar primero con mis tareas", ["tasks"])
    assert answer == "síntesis LLM"