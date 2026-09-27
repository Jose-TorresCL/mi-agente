import pytest
from app.router import route_query, debug_route_layers

# 🔑 Test 1: Recomendación de tareas → memory:reasoning
@pytest.mark.parametrize("question", [
    "por cual me recomiendas empezar",
    "qué me recomiendas empezar",
    "cuál tarea debería empezar",
    "qué me conviene hacer ahora",
    "qué tarea me conviene",
])
def test_task_recommendation_routing(question):
    lane = route_query(question)
    assert lane == "memory:reasoning", f"Expected memory:reasoning, got {lane}"

# 🔑 Test 2: Completar tarea → tool_complete_task
@pytest.mark.parametrize("question", [
    "marca como completada",
    "marca esta tarea como completada",
    "cerrar la tarea pendiente",
    "completar la tarea",
])
def test_complete_task_routing(question):
    lane = route_query(question)
    assert lane == "tool_complete_task", f"Expected tool_complete_task, got {lane}"

# 🔑 Test 3: Lectura de tarea → tool_read_file
def test_read_task_not_complete():
    question = "lee T-0901105847"
    lane = route_query(question)
    assert lane == "tool_read_file", f"Expected tool_read_file, got {lane}"

# 🔑 Test 4: Preguntas implícitas → detectadas como preguntas
@pytest.mark.parametrize("question", [
    "qué tarea me conviene",
    "cuál es la tarea más importante",
    "por qué no avanzo",
])
def test_is_question_detection(question):
    info = debug_route_layers(question)
    assert info["layer"] in ("kw", "emb", "fallback"), "Expected router to classify question"
