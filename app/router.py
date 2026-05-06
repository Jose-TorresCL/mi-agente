"""Router híbrido — Fase 3A

Estrategia en dos capas:
  1. _route_by_keywords()  → instantáneo, sin costo de LLM.
     Si la pregunta tiene una keyword conocida, devuelve el carril directo.

  2. _route_by_llm()       → solo cuando keywords no encontró nada útil.
     Le pregunta al LLM (Ollama local) qué carril corresponde.
     Paga latencia solo en frases ambiguas o nuevas.

Logging diferenciado:
  [router:kw]  → fue resuelto por keywords
  [router:llm] → fue resuelto por LLM fallback
"""
from __future__ import annotations

import re
import json

from app.tools import extract_file_path


# ─────────────────────────────────────────────
# Listas de keywords (capa 1)
# ─────────────────────────────────────────────

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
    "completar tarea",
    "como completada",
    "como completado",
]

# \d+ acepta IDs de cualquier longitud: T-003, T-0506132952, etc.
_COMPLETE_TASK_PATTERN = re.compile(
    r"(marca|marcar|cierra|cerrar|completar|completé|complete)\s+t-\d+",
    re.IGNORECASE,
)

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

# Carriles válidos que el LLM puede devolver
VALID_LANES = {
    "tool_list_files",
    "tool_read_file",
    "tool_save_fact",
    "tool_create_task",
    "tool_complete_task",
    "tool_update_work_state",
    "memory",
    "rag",
}

# Prompt de clasificación para el LLM fallback
_CLASSIFICATION_PROMPT = """Eres un clasificador de intenciones para un asistente local.
Tu única tarea es identificar a qué carril pertenece la pregunta del usuario.

Carriles disponibles y cuándo usarlos:
- tool_create_task    : el usuario quiere crear, apuntar, registrar o agregar una tarea o pendiente
- tool_complete_task  : el usuario quiere marcar, cerrar o completar una tarea existente
- tool_update_work_state : el usuario quiere cambiar el foco, fase, siguiente paso o estado de trabajo
- tool_save_fact      : el usuario quiere guardar un hecho, dato o información del proyecto
- tool_list_files     : el usuario quiere ver qué archivos existen en el proyecto
- tool_read_file      : el usuario quiere leer el contenido de un archivo específico
- memory              : el usuario pregunta por su perfil, tareas, estado actual o hechos del proyecto
- rag                 : cualquier otra pregunta documental o conceptual

Ejemplos:
"apunta que tengo que revisar el router" → tool_create_task
"ponme al día de lo que hice ayer" → memory
"cuéntame cómo funciona Chroma" → rag
"ya terminé con la tarea del router" → tool_complete_task
"cambia mi foco a fase 3" → tool_update_work_state
"qué tengo pendiente" → memory

Responde únicamente con el nombre del carril, sin explicación ni texto adicional.

Pregunta del usuario: "{question}"
Carril:"""


# ─────────────────────────────────────────────
# Funciones internas
# ─────────────────────────────────────────────

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


def _route_by_keywords(question: str) -> str:
    """Capa 1: clasifica por keywords. Rápido, sin costo de LLM.

    Devuelve 'rag' si no encontró ninguna keyword conocida,
    lo que indica que la capa 2 (LLM) debe tomar el relevo.
    """
    q = question.lower().strip()

    if any(keyword in q for keyword in TOOL_SAVE_FACT_KEYWORDS):
        return "tool_save_fact"
    if any(keyword in q for keyword in TOOL_CREATE_TASK_KEYWORDS):
        return "tool_create_task"
    if any(keyword in q for keyword in TOOL_COMPLETE_TASK_KEYWORDS) \
            or _COMPLETE_TASK_PATTERN.search(q):
        return "tool_complete_task"
    if any(keyword in q for keyword in TOOL_UPDATE_WORK_STATE_KEYWORDS):
        return "tool_update_work_state"
    if extract_file_path(question) is not None:
        return "tool_read_file"
    if any(keyword in q for keyword in TOOL_LIST_KEYWORDS):
        return "tool_list_files"
    if any(keyword in q for keyword in TOOL_READ_KEYWORDS):
        return "tool_read_file"
    if classify_memory_query(question) is not None:
        return "memory"
    if any(keyword in q for keyword in RAG_HINTS):
        return "rag"

    # No encontró nada concreto → señal para que el LLM clasifique
    return "rag"


def _route_by_llm(question: str) -> str:
    """Capa 2: usa el LLM local para clasificar frases ambiguas.

    Solo se llama cuando _route_by_keywords() no encontró ninguna
    keyword específica. Timeout de 30s para sobrevivir el cold start
    de Ollama (primera llamada tras inactividad).

    Si el LLM falla o devuelve un carril inválido, retorna 'rag'
    de forma segura (nunca lanza excepción).
    """
    try:
        import requests
        prompt = _CLASSIFICATION_PROMPT.format(question=question)
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2:latest",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0,       # máximo determinismo
                    "num_predict": 10,      # solo necesitamos el nombre del carril
                    "stop": ["\n", " ", "."]  # corta en cuanto termina la palabra
                },
            },
            timeout=30,  # 30s para sobrevivir cold start de Ollama
        )
        raw = response.json().get("response", "").strip().lower()

        # Limpia espacios, comillas o saltos que el LLM pueda añadir
        lane = raw.strip("\"' \n\t")

        if lane in VALID_LANES:
            return lane

        # Si devolvió algo inesperado, log y fallback seguro
        print(f"[router:llm] respuesta inesperada del LLM: '{raw}' → rag")
        return "rag"

    except Exception as e:
        print(f"[router:llm] error al clasificar: {e} → rag")
        return "rag"


# ─────────────────────────────────────────────
# Punto de entrada público
# ─────────────────────────────────────────────

def route_query(question: str) -> str:
    """Clasifica la pregunta en el carril de ejecución correcto.

    Flujo híbrido:
      1. Intenta clasificar por keywords (0ms, sin LLM).
      2. Si keywords no encontró nada específico, delega al LLM
         para frases ambiguas o con vocabulario nuevo.
    """
    # Capa 1: keywords — rápido
    kw_lane = _route_by_keywords(question)

    # Si encontró algo concreto O hay hints explícitos de RAG → va directo
    has_rag_hint = any(hint in question.lower() for hint in RAG_HINTS)

    if kw_lane != "rag" or has_rag_hint:
        print(f"[router:kw]  '{question[:50]}' → {kw_lane}")
        return kw_lane

    # Capa 2: LLM fallback — solo para frases sin keyword conocida
    llm_lane = _route_by_llm(question)
    print(f"[router:llm] '{question[:50]}' → {llm_lane}")
    return llm_lane
