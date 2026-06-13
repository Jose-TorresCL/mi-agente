"""Capa de inteligencia — orquestador de decisión.

Responsabilidad única: dado un carril ya clasificado, decidir qué hacer
y devolver DecisionResult.

NO conoce chat.py ni chat_ui.py.
NO persiste historial de conversación — eso es responsabilidad de chat_core.
SÍ usa la capa de memoria (memory_manager) y los módulos de inteligencia
(rag_engine, fidelity_check, tool_registry, semantic_cache).

Contrato público
────────────────
    process_turn(ctx: TurnContext) -> DecisionResult
    process_turn(route, user_input, vectordb, chat_history) -> DecisionResult  # legacy

    Ambas formas son equivalentes. chat_core usa TurnContext (forma nueva).
    Los tests que llaman a process_turn directamente con 4 args siguen funcionando.

R1  — contratos internos (CERRADO)
R2-connect — intent_type y num_docs en record_turn() (CERRADO)
R4-B — composición multi-capa de memoria (CERRADO)
Fix B3 — timeout síntesis subido de 10s a 30s (CERRADO)
Fix B4 — _format_tasks_answer distingue tareas hechas vs pendientes (CERRADO)
Fix C1 — chat_history en _synthesize_memory_answer (CERRADO)
Fix C2 — cliente LLM unificado con generate_raw() (CERRADO)
D2  — prompt de síntesis movido a prompts.py (CERRADO)
D3  — umbral episódico propio en intelligence.py (CERRADO)
D4-B — prompt de resumen episódico reducido (CERRADO)
D5  — detect_memory_intents se llama UNA sola vez en process_turn (CERRADO).
R5-MoA — separación recuperador/sintetizador en _decide_memory (CERRADO).
R6-RAG — separación de responsabilidades en _decide_rag (CERRADO).
TurnContext — process_turn acepta TurnContext o 4 args sueltos (CERRADO).
feat: carril 'identity' — respuesta hardcodeada para preguntas de identidad.
E3  — process_turn devuelve DecisionResult en vez de tuple (CERRADO).
Fix P5-Paso4 — el bloque memory lee el subtipo desde el carril (CERRADO).
R-F1 — refactor de funciones puras y constantes (CERRADO).
H-B1 — hardening Opción B: tabla _DIRECT_ROUTES + _make_direct_result (CERRADO).
Fix memory_context — build_chain ya no inyecta memory_context (CERRADO).
Fix 3 — síntesis LLM forzada cuando la pregunta pide razonamiento (CERRADO):
  _decide_memory() detecta señales de razonamiento en la pregunta
  (recomendar, mejor, prioridad, atacar, empezar, debería, conviene,
  importante, comparar, contradicción) y fuerza síntesis LLM incluso
  cuando needs_llm=False (ej. lista plana de tareas). Si el LLM falla,
  devuelve el fallback original sin romper nada.
"""
from __future__ import annotations

import time
from typing import Any, Callable, TypedDict

from langchain_core.messages import HumanMessage

from app.config import MAX_TURNS, MODEL_NAME, OLLAMA_URL
from app.logger import get_logger
from app.memory_manager import (
    get_selective_context,
    get_context_for,
    get_profile,
    get_project_facts,
    get_tasks,
    get_work_state,
    record_episode,
    detect_memory_intents,
    get_composed_context,
)
from app.metrics import record_turn as _record_metric
from app.rag_engine import retrieve_context, build_chain, generate_raw
from app.semantic_cache import cache_lookup, cache_save
from app.fidelity_check import verify_fidelity, NO_EVIDENCE_MSG
from app.router import classify_memory_query
from app.tool_registry import TOOLS, dispatch_tool_str
from app.prompts import (
    QA_SYSTEM_PROMPT,
    MEMORY_SYNTHESIS_PROMPT,
    IDENTITY_MSG,
    UNSUPPORTED_MSG,
    MEMORY_NOT_FOUND_MSG,
)
from app.tool_helpers import list_project_files, handle_list_files
from app.formatters import (
    format_profile_answer,
    format_tasks_answer,
    build_history_snippet,
    format_episodes_context,
)
from app.schemas import TurnContext, DecisionResult

log = get_logger(__name__)

_EPISODE_TIMEOUT           = 40
_MEMORY_SYNTHESIS_TIMEOUT  = 30
_HISTORY_LINE_MAX          = 80
_CACHE_MIN_SCORE           = 0.55
_COUNT_KEYWORDS            = {"cuántos", "cuantos", "cuántas", "cuantas", "cuanto", "cuánto"}
_IDENTITY_KEYWORDS         = {"quién eres", "quien eres", "cómo te llamas", "como te llamas",
                               "cuál es tu nombre", "cual es tu nombre", "quién soy", "quien soy"}
_MEMORY_HISTORY_TURNS      = 3

# D3: umbral propio de intelligence.py para inyección episódica.
_MIN_EXPERIENCE_SCORE      = 0.70

# Fix 3: señales de razonamiento — cuando la pregunta las contiene,
# _decide_memory fuerza síntesis LLM aunque needs_llm=False.
# Esto evita que Lautaro devuelva listas planas cuando el usuario
# pide recomendación, priorización o análisis cruzado.
_REASONING_SIGNALS = {
    "recomendar", "recomendas", "recomiendas", "recomendarías",
    "mejor", "primero", "atacar", "prioridad", "priorizar",
    "empezar", "empezaría", "debería", "deberíamos", "deberia", "deberiamos",
    "conviene", "convendría",
    "importante", "más importante",
    "comparar", "contradicción", "contradiccion",
    "por que", "por qué",
    "cuál me", "cual me",
    "qué haría", "que haria",
    "qué conviene", "que conviene",
}


# ──────────────────────────────────────────────
# TypedDicts — contratos entre sub-funciones
# ──────────────────────────────────────────────

class MemoryContext(TypedDict):
    context_text: str
    fallback: str
    sources: list[str]
    needs_llm: bool


class RagContext(TypedDict):
    """Contrato de salida del AGENTE RECUPERADOR RAG (R6-RAG)."""
    context_text: str
    source_docs: list
    memory_context: str
    experience_injected: bool
    retrieval_ms: int


# ──────────────────────────────────────────────
# H-B1: helper + tabla de carriles directos
# ──────────────────────────────────────────────

def _make_direct_result(route: str, response_fn: Callable[[], str]) -> DecisionResult:
    return DecisionResult(
        route=route,
        response=response_fn(),
        cached=False,
        source="direct",
        source_docs=[],
        retrieval_ms=0,
        llm_ms=0,
        tokens_est=0,
    )


def _get_direct_routes() -> dict[str, Callable[[], str]]:
    from app.router import format_estado
    return {
        "identity":    lambda: IDENTITY_MSG,
        "unsupported": lambda: UNSUPPORTED_MSG,
        "!estado":     format_estado,
    }


# ──────────────────────────────────────────────
# R5-MoA — AGENTE RECUPERADOR de memoria
# ──────────────────────────────────────────────

def _retrieve_memory_context(question: str, intents: list[str]) -> MemoryContext:
    if len(intents) > 1:
        composed = get_composed_context(intents)
        if not composed.strip():
            return MemoryContext(context_text="", fallback=MEMORY_NOT_FOUND_MSG,
                                 sources=intents, needs_llm=False)
        return MemoryContext(context_text=composed,
                             fallback=f"Información de memoria:\n{composed}",
                             sources=intents, needs_llm=True)

    kind = intents[0]

    if kind == "profile":
        p = get_profile()
        if not p:
            return MemoryContext(context_text="", fallback="No encontré información de perfil.",
                                 sources=["profile"], needs_llm=False)
        return MemoryContext(context_text="", fallback=format_profile_answer(p),
                             sources=["profile"], needs_llm=False)

    if kind == "tasks":
        t = get_tasks()
        if not t:
            return MemoryContext(context_text="", fallback="No encontré tareas registradas.",
                                 sources=["tasks"], needs_llm=False)
        return MemoryContext(
            context_text=format_tasks_answer(t, question=question),
            fallback=format_tasks_answer(t, question=question),
            sources=["tasks"],
            needs_llm=False,
        )

    if kind == "project_facts":
        f = get_project_facts()
        if not f:
            return MemoryContext(context_text="", fallback="No encontré hechos del proyecto.",
                                 sources=["project_facts"], needs_llm=False)
        context_text = "\n".join(f"- {k}: {v}" for k, v in f.items())
        return MemoryContext(context_text=context_text,
                             fallback="**Hechos del proyecto:**\n" + context_text,
                             sources=["project_facts"], needs_llm=True)

    if kind == "work_state":
        w = get_work_state()
        if not w:
            return MemoryContext(context_text="", fallback="No encontré estado de trabajo.",
                                 sources=["work_state"], needs_llm=False)
        _ws_fields = [
            ("current_focus",  "Foco actual"),
            ("last_completed", "Último paso completado"),
            ("next_step",      "Siguiente paso"),
        ]
        context_lines = [f"- {label}: {w.get(k, 'sin definir')}" for k, label in _ws_fields]
        blockers = w.get("current_blockers", [])
        if isinstance(blockers, list) and blockers:
            context_lines.append(f"- Bloqueos: {', '.join(blockers)}")
        elif isinstance(blockers, str) and blockers.strip():
            context_lines.append(f"- Bloqueos: {blockers.strip()}")
        context_text = "\n".join(context_lines)
        return MemoryContext(context_text=context_text,
                             fallback="**Estado de trabajo:**\n" + context_text,
                             sources=["work_state"], needs_llm=True)

    if kind == "episode":
        episodes: list[dict] = []
        try:
            from app.episode_store import search_episodes
            episodes = search_episodes(question, k=3)
        except Exception as exc:
            log.warning("[episode] search_episodes falló: %s", exc)

        _EMPTY_MARKER = "Resumen no disponible"
        episodes_with_content = [ep for ep in episodes
                                  if _EMPTY_MARKER not in ep.get("summary", "")]
        if episodes_with_content:
            context_text = format_episodes_context(episodes_with_content)
            return MemoryContext(context_text=context_text,
                                 fallback=f"Sesiones encontradas:\n{context_text}",
                                 sources=["episode"], needs_llm=True)

        json_context = get_context_for("episode")
        if json_context:
            return MemoryContext(context_text="", fallback=json_context,
                                 sources=["episode"], needs_llm=False)
        return MemoryContext(
            context_text="",
            fallback="No encontré sesiones anteriores registradas con información relevante.",
            sources=["episode"], needs_llm=False)

    log.debug("_retrieve_memory_context: tipo no reconocido '%s'", kind)
    return MemoryContext(context_text="", fallback=MEMORY_NOT_FOUND_MSG,
                         sources=[kind], needs_llm=False)


# ──────────────────────────────────────────────
# R5-MoA — AGENTE SINTETIZADOR de memoria
# ──────────────────────────────────────────────

def _synthesize_memory_answer(
    question: str,
    context_text: str,
    fallback: str,
    chat_history: list | None = None,
) -> str:
    history_snippet = build_history_snippet(chat_history) or "(sin historial previo)"
    prompt = MEMORY_SYNTHESIS_PROMPT.format(
        context_text=context_text,
        chat_history=history_snippet,
        question=question,
    )
    answer = generate_raw(prompt, temperature=0.3, num_predict=150,
                          timeout=_MEMORY_SYNTHESIS_TIMEOUT)
    if answer:
        return answer
    log.warning("_synthesize_memory_answer: generate_raw devolvió None, usando fallback")
    return fallback


# ──────────────────────────────────────────────
# R5-MoA — ORQUESTADOR de memoria
# ──────────────────────────────────────────────

def _has_reasoning_signal(question: str) -> bool:
    """Retorna True si la pregunta contiene señales de razonamiento/recomendación.

    Fix 3: cuando el usuario pide priorizar, recomendar o analizar,
    Lautaro debe sintetizar con LLM en vez de devolver datos crudos.
    La normalización convierte tildes y mayúsculas para comparación limpia.
    """
    q_lower = question.lower()
    return any(signal in q_lower for signal in _REASONING_SIGNALS)


def _decide_memory(
    question: str,
    intents: list[str],
    chat_history: list | None = None,
) -> str:
    """D5: recibe intents ya detectados desde process_turn — no los re-detecta.

    Fix 3: si needs_llm=False pero la pregunta tiene señales de razonamiento
    (recomendar, priorizar, mejor, debería, etc.), fuerza síntesis LLM.
    El context_text se usa cuando está disponible; si está vacío pero el
    fallback tiene datos útiles, se usa el fallback como contexto.
    Si el LLM falla, se devuelve el fallback original sin romper nada.
    """
    log.debug("R5-MoA: intents recibidos=%s para '%s'", intents, question[:60])

    if not intents:
        return MEMORY_NOT_FOUND_MSG

    mem_ctx: MemoryContext = _retrieve_memory_context(question, intents)
    log.debug("R5-MoA: recuperador [sources=%s needs_llm=%s ctx_len=%d]",
              mem_ctx["sources"], mem_ctx["needs_llm"], len(mem_ctx["context_text"]))

    # Ruta directa: si ya necesita LLM, sintetizar siempre
    if mem_ctx["needs_llm"]:
        return _synthesize_memory_answer(
            question, mem_ctx["context_text"], mem_ctx["fallback"],
            chat_history=chat_history,
        )

    # Fix 3: aunque needs_llm=False, forzar síntesis si la pregunta
    # pide razonamiento (priorizar, recomendar, analizar, etc.).
    # El contexto para el LLM es el fallback (ya tiene los datos formateados).
    if _has_reasoning_signal(question):
        context_for_llm = mem_ctx["context_text"] or mem_ctx["fallback"]
        if context_for_llm.strip():
            log.debug("[Fix3] señal de razonamiento detectada — forzando síntesis LLM")
            return _synthesize_memory_answer(
                question, context_for_llm, mem_ctx["fallback"],
                chat_history=chat_history,
            )

    return mem_ctx["fallback"]


# ──────────────────────────────────────────────
# R6-RAG — CACHÉ
# ──────────────────────────────────────────────

def _lookup_rag_cache(user_input: str, is_identity: bool) -> str | None:
    if is_identity:
        return None
    return cache_lookup(user_input)


# ──────────────────────────────────────────────
# R6-RAG — AGENTE RECUPERADOR RAG
# ──────────────────────────────────────────────

def _retrieve_rag_context(user_input: str, vectordb: Any, route: str) -> RagContext:
    t_start = time.perf_counter()

    memory_context = get_selective_context(route)
    context_text, source_docs = retrieve_context(user_input, vectordb)

    experience_injected = False
    try:
        from app.episode_store import experience_lookup_with_score
        snippet, exp_score = experience_lookup_with_score(user_input)

        if snippet and exp_score >= _MIN_EXPERIENCE_SCORE:
            context_text = snippet + "\n\n---\n\n" + context_text
            experience_injected = True
            log.debug(
                "[R6-RAG] Experiencia episódica inyectada (score=%.3f >= %.2f)",
                exp_score, _MIN_EXPERIENCE_SCORE,
            )
        elif snippet:
            log.debug(
                "[R6-RAG] Experiencia episódica descartada (score=%.3f < %.2f)",
                exp_score, _MIN_EXPERIENCE_SCORE,
            )
    except Exception as exc:
        log.warning("[R6-RAG] experience_lookup_with_score falló (no bloquea): %s", exc)

    retrieval_ms = int((time.perf_counter() - t_start) * 1000)

    return RagContext(
        context_text=context_text,
        source_docs=source_docs,
        memory_context=memory_context,
        experience_injected=experience_injected,
        retrieval_ms=retrieval_ms,
    )


# ──────────────────────────────────────────────
# R6-RAG — AGENTE GENERADOR RAG
# ──────────────────────────────────────────────

def _generate_rag_answer(
    user_input: str,
    rag_ctx: RagContext,
    chat_history: list,
) -> tuple[str, list, int, bool, float]:
    chat_history_text = "\n".join(
        f"{'Usuario' if isinstance(m, HumanMessage) else 'Lautaro'}: {m.content}"
        for m in chat_history
    ) or "(sin historial previo)"

    t_llm_start = time.perf_counter()
    chain = build_chain(QA_SYSTEM_PROMPT)
    answer = chain.invoke({
        "question":       user_input,
        "context":        rag_ctx["context_text"],
        "chat_history":   chat_history_text,
        "memory_context": rag_ctx["memory_context"],
    })
    llm_ms = int((time.perf_counter() - t_llm_start) * 1000)

    is_faithful, score = verify_fidelity(answer, rag_ctx["source_docs"], question=user_input)
    if not is_faithful:
        log.warning("[R6-RAG] Respuesta bloqueada por fidelidad (score=%.3f): %s",
                    score, user_input[:60])
        return NO_EVIDENCE_MSG, rag_ctx["source_docs"], llm_ms, False, score

    return answer, rag_ctx["source_docs"], llm_ms, True, score


# ──────────────────────────────────────────────
# R6-RAG — ORQUESTADOR RAG
# ──────────────────────────────────────────────

def _decide_rag(
    user_input: str,
    vectordb: Any,
    chat_history: list,
    route: str,
) -> tuple[str, list, int, int, bool]:
    is_identity = any(kw in user_input.lower() for kw in _IDENTITY_KEYWORDS)

    hit = _lookup_rag_cache(user_input, is_identity)
    if hit is not None:
        return hit, [], 0, 0, True

    rag_ctx = _retrieve_rag_context(user_input, vectordb, route)

    answer, source_docs, llm_ms, is_faithful, score = _generate_rag_answer(
        user_input, rag_ctx, chat_history
    )

    can_cache = (
        not is_identity
        and not rag_ctx["experience_injected"]
        and is_faithful
        and score >= _CACHE_MIN_SCORE
    )
    if can_cache:
        cache_save(user_input, answer)
    else:
        reasons = []
        if is_identity:                       reasons.append("identidad")
        if rag_ctx["experience_injected"]:    reasons.append("inyección episódica")
        if not is_faithful:                   reasons.append("baja fidelidad")
        elif score < _CACHE_MIN_SCORE:        reasons.append(f"score={score:.3f}")
        if reasons:
            log.debug("[R6-RAG] No cacheado (%s)", ", ".join(reasons))

    return answer, source_docs, rag_ctx["retrieval_ms"], llm_ms, False


# ──────────────────────────────────────────────
# Decisores — otros carriles (exit)
# ──────────────────────────────────────────────

def _compress_history(chat_history: list, max_line: int = _HISTORY_LINE_MAX) -> str:
    lines: list[str] = []
    for m in chat_history[-(MAX_TURNS * 2):]:
        role = "Usuario" if isinstance(m, HumanMessage) else "Lautaro"
        content = m.content.strip().replace("\n", " ")
        truncated = content[:max_line] + ("…" if len(content) > max_line else "")
        lines.append(f"{role}: {truncated}")
    return "\n".join(lines)


def _decide_exit(chat_history: list) -> DecisionResult:
    turns = len(chat_history) // 2
    summary = "Resumen no disponible (sesión cerrada sin tiempo para generar)."

    if turns > 0:
        log.info("Guardando resumen episódico (%d turnos)", turns)
        history_text = _compress_history(chat_history)
        prompt = (
            "Resume esta conversación en exactamente 2 líneas en español.\n"
            "Línea 1: tema principal y decisión tomada.\n"
            "Línea 2: siguiente paso pendiente.\n"
            "Sin bullet points ni numeración. Solo 2 líneas.\n\n"
            f"Conversación:\n{history_text}\n\nResumen:"
        )
        generated = generate_raw(prompt, temperature=0.1, num_predict=45,
                                 timeout=_EPISODE_TIMEOUT)
        if generated:
            summary = generated
        else:
            log.warning("No se pudo generar resumen de sesión")

    record_episode(summary=summary, turns=turns)
    log.info("Episodio guardado correctamente (turns=%d)", turns)
    return DecisionResult(
        route="exit",
        response="__EXIT__",
        cached=False,
        source="direct",
        source_docs=[],
        retrieval_ms=0,
        llm_ms=0,
        tokens_est=0,
    )


# ──────────────────────────────────────────────
# Contrato público de la capa de inteligencia
# ──────────────────────────────────────────────

def process_turn(
    route_or_ctx: str | TurnContext,
    user_input: str | None = None,
    vectordb: Any = None,
    chat_history: list | None = None,
) -> DecisionResult:
    """Punto de entrada único de la capa de inteligencia."""
    if isinstance(route_or_ctx, dict):
        ctx: TurnContext = route_or_ctx
        route        = ctx["route"]
        user_input   = ctx["query"]
        vectordb     = ctx["vectordb"]
        chat_history = ctx["chat_history"]
        channel      = ctx.get("channel", "cli")
    else:
        route = route_or_ctx
        channel = "cli"

    if chat_history is None:
        chat_history = []

    # ── exit ──────────────────────────────────────────────────────────────
    if route == "exit":
        result = _decide_exit(chat_history)
        _record_metric(route="exit", intent_type="exit", channel=channel)
        return result

    # ── H-B1: carriles directos (identity, unsupported, !estado) ──────────
    direct_routes = _get_direct_routes()
    if route in direct_routes:
        _record_metric(route=route, intent_type=route, channel=channel)
        return _make_direct_result(route, direct_routes[route])

    # ── tool_list_files ───────────────────────────────────────────────────
    if route == "tool_list_files":
        answer = handle_list_files(user_input)
        _record_metric(route=route, intent_type="tool_list_files", channel=channel)
        return DecisionResult(
            route=route,
            response=answer,
            cached=False,
            source="tool",
            source_docs=[],
            retrieval_ms=0,
            llm_ms=0,
            tokens_est=0,
        )

    # ── tools registradas ─────────────────────────────────────────────────
    if route in TOOLS:
        t0 = time.perf_counter()
        answer = dispatch_tool_str(route, user_input)
        llm_ms = int((time.perf_counter() - t0) * 1000)
        _record_metric(route=route, intent_type=route, llm_ms=llm_ms, channel=channel)
        return DecisionResult(
            route=route,
            response=answer,
            cached=False,
            source="tool",
            source_docs=[],
            retrieval_ms=0,
            llm_ms=llm_ms,
            tokens_est=0,
        )

    # ── memory ───────────────────────────────────────────────────────────
    if route == "memory" or route.startswith("memory:"):
        t0 = time.perf_counter()

        if ":" in route:
            subtype = route.split(":", 1)[1]
            intents = [subtype]
            log.debug("[memory] subtipo desde carril: %s", subtype)
        else:
            intents = detect_memory_intents(user_input)
            log.debug("[memory] intents detectados: %s", intents)

        answer = _decide_memory(user_input, intents, chat_history=chat_history)
        llm_ms = int((time.perf_counter() - t0) * 1000)
        _record_metric(route="memory", intent_type="memory", llm_ms=llm_ms, channel=channel)
        return DecisionResult(
            route="memory",
            response=answer,
            cached=False,
            source="memory",
            source_docs=[],
            retrieval_ms=0,
            llm_ms=llm_ms,
            tokens_est=0,
        )

    # ── rag ───────────────────────────────────────────────────────────────
    answer, source_docs, retrieval_ms, llm_ms, cached = _decide_rag(
        user_input, vectordb, chat_history, route
    )
    _record_metric(
        route="rag",
        intent_type="rag",
        num_docs=len(source_docs),
        retrieval_ms=retrieval_ms,
        llm_ms=llm_ms,
        channel=channel,
    )
    return DecisionResult(
        route="rag",
        response=answer,
        cached=cached,
        source="rag",
        source_docs=source_docs,
        retrieval_ms=retrieval_ms,
        llm_ms=llm_ms,
        tokens_est=0,
    )
