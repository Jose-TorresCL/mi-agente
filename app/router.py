"""Router híbrido — Fase 3B

Estrategia en tres capas:
  1. _route_by_keywords()   → instantáneo, sin costo de modelo.
     Si la pregunta tiene una keyword conocida, devuelve el carril directo.
     Devuelve None si no reconoce nada (señal explícita de "no sé").

  2. _route_by_embeddings() → ~50ms, consulta storage/intent_index.
     Busca la frase más similar en el índice y devuelve su carril.
     Solo activa si la similitud supera el umbral EMBED_THRESHOLD.
     Singleton gestionado por app.intent_index — el router no toca Chroma.

  3. Fallback directo → 'rag' sin llamada al LLM.
     Si Capa 1 y Capa 2 no resuelven, se asume RAG como carril seguro.
     Eliminado _route_by_llm() porque timeout=30s + modelo ocupado
     generando respuesta = 30s de espera inútil por turno.

Logging diferenciado:
  [router:kw]    → resuelto por keywords (0ms)
  [router:emb]   → resuelto por embeddings (~50ms)
  [router:llm]   → fallback directo a rag (0ms, sin llamada LLM)

Requisito previo para la Capa 2:
  Ejecutar python build_intent_index.py una vez para crear storage/intent_index.
  Si el índice no existe, la Capa 2 se salta silenciosamente.

Fix 6B:
  classify_memory_query: añadido tipo 'episode' para preguntas sobre
  sesiones anteriores, aprendizajes pasados y episodios de trabajo.
  Se conecta a memory_manager.get_episodic_context() en la fase 6B-2.

Fix R1-E:
  El singleton de Chroma para intent_index vive en app.intent_index.
  router.py es función pura de clasificación — sin imports de Chroma.

Fix P13:
  Agregado 'sprint' y variantes a MEMORY_PROJECT_FACTS_KEYWORDS.

Fix B1:
  Agregado '!estado' al set de comandos especiales en _route_by_keywords.
  Antes '!estado' caía a embeddings y se enrutaba como 'memory' (incorrecto).

Fix B2:
  Nueva lista AGENT_IDENTITY_KEYWORDS → carril 'identity'.
  Se evalúa ANTES de classify_memory_query en _route_by_keywords para que
  'quién eres tú', 'qué puedes hacer', etc. nunca lleguen al clasificador
  de embeddings y no caigan erróneamente en el carril 'memory' ni 'rag'.
  intelligence.py devuelve respuesta fija para este carril — 0ms, sin LLM.

Fix N1+N2:
  _normalize(text) movida a app/text_utils.py (fix-circular-import).
  router.py la importa desde allí. Mismo comportamiento, sin ciclo.
  Todas las listas de keywords solo tienen la versión sin tilde.

Fix N3:
  _COMPLETE_TASK_PATTERN ampliado: ahora acepta texto libre además de
  número de tarea. 'completé la tarea de tests' ahora matchea correctamente
  en tool_complete_task antes de llegar a tool_update_work_state.

Fix R4+R7:
  RAG_HINTS ahora se evalúa DESPUÉS de identity y memory en _route_by_keywords.
  Antes: 'que es lo que tengo pendiente' → RAG (por 'que es' en RAG_HINTS).
  Ahora: identity → memory → RAG_HINTS → fallback.
  Eliminadas de RAG_HINTS las keywords demasiado genéricas que competían con
  memory e identity: 'que es', 'objetivo', 'explicame', 'para que sirve',
  'componentes'. Solo quedan señales ineuquívocamente documentales.

Fix R6:
  Eliminadas 'crear', 'nuevo', 'nuevas' de _TASK_SUGGESTION_SIGNALS.
  Antes: 'crear tarea' bloqueaba el carril tasks porque 'crear' era señal
  de sugerencia. Ahora solo bloquean señales que indican intención de
  proponer ideas, no de ejecutar acciones.

Fix R8:
  Confirmado: route_query ya aplica _normalize() antes del chequeo de
  _EXIT_WORDS. 'Adiós', 'CHAO', 'hasta luego' matchean correctamente
  sin importar tildes ni mayúsculas.

Fix P5-Paso1:
  _route_by_keywords ahora retorna 'memory:<subtipo>' en vez de 'memory'.
  Ejemplos: 'memory:tasks', 'memory:profile', 'memory:work_state',
            'memory:project_facts', 'memory:episode'.
  Esto permite que intelligence.py use contexto selectivo en lugar de
  get_full_context(). Pendiente: Paso 2 (Capa 2) y Paso 4 (intelligence.py).
  VALID_LANES actualizado con los subtipos para que _route_by_embeddings
  no los rechace cuando la Capa 2 empiece a propagarlos.

Fix B3:
  Bug1 — extract_file_path disparaba tool_read_file para cualquier pregunta
  que mencionara un archivo (ej: '¿qué hace intelligence.py?'). Ahora se
  requiere que haya un verbo lector explícito (leer, abre, muéstrame, ver,
  lee, mostrar, abrir) junto con el nombre de archivo. Sin verbo, la pregunta
  sigue al siguiente carril (RAG_HINTS → rag).

  Bug2 — '¿qué es el retriever en LangChain?' llegaba a embeddings y se
  clasificaba como memory:work_state (similitud 0.71). Agregados a RAG_HINTS:
  'que es el', 'que es la', 'que es un', 'que es una'. Son señales
  inequívocamente documentales que la Capa 1 debe interceptar.

Fix B4:
  'para que sirve fidelity_check.py' llegaba a Capa 2 y se clasificaba
  como memory:project_facts (similitud 0.71). Agregado 'para que sirve'
  a RAG_HINTS para que la Capa 1 lo intercepte antes de embeddings.
  'para que sirves' (identity) se evalúa antes de RAG_HINTS → sin colisión.

Fix C1 (este commit):
  from app.tools import extract_file_path movido de nivel de módulo a
  import local dentro de _route_by_keywords(). Rompe el ciclo:
    router → tools → memory_manager → router (💥 antes)
  Mismo comportamiento funcional, sin ImportError al cargar el módulo.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from app.config import MODEL_NAME, OLLAMA_URL
from app.text_utils import _normalize
from app.logger import get_logger
from app import intent_index

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

EMBED_THRESHOLD = intent_index.EMBED_THRESHOLD
EMBED_TOP_K     = intent_index.EMBED_TOP_K


# ─────────────────────────────────────────────
# Palabras de salida
# ─────────────────────────────────────────────

_EXIT_WORDS = {
    "salir", "exit", "quit", "bye",
    "sal", "salo", "sali", "salie",
    "chao", "chau",
    "adios",
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
# Fix B3 — verbos lectores
# ─────────────────────────────────────────────

_READ_VERBS = {
    "leer", "lee", "abre", "abrir",
    "muestrame", "mostrar", "ver", "open",
}


def _has_read_verb(q_normalized: str) -> bool:
    return any(verb in q_normalized for verb in _READ_VERBS)


# ─────────────────────────────────────────────
# Listas de keywords (Capa 1)
# ─────────────────────────────────────────────

TOOL_LIST_KEYWORDS = [
    "listar archivos", "lista de archivos", "que archivos",
    "archivos del proyecto", "ver archivos", "mostrar archivos",
    "muestrame los archivos",
    "que hay en el proyecto",
]

TOOL_READ_KEYWORDS = [
    "leer archivo", "muestrame el archivo",
    "abre el archivo", "ver archivo", "mostrar archivo", "lee el archivo",
    "leer docs", "leer documentacion", "leer documento", "mostrar documento",
]

MEMORY_PROFILE_KEYWORDS = [
    "mi estilo", "estilo preferido", "preferencia", "preferido",
    "como prefiero", "como trabajo",
    "perfil", "mi perfil",
    "quien soy", "quien soy yo",
    "como me llamo", "mi nombre", "cual es mi nombre",
]

MEMORY_WORK_STATE_KEYWORDS = [
    "estado actual", "foco actual", "siguiente paso",
    "en que vamos", "que sigue",
    "en que estoy", "que estoy haciendo",
    "ultimo paso", "en que quedamos",
    "que hago hoy", "cual es el plan",
    "que hicimos", "en que estamos",
    "cual es mi foco", "que estoy trabajando",
    "que estaba haciendo", "a que me dedico ahora",
]

MEMORY_TASKS_KEYWORDS = [
    "que tareas hay", "mis tareas", "mis tareas pendientes",
    "lista de tareas pendientes",
    "tareas pendientes", "tareas abiertas",
    "que tengo pendiente", "que tareas tengo",
    "ponme al dia",
    "tareas", "ver tareas", "mostrar tareas",
    "tareas hechas", "tareas completadas", "tareas cerradas",
    "que tareas hice",
    "lista todas las tareas", "todas las tareas",
]

_TASK_SUGGESTION_SIGNALS = [
    "podriamos", "podrias",
    "agregar", "sugerir",
    "posibles", "ideas", "proponer", "que mas",
    "implementar", "anadir",
]

MEMORY_PROJECT_FACTS_KEYWORDS = [
    "fase actual", "fase del proyecto", "estado del proyecto",
    "hechos del proyecto", "datos del proyecto",
    "en que fase", "nombre del proyecto",
    "sprint", "en que sprint",
    "que sprint", "sprint actual",
]

MEMORY_EPISODE_KEYWORDS = [
    "que aprendi", "que aprendimos",
    "sesion anterior", "ultima sesion",
    "sesiones anteriores", "la semana pasada", "ayer trabajamos",
    "que hicimos antes", "que trabajamos",
    "historial de sesiones", "episodios anteriores",
    "que avance", "que avanzamos",
    "ultima vez que",
]

AGENT_IDENTITY_KEYWORDS = [
    "quien eres", "quien eres tu",
    "que eres", "que eres tu",
    "que puedes hacer", "que puedes",
    "que sabes hacer",
    "para que sirves",
    "cuentame de ti", "cuentame sobre ti",
    "dime quien eres",
    "como te llamas", "cual es tu nombre",
    "que modelo eres",
    "cuales son tus capacidades",
    "que herramientas tienes",
    "tus limites", "que no puedes hacer",
    "tus capacidades",
]

TOOL_SAVE_FACT_KEYWORDS = [
    "guarda como hecho", "guardar hecho", "registra que", "anota que",
    "guarda el hecho", "registra el hecho", "guarda esto como hecho",
]

TOOL_CREATE_TASK_KEYWORDS = [
    "crea una tarea", "crear tarea", "agrega una tarea", "agregar tarea",
    "nueva tarea", "anade una tarea", "anota una tarea", "registra una tarea",
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
    r"(marca|marcar|cierra|cerrar|completar|complete)\s+(t-\d+|la tarea|el issue|el paso)",
    re.IGNORECASE,
)

TOOL_UPDATE_WORK_STATE_KEYWORDS = [
    "actualiza el foco", "cambia el foco", "enfocate en", "ahora estoy en",
    "complete", "termine", "acabe", "ya hice", "listo:",
    "el siguiente paso es", "sigue:", "proximo paso",
    "nuevo bloqueo", "actualiza bloqueante", "actualiza el estado de trabajo",
]

TOOL_UNSUPPORTED_KEYWORDS = [
    "cuantas lineas",
    "lineas de codigo", "lineas tiene",
    "cuanto codigo",
    "tamano del proyecto", "peso del proyecto",
    "cuantos archivos hay", "cuantos archivos tiene",
    "cuantas funciones", "cuantas clases",
]

RAG_HINTS = [
    "segun los documentos",
    "segun la documentacion",
    "segun los archivos",
    "que dice", "que hace",
    "como funciona", "como esta",
    "arquitectura",
    "relacion entre",
    "diferencia entre",
    "que es el", "que es la", "que es un", "que es una",
    "para que sirve",
]

VALID_LANES = {
    "tool_list_files", "tool_read_file", "tool_save_fact",
    "tool_create_task", "tool_complete_task", "tool_update_work_state",
    "memory",
    "memory:profile", "memory:work_state", "memory:tasks",
    "memory:project_facts", "memory:episode",
    "rag", "identity",
    "unsupported",
}


# ─────────────────────────────────────────────
# Funciones internas
# ─────────────────────────────────────────────

def _has_task_suggestion_signal(q: str) -> bool:
    return any(signal in q for signal in _TASK_SUGGESTION_SIGNALS)


def classify_memory_query(question: str) -> str | None:
    """Clasifica el tipo de consulta de memoria."""
    q = _normalize(question)
    if any(k in q for k in MEMORY_PROFILE_KEYWORDS):       return "profile"
    if any(k in q for k in MEMORY_WORK_STATE_KEYWORDS):    return "work_state"
    if any(k in q for k in MEMORY_TASKS_KEYWORDS) \
            and not _has_task_suggestion_signal(q):         return "tasks"
    if any(k in q for k in MEMORY_PROJECT_FACTS_KEYWORDS): return "project_facts"
    if any(k in q for k in MEMORY_EPISODE_KEYWORDS):       return "episode"
    return None


def _is_question(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(("¿", "?")) or stripped.endswith("?")


def _handle_unsupported(question: str) -> str:
    return (
        "Todavía no tengo una herramienta para calcular métricas del código "
        "(líneas, funciones, tamaño de archivos) de forma precisa.\n\n"
        "Puedes obtener ese dato en tu terminal:\n"
        "  • PowerShell:  `Get-ChildItem app/ -Recurse -Filter *.py | "
        "ForEach-Object { (Get-Content $_).Count } | Measure-Object -Sum`\n"
        "  • Git Bash / WSL:  `find app/ -name '*.py' | xargs wc -l`\n\n"
        "Pronto tendré la herramienta `tool_code_stats` para responder esto directamente."
    )


def _route_by_keywords(question: str) -> str | None:
    """Capa 1: clasificación instantánea por keywords."""
    # Fix C1: import local para evitar ciclo router → tools → memory_manager → router
    from app.tools import extract_file_path

    q = _normalize(question)

    if q in {"!estado", "!estatus", "!status"}:
        return "!estado"

    if any(k in q for k in TOOL_SAVE_FACT_KEYWORDS):         return "tool_save_fact"
    if any(k in q for k in TOOL_CREATE_TASK_KEYWORDS):        return "tool_create_task"
    if any(k in q for k in TOOL_COMPLETE_TASK_KEYWORDS) \
            or _COMPLETE_TASK_PATTERN.search(q):              return "tool_complete_task"
    if any(k in q for k in TOOL_UPDATE_WORK_STATE_KEYWORDS):  return "tool_update_work_state"

    if any(k in q for k in TOOL_UNSUPPORTED_KEYWORDS):        return "unsupported"

    if extract_file_path(question) is not None and _has_read_verb(q):
        return "tool_read_file"
    if any(k in q for k in TOOL_LIST_KEYWORDS):               return "tool_list_files"
    if any(k in q for k in TOOL_READ_KEYWORDS):               return "tool_read_file"

    if any(k in q for k in AGENT_IDENTITY_KEYWORDS):          return "identity"

    memory_subtype = classify_memory_query(question)
    if memory_subtype is not None:
        return f"memory:{memory_subtype}"

    if any(k in q for k in RAG_HINTS):                        return "rag"

    return None


def _route_by_embeddings(question: str) -> str | None:
    """Capa 2: clasificación por similitud semántica via intent_index."""
    vectordb = intent_index.get_intent_db()
    if vectordb is None:
        return None
    try:
        results = vectordb.similarity_search_with_score(
            query=question, k=intent_index.EMBED_TOP_K
        )
        if not results:
            return None
        doc, distance = results[0]
        similarity = 1.0 - (distance / 2.0)
        lane = doc.metadata.get("lane", "")
        log.debug("[router:emb] similitud=%.2f lane_candidato=%s", similarity, lane)
        if _is_question(question) and lane in _WRITE_LANES:
            log.debug("[router:emb] pregunta detectada — bloqueando '%s' → fallback rag", lane)
            return None
        if similarity >= intent_index.EMBED_THRESHOLD and lane in VALID_LANES:
            return lane
        log.debug("[router:emb] similitud baja (%.2f < %.2f) → fallback rag", similarity, intent_index.EMBED_THRESHOLD)
        return None
    except Exception as e:
        log.warning("[router:emb] error: %s → fallback rag", e)
        return None


# ─────────────────────────────────────────────
# !estado — display del estado de sesión
# ─────────────────────────────────────────────

def format_estado() -> str:
    """Genera el bloque de texto para el comando !estado / !estatus."""
    from app.semantic_cache import cache_stats

    stats  = cache_stats()
    total  = SESSION_STATS["total"] or 1
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
        f"  → Fallback (rag): {SESSION_STATS['llm']}  ({llm_pct}%)\n"
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
    """Clasifica la pregunta en el carril de ejecución correcto."""
    if _normalize(question) in _EXIT_WORDS:
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
    log.info("[router:llm] '%s' → rag", question[:50])
    return "rag"
