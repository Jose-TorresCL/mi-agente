import pytest

from app.router import debug_route_layers


@pytest.mark.parametrize(
    ("question", "expected_lane"),
    [
        ("cuál es la de más alta prioridad", "memory:tasks"),
        ("cuáles son las tareas más importantes", "memory:tasks"),
        ("por cuál empiezo", "memory:tasks"),
        ("qué me recomendás atacar primero", "memory:tasks"),
        ("cómo definimos prioridad alta en el ADR", "rag"),
        ("marcá como terminada la última tarea", "tool_complete_task"),
    ],
)
def test_task_query_routing_contract(question: str, expected_lane: str) -> None:
    result = debug_route_layers(question)

    assert result["lane"] == expected_lane