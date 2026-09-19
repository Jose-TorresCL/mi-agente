"""Contrato: consultas estructuradas sobre tareas responden sin LLM."""

from app import intelligence


def _fake_tasks() -> dict:
    return {
        "tasks": [
            {
                "id": "T-HIGH",
                "title": "Revisar fidelity_check",
                "status": "pending",
                "priority": "high",
            },
            {
                "id": "T-MEDIUM",
                "title": "Mejorar dashboard",
                "status": "pending",
                "priority": "medium",
            },
            {
                "id": "T-DONE-HIGH",
                "title": "Tarea alta cerrada",
                "status": "completed",
                "priority": "high",
            },
        ]
    }


def _fail_if_llm_is_called(*args, **kwargs):
    raise AssertionError(
        "Una consulta estructurada de tareas no debe invocar el LLM"
    )


def test_task_priority_returns_only_pending_high_without_llm(monkeypatch):
    monkeypatch.setattr(intelligence, "get_tasks", _fake_tasks)
    monkeypatch.setattr(
        intelligence,
        "_synthesize_memory_answer",
        _fail_if_llm_is_called,
    )

    answer = intelligence._decide_memory(
        "cual es la de mas alta prioridad",
        ["tasks"],
        chat_history=[],
    )

    assert "T-HIGH" in answer
    assert "Revisar fidelity_check" in answer
    assert "T-MEDIUM" not in answer
    assert "Mejorar dashboard" not in answer
    assert "T-DONE-HIGH" not in answer
    assert "Tarea alta cerrada" not in answer


def test_task_id_request_lists_only_pending_tasks_without_llm(monkeypatch):
    monkeypatch.setattr(intelligence, "get_tasks", _fake_tasks)
    monkeypatch.setattr(
        intelligence,
        "_synthesize_memory_answer",
        _fail_if_llm_is_called,
    )

    answer = intelligence._decide_memory(
        "dame los ids de las tareas pendientes",
        ["tasks"],
        chat_history=[],
    )

    assert "T-HIGH" in answer
    assert "T-MEDIUM" in answer
    assert "T-DONE-HIGH" not in answer


def test_task_recommendation_is_conditioned_without_llm(monkeypatch):
    monkeypatch.setattr(intelligence, "get_tasks", _fake_tasks)
    monkeypatch.setattr(
        intelligence,
        "_synthesize_memory_answer",
        _fail_if_llm_is_called,
    )

    answer = intelligence._decide_memory(
        "por cual empiezo",
        ["tasks"],
        chat_history=[],
    )

    lowered = answer.lower()

    assert "T-HIGH" in answer
    assert "prioridad" in lowered
    assert "dependencias" in lowered
    assert "impacto" in lowered


def test_normal_task_list_preserves_existing_direct_formatter(monkeypatch):
    monkeypatch.setattr(intelligence, "get_tasks", _fake_tasks)
    monkeypatch.setattr(
        intelligence,
        "format_tasks_answer",
        lambda tasks, question="": "LISTA DIRECTA DE TAREAS",
    )
    monkeypatch.setattr(
        intelligence,
        "_synthesize_memory_answer",
        _fail_if_llm_is_called,
    )

    answer = intelligence._decide_memory(
        "lista tareas pendientes",
        ["tasks"],
        chat_history=[],
    )

    assert answer == "LISTA DIRECTA DE TAREAS"