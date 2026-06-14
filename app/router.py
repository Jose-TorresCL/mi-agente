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
"""
from __future__ import annotations

from typing import Any

from app.text_utils import _normalize
from app.logger import get_logger
from app import intent_index
from app.router_config import (
    _EXIT_WORDS,
    _WRITE_LANES,
    _READ_VERBS,
    TOOL_LIST_KEYWORDS,
    TOOL_READ_KEYWORDS,
    MEMORY_PROFILE_KEYWORDS,
    MEMORY_WORK_STATE_KEYWORDS,
    MEMORY_TASKS_KEYWORDS,
    _TASK_SUGGESTION_SIGNALS,
    MEMORY_PROJECT_FACTS_KEYWORDS,
    MEMORY_EPISODE_KEYWORDS,
    AGENT_IDENTITY_KEYWORDS,
    TOOL_SAVE_FACT_KEYWORDS,
    TOOL_SAVE_NOTE_KEYWORDS,
    TOOL_CREATE_TASK_KEYWORDS,
    TOOL_COMPLETE_TASK_KEYWORDS,
    _COMPLETE_TASK_PATTERN,
    TOOL_UPDATE_WORK_STATE_KEYWORDS,
    TOOL_SET_SESSION_GOAL_KEYWORDS,
    TOOL_UNSUPPORTED_KEYWORDS,
    MATH_KEYWORDS,
    _RE_MATH_EXPR,
    RAG_HINTS,
    MEMORY_REASONING_KEYWORDS,
    VALID_LANES,
    RouterDebugInfo,
)

log = get_logger(__name__)


SESSION_STATS: dict[str, int] = {
    "kw":    0,
    "emb":   0,
    "llm":   0,
    "total": 0,
}

EMBED_THRESHOLD = intent_index.EMBED_THRESHOLD
EMBED_TOP_K     = intent_index.EMBED_TOP_K


def _has_read_verb(q_normalized: str) -> bool:
    return any(verb in q_normalized for verb in _READ_VERBS)


def _has_task_suggestion_signal(q: str) -> bool:
    return any(signal in q for signal in _TASK_SUGGESTION_SIGNALS)


def classify_memory_query(question: str) -> str | None:
    q = _normalize(question)
    if any(k in q for k in MEMORY_PROFILE_KEYWORDS):       return "profile"
    if any(k in q for k in MEMORY_WORK_STATE_KEYWORDS):    return "work_state"
    if any(k in q for k in MEMORY_TASKS_KEYWORDS) and not _has_task_suggestion_signal(q):
        return "tasks"
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
    from app.tools import extract_file_path

    q = _normalize(question)

    if q in {"!estado", "!estatus", "!status"}:
        return "!estado"

    if any(k in q for k in TOOL_SAVE_FACT_KEYWORDS):                return "tool_save_fact"
    if any(k in q for k in TOOL_CREATE_TASK_KEYWORDS):              return "tool_create_task"
    if any(k in q for k in TOOL_COMPLETE_TASK_KEYWORDS) or _COMPLETE_TASK_PATTERN.search(q):
        return "tool_complete_task"
    if any(k in q for k in TOOL_SET_SESSION_GOAL_KEYWORDS):         return "tool_set_session_goal"
    if any(k in q for k in TOOL_UPDATE_WORK_STATE_KEYWORDS):        return "tool_update_work_state"
    if any(k in q for k in TOOL_UNSUPPORTED_KEYWORDS):              return "unsupported"

    if extract_file_path(question) is not None and _has_read_verb(q):
        return "tool_read_file"
    if any(k in q for k in TOOL_LIST_KEYWORDS):                     return "tool_list_files"
    if any(k in q for k in TOOL_READ_KEYWORDS):                     return "tool_read_file"

    if any(k in q for k in AGENT_IDENTITY_KEYWORDS):                return "identity"

    # [A] Fix A: razonamiento personal antes de classify_memory_query.
    if any(k in q for k in MEMORY_REASONING_KEYWORDS):              return "memory:work_state"

    memory_subtype = classify_memory_query(question)
    if memory_subtype is not None:
        return f"memory:{memory_subtype}"

    # Fix: notas libres → tool_save_fact (antes caían a RAG)
    # Se evalúa ANTES de math para no capturar frases con números dentro de una nota.
    if any(k in q for k in TOOL_SAVE_NOTE_KEYWORDS):                return "tool_save_fact"

    # Fix: preguntas matemáticas → math (antes caían a RAG y fidelity las bloqueaba)
    # Se evalúa por keyword y por expresión directa (ej. '847 / 13').
    if any(k in q for k in MATH_KEYWORDS) or _RE_MATH_EXPR.match(q): return "math"

    if any(k in q for k in RAG_HINTS):                              return "rag"

    return None


def _route_by_embeddings(question: str) -> str | None:
    vectordb = intent_index.get_intent_db()
    if vectordb is None:
        return None
    try:
        results = vectordb.similarity_search_with_score(query=question, k=EMBED_TOP_K)
        if not results:
            return None
        doc, distance = results[0]
        similarity = 1.0 - (distance / 2.0)
        lane = doc.metadata.get("lane", "")
        log.debug("[router:emb] similitud=%.2f lane_candidato=%s", similarity, lane)
        if _is_question(question) and lane in _WRITE_LANES:
            log.debug("[router:emb] pregunta detectada — bloqueando '%s' → fallback rag", lane)
            return None
        if similarity >= EMBED_THRESHOLD and lane in VALID_LANES:
            return lane
        log.debug("[router:emb] similitud baja (%.2f < %.2f) → fallback rag", similarity, EMBED_THRESHOLD)
        return None
    except Exception as e:
        log.warning("[router:emb] error: %s → fallback rag", e)
        return None


def format_estado() -> str:
    from app.semantic_cache import cache_stats

    stats  = cache_stats()
    total  = SESSION_STATS["total"] or 1
    kw_pct  = SESSION_STATS["kw"]  * 100 // total
    emb_pct = SESSION_STATS["emb"] * 100 // total
    llm_pct = SESSION_STATS["llm"] * 100 // total

    ttl_line = ""
    if "ttl_hours" in stats:
        ttl_line = f"  TTL caché:       {stats['ttl_hours']}h\n"

    separator = "─" * 40
    return (
        f"\n{separator}\n"
        f" Estado de sesión\n"
        f"{separator}\n"
        f"  Consultas totales: {SESSION_STATS['total']}\n"
        f"  → Capa 1 (kw):    {SESSION_STATS['kw']}  ({kw_pct}%)\n"
        f"  → Capa 2 (emb):   {SESSION_STATS['emb']}  ({emb_pct}%)\n"
        f"  → Fallback (rag): {SESSION_STATS['llm']}  ({llm_pct}%)\n"
        f"{separator}\n"
        f" Caché semántica\n"
        f"{separator}\n"
        f"  Hits:             {stats.get('hits', 0)}\n"
        f"  Misses:           {stats.get('misses', 0)}\n"
        f"  Entradas:         {stats.get('entries', 0)}\n"
        f"{ttl_line}"
        f"{separator}\n"
    )


def route_query(question: str) -> str:
    _q_norm = _normalize(question)
    if _q_norm in _EXIT_WORDS or _q_norm.startswith(("_exit", "__exit")):
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


def debug_route_layers(question: str) -> RouterDebugInfo:
    """Devuelve qué capa decidió y qué lane, sin efectos secundarios en SESSION_STATS."""
    _q_norm = _normalize(question)
    if _q_norm in _EXIT_WORDS or _q_norm.startswith(("_exit", "__exit")):
        return {"layer": "exit", "lane": "exit"}

    lane_kw = _route_by_keywords(question)
    if lane_kw is not None:
        return {"layer": "kw", "lane": lane_kw}

    lane_emb = _route_by_embeddings(question)
    if lane_emb is not None:
        return {"layer": "emb", "lane": lane_emb}

    return {"layer": "fallback", "lane": "rag"}
