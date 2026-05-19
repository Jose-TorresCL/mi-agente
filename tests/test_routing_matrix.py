"""R3 — Matriz de evaluación de routing (nivel 1 de evaluación)

Basado en: An Assessment Framework for Evaluating Agentic AI Systems (arXiv, 2025)
Nivel evaluado: routing correcto ANTES de evaluar calidad de respuesta.

Principio determinista: NO se usa LLM-as-Judge.
Cada caso define expected_lane explícita → se compara con route_query() directamente.
Esto evita la trampa circular de usar llama3.2 para evaluar sus propias decisiones.

Cobertura: 9 tipos de carril × 3 ejemplos = 27 casos.

Tipos cubiertos:
  1. exit               → palabras de salida
  2. tool_list_files    → listar archivos del proyecto
  3. tool_read_file     → leer/abrir un archivo específico
  4. tool_save_fact     → guardar un hecho
  5. tool_create_task   → crear una tarea
  6. tool_complete_task → completar una tarea
  7. memory             → consultas de memoria (perfil, estado, tareas, episodios)
  8. rag                → preguntas sobre documentos/código
  9. unsupported        → preguntas cuantitativas aún no soportadas

Cómo correr:
    pytest tests/test_routing_matrix.py -v

Nota: route_query() depende de SESSION_STATS (contador de sesión) pero eso
no afecta el carril retornado — solo actualiza contadores internos.
"""
import pytest
from app.router import route_query


# ─────────────────────────────────────────────
# Matriz de casos
# Cada tupla: (pregunta, carril_esperado, descripcion)
# ─────────────────────────────────────────────

ROUTING_MATRIX = [

    # ── 1. exit ────────────────────────────────────────────────────────────
    ("salir",                           "exit",              "exit: palabra exacta"),
    ("chao",                            "exit",              "exit: despedida informal"),
    ("bye",                             "exit",              "exit: despedida en inglés"),

    # ── 2. tool_list_files ─────────────────────────────────────────────────
    ("listar archivos",                 "tool_list_files",   "list: keyword exacta"),
    ("qué archivos hay en el proyecto", "tool_list_files",   "list: variante con 'qué archivos'"),
    ("mostrar archivos del proyecto",   "tool_list_files",   "list: variante con 'mostrar'"),

    # ── 3. tool_read_file ──────────────────────────────────────────────────
    ("leer archivo router.py",          "tool_read_file",    "read: ruta detectada por extract_file_path"),
    ("muéstrame el archivo config.py",  "tool_read_file",    "read: keyword + nombre archivo"),
    ("abre el archivo memory_manager.py", "tool_read_file",  "read: keyword 'abre'"),

    # ── 4. tool_save_fact ──────────────────────────────────────────────────
    ("guarda como hecho: el proyecto usa Python 3.11",
                                        "tool_save_fact",    "save_fact: keyword exacta"),
    ("registra que el modelo es llama3.2",
                                        "tool_save_fact",    "save_fact: keyword 'registra que'"),
    ("anota que usamos Chroma como vector store",
                                        "tool_save_fact",    "save_fact: keyword 'anota que'"),

    # ── 5. tool_create_task ────────────────────────────────────────────────
    ("crea una tarea: implementar R4",  "tool_create_task",  "create_task: keyword exacta"),
    ("agregar tarea: revisar métricas", "tool_create_task",  "create_task: keyword 'agregar tarea'"),
    ("nueva tarea: escribir ADR-006",   "tool_create_task",  "create_task: keyword 'nueva tarea'"),

    # ── 6. tool_complete_task ──────────────────────────────────────────────
    ("marca como completada la tarea T-1",
                                        "tool_complete_task","complete_task: keyword exacta"),
    ("marcar como completado T-3",      "tool_complete_task","complete_task: con ID"),
    ("cierra la tarea T-2",             "tool_complete_task","complete_task: keyword 'cierra'"),

    # ── 7. memory ──────────────────────────────────────────────────────────
    # sub-tipo: profile
    ("¿cuál es mi perfil?",             "memory",            "memory/profile: pregunta de perfil"),
    # sub-tipo: work_state
    ("¿cuál es mi foco actual?",        "memory",            "memory/work_state: foco actual"),
    # sub-tipo: tasks
    ("¿qué tareas tengo pendientes?",   "memory",            "memory/tasks: tareas pendientes"),
    # sub-tipo: episode
    ("¿qué aprendí la sesión anterior?","memory",            "memory/episode: episodio pasado"),

    # ── 8. rag ─────────────────────────────────────────────────────────────
    ("¿cómo funciona el router del agente?",
                                        "rag",               "rag: hint 'cómo funciona'"),
    ("explícame la arquitectura del proyecto",
                                        "rag",               "rag: hint 'explica' + 'arquitectura'"),
    ("¿qué hace intelligence.py?",      "rag",               "rag: hint 'qué hace'"),

    # ── 9. unsupported ─────────────────────────────────────────────────────
    ("¿cuántas líneas de código tiene el proyecto?",
                                        "unsupported",       "unsupported: métrica de líneas"),
    ("¿cuántos archivos tiene el proyecto?",
                                        "unsupported",       "unsupported: conteo de archivos"),
    ("¿cuántas funciones hay en el código?",
                                        "unsupported",       "unsupported: conteo de funciones"),
]


# ─────────────────────────────────────────────
# Test parametrizado — determinista, sin LLM
# ─────────────────────────────────────────────

@pytest.mark.parametrize("question,expected_lane,description", ROUTING_MATRIX)
def test_routing_matrix(question: str, expected_lane: str, description: str):
    """Verifica que route_query() devuelve el carril correcto para cada caso.

    Evaluación nivel 1 según arXiv:2025 Assessment Framework:
    'routing correcto' es el prerequisito de cualquier evaluación de calidad.
    """
    actual_lane = route_query(question)
    assert actual_lane == expected_lane, (
        f"\n[FALLO] {description}"
        f"\n  Pregunta:   '{question}'"
        f"\n  Esperado:   '{expected_lane}'"
        f"\n  Obtenido:   '{actual_lane}'"
        f"\n  → Revisar keywords en router.py o umbral de embeddings."
    )


# ─────────────────────────────────────────────
# Test de cobertura de tipos
# ─────────────────────────────────────────────

def test_matrix_covers_all_lane_types():
    """Verifica que la matriz cubre los 9 tipos de carril definidos."""
    lanes_in_matrix = {lane for _, lane, _ in ROUTING_MATRIX}
    required_lanes = {
        "exit",
        "tool_list_files",
        "tool_read_file",
        "tool_save_fact",
        "tool_create_task",
        "tool_complete_task",
        "memory",
        "rag",
        "unsupported",
    }
    missing = required_lanes - lanes_in_matrix
    assert not missing, (
        f"La matriz no cubre estos tipos de carril: {missing}\n"
        f"Agrega al menos un caso por tipo."
    )


def test_matrix_has_minimum_cases_per_lane():
    """Cada tipo de carril debe tener al menos 2 casos en la matriz."""
    from collections import Counter
    lane_counts = Counter(lane for _, lane, _ in ROUTING_MATRIX)
    for lane, count in lane_counts.items():
        assert count >= 2, (
            f"El carril '{lane}' solo tiene {count} caso(s). "
            f"Se requieren al menos 2 por tipo para robustez."
        )
