from __future__ import annotations

from app.tools import extract_file_path


TOOL_LIST_KEYWORDS = [
    "listar archivos",
    "lista de archivos",
    "qué archivos",
    "que archivos",
    "archivos del proyecto",
    "ver archivos",
    "mostrar archivos",
    "muéstrame los archivos",
    "muestrame los archivos",
    "qué hay en el proyecto",
    "que hay en el proyecto",
]


TOOL_READ_KEYWORDS = [
    "leer archivo",
    "muéstrame el archivo",
    "muestrame el archivo",
    "abre el archivo",
    "ver archivo",
    "mostrar archivo",
    "lee el archivo",
    "leer docs",
    "leer documentación",
    "leer documento",
    "mostrar documento",
]


MEMORY_PROFILE_KEYWORDS = [
    "mi estilo",
    "estilo preferido",
    "preferencia",
    "preferido",
    "cómo prefiero",
    "como prefiero",
    "cómo trabajo",
    "como trabajo",
    "perfil",
    "mi perfil",
]


MEMORY_WORK_STATE_KEYWORDS = [
    "estado actual",
    "foco actual",
    "siguiente paso",
    "en qué vamos",
    "en que vamos",
    "qué sigue",
    "que sigue",
    "en qué estoy",
    "en que estoy",
    "qué estoy haciendo",
    "que estoy haciendo",
    "último paso",
    "ultimo paso",
    "en qué quedamos",
    "en que quedamos",
]


MEMORY_TASKS_KEYWORDS = [
    "tareas",
    "pendientes",
    "pendiente",
    "qué tareas hay",
    "que tareas hay",
    "mis tareas",
    "lista de tareas",
]


MEMORY_PROJECT_FACTS_KEYWORDS = [
    "fase actual",
    "fase del proyecto",
    "estado del proyecto",
    "hechos del proyecto",
    "datos del proyecto",
    "en qué fase",
    "en que fase",
    "nombre del proyecto",
]


TOOL_SAVE_FACT_KEYWORDS = [
    "guarda como hecho",
    "guardar hecho",
    "registra que",
    "anota que",
    "guarda el hecho",
    "registra el hecho",
    "guarda esto como hecho",
]


TOOL_CREATE_TASK_KEYWORDS = [
    "crea una tarea",
    "crear tarea",
    "agrega una tarea",
    "agregar tarea",
    "nueva tarea",
    "añade una tarea",
    "anota una tarea",
    "registra una tarea",
]


# ── Nuevos carriles — Fase 2 ─────────────────────────────────────────────

TOOL_COMPLETE_TASK_KEYWORDS = [
    "marca como completada",
    "marca como completado",
    "marcar como completada",
    "marcar como completado",
    "cierra la tarea",
    "cerrar tarea",
    "completé la tarea",
    "complete la tarea",
    "tarea completada",
    "done T-",
    "completar T-",
    "completar tarea",
]


TOOL_UPDATE_WORK_STATE_KEYWORDS = [
    "actualiza el foco",
    "actualiza foco",
    "cambia el foco",
    "cambia foco",
    "actualiza work_state",
    "actualiza el estado de trabajo",
    "actualiza estado de trabajo",
    "cambia next_step",
    "cambia siguiente paso",
    "actualiza siguiente paso",
    "pon en siguiente paso",
    "actualiza la fase",
    "cambia la fase",
    "estoy trabajando en",
    "ahora estoy en",
    "cambia el último paso",
    "actualiza el último paso",
    "nuevo bloqueo",
    "actualiza bloqueante",
    "cambia bloqueante",
]


RAG_HINTS = [
    "según los documentos",
    "segun los documentos",
    "según la documentación",
    "segun la documentación",
    "qué dice",
    "que dice",
    "explica",
    "explícame",
    "explicame",
    "arquitectura",
    "objetivo",
    "relación entre",
    "relacion entre",
    "documentación",
    "documentacion",
]


def classify_memory_query(question: str) -> str | None:
    """Devuelve el tipo de memoria que corresponde, o None si no aplica."""
    q = question.lower().strip()

    if any(keyword in q for keyword in MEMORY_PROFILE_KEYWORDS):
        return "profile"

    if any(keyword in q for keyword in MEMORY_WORK_STATE_KEYWORDS):
        return "work_state"

    if any(keyword in q for keyword in MEMORY_TASKS_KEYWORDS):
        return "tasks"

    if any(keyword in q for keyword in MEMORY_PROJECT_FACTS_KEYWORDS):
        return "project_facts"

    return None


def route_query(question: str) -> str:
    """Clasifica la pregunta y devuelve el carril de ejecución correcto.

    Carriles disponibles:
    - tool_list_files
    - tool_read_file
    - tool_save_fact
    - tool_create_task
    - tool_complete_task      (Fase 2)
    - tool_update_work_state  (Fase 2)
    - memory
    - rag
    """
    q = question.lower().strip()

    # Tools de escritura (prioridad alta: intención explícita)
    if any(keyword in q for keyword in TOOL_SAVE_FACT_KEYWORDS):
        return "tool_save_fact"

    if any(keyword in q for keyword in TOOL_CREATE_TASK_KEYWORDS):
        return "tool_create_task"

    # Nuevos carriles Fase 2
    if any(keyword in q for keyword in TOOL_COMPLETE_TASK_KEYWORDS):
        return "tool_complete_task"

    if any(keyword in q for keyword in TOOL_UPDATE_WORK_STATE_KEYWORDS):
        return "tool_update_work_state"

    # Tools de lectura de archivos
    if extract_file_path(question) is not None:
        return "tool_read_file"

    if any(keyword in q for keyword in TOOL_LIST_KEYWORDS):
        return "tool_list_files"

    if any(keyword in q for keyword in TOOL_READ_KEYWORDS):
        return "tool_read_file"

    # Memoria estructurada
    memory_kind = classify_memory_query(question)
    if memory_kind is not None:
        return "memory"

    # RAG (fallback documental)
    if any(keyword in q for keyword in RAG_HINTS):
        return "rag"

    return "rag"
