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

from app.config import MODEL_NAME, OLLAMA_URL
from app.tools import extract_file_path
from app.logger import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────
# Estadísticas de sesión — para !estado
# ─────────────────────────────────────────────

SESSION_STATS: dict[str, int] = {
    "kw":    0,
    "emb":   0,
    "llm":   0,
    "total": 0,
}


# ─────────────────────────────────────────────
# Configuración de embeddings (Capa 2)
# ─────────────────────────────────────────────

INTENT_DIR      = Path("storage/intent_index")
EMBED_MODEL     = "nomic-embed-text"
EMBED_THRESHOLD = 0.70
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
# Palabras de salida
# ─────────────────────────────────────────────

_EXIT_WORDS = {
    "salir", "exit", "quit", "bye",
    "sal", "salo", "sali", "salie",
    "chao", "chau",
    "adios", "adiós",
    "hasta luego", "hasta pronto",
    "nos vemos",
    "me voy", "cierro",
    "by",
}


# ─────────────────────────────────────────────
# Carriles de escritura
# ─────────────────────────────────────────────

_WRITE_LANES = {"tool_save_fact", "tool_create_task", "tool_complete_task", "tool_update_work_state"}


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
    # fix #9: frases de identidad
    "quién soy", "quien soy",
    "quién soy yo", "quien soy yo",
    "cómo me llamo", "como me llamo",
    "mi nombre", "cuál es mi nombre", "cual es mi nombre",
]

MEMORY_WORK_STATE_KEYWORDS = [
    "estado actual", "foco actual", "siguiente paso",
    "en qué vamos", "en que vamos", "qué sigue", "que sigue",
    "en qué estoy", "en que estoy", "qué estoy haciendo", "que estoy haciendo",
    "último paso", "ultimo paso", "en qué quedamos", "en que quedamos",
    # fix #8: frases naturales de estado
    "qué hago hoy", "que hago hoy",
    "cuál es el plan", "cual es el plan",
    "qué hicimos", "que hicimos",
    "en qué estamos", "en que estamos",
    "cuál es mi foco", "cual es mi foco",
    "qué estoy trabajando", "que estoy trabajando",
    "qué estaba haciendo", "que estaba haciendo",
    "a qué me dedico ahora", "a que me dedico ahora",
]

MEMORY_TASKS_KEYWORDS = [
    "qué tareas hay", "que tareas hay",
    "mis tareas", "mis tareas pendientes",
    "lista de tareas pendientes",
    "tareas pendientes", "tareas abiertas",
    "qué tengo pendiente", "que tengo pendiente",
    "qué tareas tengo", "que tareas tengo",
    "ponme al día", "ponme al dia",
    "tareas", "mis tareas", "ver tareas", "mostrar tareas",
]

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
    "complete la tarea",
    "tarea completada", "completar tarea",
    "como completada", "como completado",
]

_COMPLETE_TASK_PATTERN = re.compile(
    r"(marca|marcar|cierra|cerrar|completar|completé|complete)\s+t-\d+",
    re.IGNORECASE,
)

TOOL_UPDATE_WORK_STATE_KEYWORDS = [
    "actualiza el foco", "cambia el foco", "enfócate en", "ahora estoy en",
    "completé", "terminé", "acabé", "ya hice", "listo:",
    "termine", "acabe",
    "el siguiente paso es", "sigue:", "próximo paso",
    "nuevo bloqueo", "actualiza bloqueante", "actualiza el estado de trabajo",
]

RAG_HINTS = [
    "según los documentos", "segun los documentos",
    "según la documentación", "segun la documentación",
    "según los archivos", "segun los archivos",
    "qué dice", "que dice",
    "qué hace", "que hace",
    "cómo funciona", "como funciona",
    "cómo está", "como esta",
    "para qué sirve", "para que sirve",
    "explica", "explícame", "explicame",
    "arquitectura", "objetivo",
    "relación entre", "relacion entre",
    "componentes", "diferencia entre",
    "qué es", "que es",
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
  "qué tareas tengo pendientes"                  → memory
  "hazme una lista de tareas que podríamos crear" → rag
  "qué más podríamos implementar"                 → rag
  "según los documentos qué falta por hacer"      → rag

IMPORTANTE — memory para identidad y estado:
  "quién soy yo"                                 → memory
  "cómo me llamo"                                → memory
  "qué hago hoy"                                 → memory
  "cuál es mi foco actual"                       → memory
  "qué hicimos ayer"                             → memory

Ejemplos:
"apunta que tengo que revisar el router"   → tool_create_task
"ya terminé con la tarea del router"       → tool_complete_task
"cambia mi foco a fase 3"                  → tool_update_work_state
"ponme al día de lo que hice ayer"         → memory
"qué tengo pendiente"                      → memory
"en qué fase estamos"                      → memory
"quién soy yo"                             → memory
"qué hago hoy"                             → memory
"qué tools están operativas"               → rag
"cómo funciona Chroma"                     → rag
"muéstrame los archivos del proyecto"      → tool_list_files
"¿qué hace el router híbrido?"             → rag

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


def _is_question(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(("¿", "?")) or stripped.endswith("?")


def _route_by_keywords(question: str) -> str | None:
    """Capa 1: clasificación instantánea por keywords."""
    q = question.lower().strip()

    if q in {"!estatus", "!status"}:
        return "!estado"

    if any(k in q for k in TOOL_SAVE_FACT_KEYWORDS):         return "tool_save_fact"
    if any(k in q for k in TOOL_CREATE_TASK_KEYWORDS):        return "tool_create_task"
    if any(k in q for k in TOOL_COMPLETE_TASK_KEYWORDS) \
            or _COMPLETE_TASK_PATTERN.search(q):              return "tool_complete_task"
    if any(k in q for k in TOOL_UPDATE_WORK_STATE_KEYWORDS):  return "tool_update_work_state"
    if any(k in q for k in RAG_HINTS):                        return "rag"
    if extract_file_path(question) is not None:               return "tool_read_file"
    if any(k in q for k in TOOL_LIST_KEYWORDS):               return "tool_list_files"
    if any(k in q for k in TOOL_READ_KEYWORDS):               return "tool_read_file"
    if classify_memory_query(question) is not None:           return "memory"

    return None


def _route_by_embeddings(question: str) -> str | None:
    if not INTENT_DIR.exists():
        return None
    try:
        vectordb = _get_intent_db()
        results = vectordb.similarity_search_with_score(query=question, k=EMBED_TOP_K)
        if not results:
            return None
        doc, distance = results[0]
        similarity = 1.0 - (distance / 2.0)
        lane = doc.metadata.get("lane", "")
        log.debug("[router:emb] similitud=%.2f lane_candidato=%s", similarity, lane)
        if _is_question(question) and lane in _WRITE_LANES:
            log.debug("[router:emb] pregunta detectada — bloqueando '%s' → pasa a LLM", lane)
            return None
        if similarity >= EMBED_THRESHOLD and lane in VALID_LANES:
            return lane
        log.debug("[router:emb] similitud baja (%.2f < %.2f) → pasa a LLM", similarity, EMBED_THRESHOLD)
        return None
    except Exception as e:
        log.warning("[router:emb] error: %s → pasa a LLM", e)
        return None


def _route_by_llm(question: str) -> str:
    try:
        import requests
        prompt = _CLASSIFICATION_PROMPT.format(question=question)
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0, "num_predict": 10, "stop": ["\n", " ", "."]},
            },
            timeout=30,
        )
        raw = response.json().get("response", "").strip().lower()
        lane = raw.strip("\"' \n\t")
        if lane in VALID_LANES:
            return lane
        log.warning("[router:llm] respuesta inesperada: '%s' → rag", raw)
        return "rag"
    except Exception as e:
        log.error("[router:llm] error: %s → rag", e)
        return "rag"


# ─────────────────────────────────────────────
# !estado — display del estado de sesión
# ─────────────────────────────────────────────

def format_estado() -> str:
    """Genera el bloque de texto para el comando !estado / !estatus.

    Incluye:
      - Estadísticas del router (kw / emb / llm / total)
      - Stats de la caché semántica (hits, misses, entradas, ttl_hours)
    """
    from app.semantic_cache import cache_stats

    stats  = cache_stats()
    total  = SESSION_STATS["total"] or 1  # evitar división por cero
    kw_pct  = SESSION_STATS["kw"]  * 100 // total
    emb_pct = SESSION_STATS["emb"] * 100 // total
    llm_pct = SESSION_STATS["llm"] * 100 // total

    ttl_line = ""
    if "ttl_hours" in stats:
        ttl_line = f"  TTL caché:       {stats['ttl_hours']}h\n"

    return (
        f"\n{'─' * 40}\n"
        f" Estado de sesión\n"
        f"{'─' * 40}\n"
        f"  Consultas totales: {SESSION_STATS['total']}\n"
        f"  → Capa 1 (kw):    {SESSION_STATS['kw']}  ({kw_pct}%)\n"
        f"  → Capa 2 (emb):   {SESSION_STATS['emb']}  ({emb_pct}%)\n"
        f"  → Capa 3 (llm):   {SESSION_STATS['llm']}  ({llm_pct}%)\n"
        f"{'─' * 40}\n"
        f" Caché semántica\n"
        f"{'─' * 40}\n"
        f"  Hits:             {stats.get('hits', 0)}\n"
        f"  Misses:           {stats.get('misses', 0)}\n"
        f"  Entradas:         {stats.get('entries', 0)}\n"
        f"{ttl_line}"
        f"{'─' * 40}\n"
    )


# ─────────────────────────────────────────────
# Punto de entrada público
# ─────────────────────────────────────────────

def route_query(question: str) -> str:
    """Clasifica la pregunta en el carril de ejecución correcto.

    Returns str con el carril ('rag', 'memory', 'tool_*', 'exit').
    Nunca retorna None ni lanza excepciones — fallback a 'rag'.
    """
    if question.lower().strip() in _EXIT_WORDS:
        return "exit"

    SESSION_STATS["total"] += 1

    kw_lane = _route_by_keywords(question)
    if kw_lane is not None:
        SESSION_STATS["kw"] += 1
        log.info("[router:kw]  '%s' → %s", question[:50], kw_lane)
        return kw_lane

    emb_lane = _route_by_embeddings(question)
    if emb_lane is not None:
        SESSION_STATS["emb"] += 1
        log.info("[router:emb] '%s' → %s", question[:50], emb_lane)
        return emb_lane

    SESSION_STATS["llm"] += 1
    llm_lane = _route_by_llm(question)
    log.info("[router:llm] '%s' → %s", question[:50], llm_lane)
    return llm_lane
