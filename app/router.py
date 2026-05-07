"""Router híbrido — Fase 3B

Estrategia en tres capas:
  1. _route_by_keywords()   → instantáneo, sin costo de modelo.
     Si la pregunta tiene una keyword conocida, devuelve el carril directo.
     Devuelve None si no reconoce nada (señal explícita de "no sé").

  2. _route_by_embeddings() → ~50ms, consulta storage/intent_index.
     Busca la frase más similar en el índice y devuelve su carril.
     Solo activa si la similitud supera el umbral EMBED_THRESHOLD.
     Usa singleton _intent_db para no recrear Chroma en cada consulta.

  3. _route_by_llm()        → ~3-8s, solo si embeddings tiene baja confianza.
     Último recurso para frases muy nuevas o sin ningún ejemplo cercano.

Logging diferenciado:
  [router:kw]    → resuelto por keywords (0ms)
  [router:emb]   → resuelto por embeddings (~50ms)
  [router:llm]   → resuelto por LLM fallback (~3-8s)

Requisito previo para la Capa 2:
  Ejecutar python build_intent_index.py una vez para crear storage/intent_index.
  Si el índice no existe, la Capa 2 se salta silenciosamente y pasa a la Capa 3.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.tools import extract_file_path


# ─────────────────────────────────────────────
# Estadísticas de sesión — para !estado
# ─────────────────────────────────────────────

SESSION_STATS: dict[str, int] = {
    "kw":    0,   # Capa 1: keywords
    "emb":   0,   # Capa 2: embeddings
    "llm":   0,   # Capa 3: LLM fallback
    "total": 0,   # total de consultas en la sesión
}


# ─────────────────────────────────────────────
# Configuración de embeddings (Capa 2)
# ─────────────────────────────────────────────

INTENT_DIR      = Path("storage/intent_index")
EMBED_MODEL     = "nomic-embed-text"
OLLAMA_URL      = "http://localhost:11434"

# Umbral de similitud coseno [0.0 — 1.0].
# Chroma devuelve distancia: 0 = idéntico, 2 = opuesto.
# Convertimos a similitud: sim = 1 - (dist / 2).
# Por debajo de este umbral la Capa 2 renuncia y pasa a la Capa 3.
EMBED_THRESHOLD = 0.70

# Cuántos vecinos buscar. Con 1 es suficiente — queremos el más cercano.
EMBED_TOP_K     = 1

# ─────────────────────────────────────────────
# Singleton para intent_db (Capa 2)
# ─────────────────────────────────────────────

_intent_db = None
_intent_embeddings = None


def _get_intent_db():
    global _intent_db, _intent_embeddings
    if _intent_db is None:
        from langchain_ollama import OllamaEmbeddings
        from langchain_chroma import Chroma

        _intent_embeddings = OllamaEmbeddings(
            model=EMBED_MODEL,
            base_url=OLLAMA_URL,
        )
        _intent_db = Chroma(
            persist_directory=str(INTENT_DIR),
            embedding_function=_intent_embeddings,
            collection_name="intent_index",
        )
    return _intent_db


# ─────────────────────────────────────────────
# Palabras de salida — interceptadas antes de cualquier capa
# ─────────────────────────────────────────────

_EXIT_WORDS = {"salir", "by","salo", "sali", "salie", "sal" "exit", "quit", "bye", "chao", "adios", "adiós"}


# ─────────────────────────────────────────────
# Listas de keywords (Capa 1)
# ─────────────────────────────────────────────

TOOL_LIST_KEYWORDS = [
    "listar archivos", "lista de archivos", "qué archivos", "que archivos",
    "archivos del proyecto", "ver archivos", "mostrar archivos",
    "muéstrame los archivos", "muestrame los archivos",
    "qué hay en el proyecto", "que hay en el proyecto",
]

TOOL_READ_KEYWORDS = [
    "leer archivo", "muéstrame el archivo", "muestrame el archivo",
    "abre el archivo", "ver archivo", "mostrar archivo", "lee el archivo",
    "leer docs", "leer documentación", "leer documento", "mostrar documento",
]

MEMORY_PROFILE_KEYWORDS = [
    "mi estilo", "estilo preferido", "preferencia", "preferido",
    "cómo prefiero", "como prefiero", "cómo trabajo", "como trabajo",
    "perfil", "mi perfil",
]

MEMORY_WORK_STATE_KEYWORDS = [
    "estado actual", "foco actual", "siguiente paso",
    "en qué vamos", "en que vamos", "qué sigue", "que sigue",
    "en qué estoy", "en que estoy", "qué estoy haciendo", "que estoy haciendo",
    "último paso", "ultimo paso", "en qué quedamos", "en que quedamos",
]

MEMORY_TASKS_KEYWORDS = [
    "qué tareas hay", "que tareas hay",
    "mis tareas", "mis tareas pendientes",
    "lista de tareas pendientes",
    "tareas pendientes", "tareas abiertas",
    "qué tengo pendiente", "que tengo pendiente",
    "qué tareas tengo", "que tareas tengo",
    "ponme al día", "ponme al dia",
    # Fix: frases cortas que antes caían a embeddings con baja similitud
    "tareas", "mis tareas", "ver tareas", "mostrar tareas",
]

# Palabras que indican intención de SUGERIR/CREAR — si aparecen junto a "tareas",
# la Capa 1 debe abstenerse y dejar pasar a embeddings (RAG).
_TASK_SUGGESTION_SIGNALS = [
    "podríamos", "podriamos", "podrías", "podrias",
    "nuevas", "nuevo", "crear", "agregar", "sugerir",
    "posibles", "ideas", "proponer", "qué más", "que mas",
    "implementar", "añadir", "añade",
]

MEMORY_PROJECT_FACTS_KEYWORDS = [
    "fase actual", "fase del proyecto", "estado del proyecto",
    "hechos del proyecto", "datos del proyecto",
    "en qué fase", "en que fase", "nombre del proyecto",
]

TOOL_SAVE_FACT_KEYWORDS = [
    "guarda como hecho", "guardar hecho", "registra que", "anota que",
    "guarda el hecho", "registra el hecho", "guarda esto como hecho",
]

TOOL_CREATE_TASK_KEYWORDS = [
    "crea una tarea", "crear tarea", "agrega una tarea", "agregar tarea",
    "nueva tarea", "añade una tarea", "anota una tarea", "registra una tarea",
]

TOOL_COMPLETE_TASK_KEYWORDS = [
    "marca como completada", "marca como completado",
    "marcar como completada", "marcar como completado",
    "cierra la tarea", "cerrar tarea",
    "completé la tarea", "complete la tarea",
    "tarea completada", "completar tarea",
    "como completada", "como completado",
]

_COMPLETE_TASK_PATTERN = re.compile(
    r"(marca|marcar|cierra|cerrar|completar|completé|complete)\s+t-\d+",
    re.IGNORECASE,
)

TOOL_UPDATE_WORK_STATE_KEYWORDS = [
    "actualiza el foco", "actualiza foco", "cambia el foco", "cambia foco",
    "actualiza work_state", "actualiza el estado de trabajo",
    "actualiza estado de trabajo", "cambia next_step",
    "cambia siguiente paso", "actualiza siguiente paso", "pon en siguiente paso",
    "actualiza la fase", "cambia la fase",
    "estoy trabajando en", "ahora estoy en",
    "cambia el último paso", "actualiza el último paso",
    "nuevo bloqueo", "actualiza bloqueante", "cambia bloqueante",
]

RAG_HINTS = [
    "según los documentos", "segun los documentos",
    "según la documentación", "segun la documentación",
    "según los archivos", "segun los archivos",
    "qué dice", "que dice", "explica", "explícame", "explicame",
    "arquitectura", "objetivo", "relación entre", "relacion entre",
    "documentación", "documentacion",
]

VALID_LANES = {
    "tool_list_files", "tool_read_file", "tool_save_fact",
    "tool_create_task", "tool_complete_task", "tool_update_work_state",
    "memory", "rag",
}

_CLASSIFICATION_PROMPT = """Eres un clasificador de intenciones para un asistente local.
Tu única tarea es identificar a qué carril pertenece la pregunta del usuario.

Carriles disponibles y cuándo usarlos:
- tool_create_task    : el usuario quiere crear, apuntar, registrar o agregar una tarea nueva
- tool_complete_task  : el usuario quiere marcar, cerrar o completar una tarea existente
- tool_update_work_state : el usuario quiere cambiar el foco, fase, siguiente paso o estado de trabajo
- tool_save_fact      : el usuario quiere guardar un hecho, dato o información del proyecto
- tool_list_files     : el usuario quiere ver la LISTA DE ARCHIVOS del proyecto (solo esto)
- tool_read_file      : el usuario quiere leer el CONTENIDO de un archivo específico
- memory              : el usuario pregunta por su perfil, tareas EXISTENTES, estado actual o hechos guardados
- rag                 : preguntas sobre funcionamiento, componentes, fases, conceptos, tools, arquitectura o SUGERENCIAS

IMPORTANTE — memory vs rag para tareas:
  "qué tareas tengo pendientes"                  → memory   (consulta tareas existentes)
  "hazme una lista de tareas que podríamos crear" → rag     (pide sugerencias nuevas)
  "qué más podríamos implementar"                 → rag
  "según los documentos qué falta por hacer"      → rag

Ejemplos:
"apunta que tengo que revisar el router"   → tool_create_task
"ya terminé con la tarea del router"       → tool_complete_task
"cambia mi foco a fase 3"                  → tool_update_work_state
"ponme al día de lo que hice ayer"         → memory
"qué tengo pendiente"                      → memory
"en qué fase estamos"                      → memory
"qué tools están operativas"               → rag
"cómo funciona Chroma"                     → rag
"cuáles son los componentes del sistema"   → rag
"muéstrame los archivos del proyecto"      → tool_list_files

Responde únicamente con el nombre del carril, sin explicación ni texto adicional.

Pregunta del usuario: "{question}"
Carril:"""


# ─────────────────────────────────────────────
# Funciones internas
# ─────────────────────────────────────────────

def _has_task_suggestion_signal(q: str) -> bool:
    return any(signal in q for signal in _TASK_SUGGESTION_SIGNALS)


def classify_memory_query(question: str) -> str | None:
    q = question.lower().strip()
    if any(k in q for k in MEMORY_PROFILE_KEYWORDS):       return "profile"
    if any(k in q for k in MEMORY_WORK_STATE_KEYWORDS):    return "work_state"
    if any(k in q for k in MEMORY_TASKS_KEYWORDS) \
            and not _has_task_suggestion_signal(q):         return "tasks"
    if any(k in q for k in MEMORY_PROJECT_FACTS_KEYWORDS): return "project_facts"
    return None


def _route_by_keywords(question: str) -> str | None:
    q = question.lower().strip()

    # Fix: interceptar !estatus como alias de !estado (comando de chat)
    if q in {"!estatus", "!status"}:
        return "!estado"  # chat.py lo maneja como comando especial

    if any(k in q for k in TOOL_SAVE_FACT_KEYWORDS):         return "tool_save_fact"
    if any(k in q for k in TOOL_CREATE_TASK_KEYWORDS):        return "tool_create_task"
    if any(k in q for k in TOOL_COMPLETE_TASK_KEYWORDS) \
            or _COMPLETE_TASK_PATTERN.search(q):              return "tool_complete_task"
    if any(k in q for k in TOOL_UPDATE_WORK_STATE_KEYWORDS):  return "tool_update_work_state"
    if extract_file_path(question) is not None:               return "tool_read_file"
    if any(k in q for k in TOOL_LIST_KEYWORDS):               return "tool_list_files"
    if any(k in q for k in TOOL_READ_KEYWORDS):               return "tool_read_file"
    if classify_memory_query(question) is not None:           return "memory"
    if any(k in q for k in RAG_HINTS):                        return "rag"
    return None


def _route_by_embeddings(question: str) -> str | None:
    if not INTENT_DIR.exists():
        return None

    try:
        vectordb = _get_intent_db()

        results = vectordb.similarity_search_with_score(
            query=question,
            k=EMBED_TOP_K,
        )

        if not results:
            return None

        doc, distance = results[0]
        similarity = 1.0 - (distance / 2.0)
        lane = doc.metadata.get("lane", "")

        print(f"[router:emb] similitud={similarity:.2f} lane_candidato={lane}")

        if similarity >= EMBED_THRESHOLD and lane in VALID_LANES:
            return lane

        print(f"[router:emb] similitud baja ({similarity:.2f} < {EMBED_THRESHOLD}) → pasa a LLM")
        return None

    except Exception as e:
        print(f"[router:emb] error: {e} → pasa a LLM")
        return None


def _route_by_llm(question: str) -> str:
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
                    "temperature": 0,
                    "num_predict": 10,
                    "stop": ["\n", " ", "."]
                },
            },
            timeout=30,
        )
        raw = response.json().get("response", "").strip().lower()
        lane = raw.strip("\"' \n\t")

        if lane in VALID_LANES:
            return lane

        print(f"[router:llm] respuesta inesperada: '{raw}' → rag")
        return "rag"

    except Exception as e:
        print(f"[router:llm] error: {e} → rag")
        return "rag"


# ─────────────────────────────────────────────
# Punto de entrada público
# ─────────────────────────────────────────────

def route_query(question: str) -> str:
    """Clasifica la pregunta en el carril de ejecución correcto."""
    if question.lower().strip() in _EXIT_WORDS:
        return "exit"

    SESSION_STATS["total"] += 1

    kw_lane = _route_by_keywords(question)

    if kw_lane is not None:
        SESSION_STATS["kw"] += 1
        print(f"[router:kw]  '{question[:50]}' → {kw_lane}")
        return kw_lane

    emb_lane = _route_by_embeddings(question)
    if emb_lane is not None:
        SESSION_STATS["emb"] += 1
        print(f"[router:emb] '{question[:50]}' → {emb_lane}")
        return emb_lane

    SESSION_STATS["llm"] += 1
    llm_lane = _route_by_llm(question)
    print(f"[router:llm] '{question[:50]}' → {llm_lane}")
    return llm_lane
