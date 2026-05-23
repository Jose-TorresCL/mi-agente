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
D3  — umbral episódico propio en intelligence.py (CERRADO):
  _MIN_EXPERIENCE_SCORE = 0.70 en _retrieve_rag_context().
  Se usa experience_lookup_with_score() que expone el score explícitamente.
  intelligence.py decide si inyectar — no depende del umbral de episode_store.
D4-B — prompt de resumen episódico reducido (CERRADO):
  3 líneas → 2 líneas. num_predict 80 → 45. temperature 0.2 → 0.1.
  Razón: el resumen solo necesita ser buscable semánticamente, no literario.
  Reducción estimada de latencia al salir: ~40% en CPU sin GPU.
D5  — detect_memory_intents se llama UNA sola vez en process_turn (CERRADO).
R5-MoA — separación recuperador/sintetizador en _decide_memory (CERRADO).
R6-RAG — separación de responsabilidades en _decide_rag (CERRADO).
TurnContext — process_turn acepta TurnContext o 4 args sueltos (CERRADO).
feat: carril 'identity' — respuesta hardcodeada para preguntas de identidad
  del agente. 0ms, sin LLM ni RAG. router.py envía 'identity' en vez de 'rag'.
E3  — process_turn devuelve DecisionResult en vez de tuple (CERRADO).
Fix P5-Paso4 — el bloque memory lee el subtipo desde el carril en vez de
  re-detectarlo con detect_memory_intents (CERRADO):
  - Si route = 'memory:tasks' → intents = ['tasks']  (Capa 1, 0 trabajo extra)
  - Si route = 'memory'       → fallback a detect_memory_intents (Capa 2)
  - route se normaliza a 'memory' antes de _record_metric para no romper métricas.
  - La condición pasa de `route == "memory"` a
    `route == "memory" or route.startswith("memory:")`.
"""
from __future__ import annotations

import time
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, AIMessage

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
from app.tool_registry import TOOLS, dispatch_tool
from app.prompts import QA_SYSTEM_PROMPT, MEMORY_SYNTHESIS_PROMPT
from app.tool_helpers import list_project_files
from app.schemas import TurnContext, DecisionResult

log = get_logger(__name__)

_EPISODE_TIMEOUT           = 20
_MEMORY_SYNTHESIS_TIMEOUT  = 30
_HISTORY_LINE_MAX          = 80
_CACHE_MIN_SCORE           = 0.55
_COUNT_KEYWORDS            = {"cuántos", "cuantos", "cuántas", "cuantas", "cuanto", "cuánto"}
_IDENTITY_KEYWORDS         = {"quién eres", "quien eres", "cómo te llamas", "como te llamas",
                               "cuál es tu nombre", "cual es tu nombre", "quién soy", "quien soy"}
_DONE_TASK_KEYWORDS        = {
    "hechas", "hecho", "completadas", "completada", "completado",
    "cerradas", "cerrada", "terminadas", "terminada", "listas", "lista",
    "done",
}
_MEMORY_HISTORY_TURNS      = 3

# D3: umbral propio de intelligence.py para inyección episódica.
# Independiente de EXPERIENCE_INJECT_THRESHOLD en episode_store.py.
_MIN_EXPERIENCE_SCORE      = 0.70

_UNSUPPORTED_MSG = (
    "Esa consulta está fuera del alcance de lo que puedo hacer por ahora. "
    "Puedo responder preguntas sobre el proyecto, buscar en la documentación, "
    "consultar tareas y estado de trabajo."
)
_MEMORY_NOT_FOUND_MSG = (
    "No encontré información relevante en la memoria para esa pregunta. "
    "Si buscas datos del proyecto, prueba con: '\u00bfcuál es el estado del proyecto?', "
    "'\u00bfqué tareas tengo pendientes?' o '\u00bfcuál es mi perfil?'."
)

# Respuesta fija de identidad — carril 'identity'.
# No depende del LLM ni del RAG. Se actualiza aquí directamente.
_IDENTITY_MSG = (
    "Soy **Lautaro**, tu asistente técnico local.\n\n"
    "**Lo que puedo hacer:**\n"
    "- Buscar en la documentación del proyecto (RAG)\n"
    "- Recordar tu perfil, foco de trabajo y tareas pendientes\n"
    "- Guardar hechos del proyecto y actualizar el estado de trabajo\n"
    "- Registrar y recuperar el historial de sesiones anteriores\n"
    "- Leer archivos del proyecto\n\n"
    "**Lo que aún no puedo hacer:**\n"
    "- Acceder a internet ni ejecutar código directamente\n"
    "- Calcular métricas de código (líneas, funciones) — pronto con `tool_code_stats`\n\n"
    "Corro completamente en local usando Ollama. Sin enviar datos a la nube."
)


# ───────────────────────────────────────────────
# TypedDicts — contratos entre sub-funciones
# ───────────────────────────────────────────────

class MemoryContext(TypedDict):
    context_text: str
    fallback: str
    sources: list[str]
    needs_llm: bool


class RagContext(TypedDict):
    """Contrato de salida del AGENTE RECUPERADOR RAG (R6-RAG).

    experience_injected: True si se prepend la experiencia episódica
                         Y su score superó _MIN_EXPERIENCE_SCORE (D3).
    """
    context_text: str
    source_docs: list
    memory_context: str
    experience_injected: bool
    retrieval_ms: int


# ───────────────────────────────────────────────
# Helpers de formato — carril memory
# ───────────────────────────────────────────────

def _format_profile_answer(profile: dict) -> str:
    lines = ["**Perfil del usuario:**"]
    lines.append(f"- Nombre: {profile.get('user_name', 'desconocido')}")
    lines.append(f"- Nivel: {profile.get('user_level', 'desconocido')}")
    lines.append(f"- Proyecto: {profile.get('project_type', 'desconocido')}")
    style = profile.get("preferred_style", [])
    if style:
        lines.append(f"- Estilo preferido: {', '.join(style)}")
    workflow = profile.get("preferred_workflow", [])
    if workflow:
        lines.append(f"- Flujo preferido: {' | '.join(workflow)}")
    return "\n".join(lines)


def _format_tasks_answer(tasks_data: dict, question: str = "") -> str:
    tasks = tasks_data.get("tasks", [])
    q_lower = question.lower()
    wants_done = any(kw in q_lower for kw in _DONE_TASK_KEYWORDS)

    if wants_done:
        filtered = [t for t in tasks if t.get("status") in ("done", "completed")]
        if not filtered:
            return "No hay tareas completadas registradas."
        lines = ["**Tareas completadas:**"]
        for t in filtered:
            lines.append(
                f"- [{t.get('id', '?')}] {t.get('title', '')} "
                f"(prioridad: {t.get('priority', 'media')})"
            )
        return "\n".join(lines)

    pending = [t for t in tasks if t.get("status") not in ("done", "completed")]
    if not pending:
        return "No hay tareas pendientes registradas."
    lines = ["**Tareas pendientes:**"]
    for t in pending:
        lines.append(
            f"- [{t.get('id', '?')}] {t.get('title', '')} "
            f"(prioridad: {t.get('priority', 'media')}, estado: {t.get('status', 'pending')})"
        )
    return "\n".join(lines)


def _build_history_snippet(chat_history: list | None, max_turns: int = _MEMORY_HISTORY_TURNS) -> str:
    if not chat_history:
        return ""
    recent = chat_history[-(max_turns * 2):]
    lines = []
    for m in recent:
        role = "Usuario" if isinstance(m, HumanMessage) else "Lautaro"
        content = m.content.strip().replace("\n", " ")
        truncated = content[:_HISTORY_LINE_MAX] + ("…" if len(content) > _HISTORY_LINE_MAX else "")
        lines.append(f"{role}: {truncated}")
    return "\n".join(lines)


def _format_episodes_context(episodes: list[dict]) -> str:
    lines = []
    for i, ep in enumerate(episodes, 1):
        lines.append(
            f"Sesión {i} ({ep.get('date', '?')} {ep.get('time', '')}, "
            f"{ep.get('turns', 0)} turnos, relevancia: {ep.get('score', 0):.2f}):"
        )
        summary = ep.get("summary", "").strip()
        if summary.startswith("["):
            newline_pos = summary.find("\n")
            summary = summary[newline_pos + 1:].strip() if newline_pos != -1 else summary
        lines.append(f"  {summary}")
        lines.append("")
    return "\n".join(lines).strip()


# ───────────────────────────────────────────────
# R5-MoA — AGENTE RECUPERADOR de memoria
# ───────────────────────────────────────────────

def _retrieve_memory_context(question: str, intents: list[str]) -> MemoryContext:
    if len(intents) > 1:
        composed = get_composed_context(intents)
        if not composed.strip():
            return MemoryContext(context_text="", fallback=_MEMORY_NOT_FOUND_MSG,
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
        return MemoryContext(context_text="", fallback=_format_profile_answer(p),
                             sources=["profile"], needs_llm=False)

    if kind == "tasks":
        t = get_tasks()
        if not t:
            return MemoryContext(context_text="", fallback="No encontré tareas registradas.",
                                 sources=["tasks"], needs_llm=False)
        return MemoryContext(context_text="", fallback=_format_tasks_answer(t, question=question),
                             sources=["tasks"], needs_llm=False)

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
            context_text = _format_episodes_context(episodes_with_content)
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
    return MemoryContext(context_text="", fallback=_MEMORY_NOT_FOUND_MSG,
                         sources=[kind], needs_llm=False)


# ───────────────────────────────────────────────
# R5-MoA — AGENTE SINTETIZADOR de memoria
# ───────────────────────────────────────────────

def _synthesize_memory_answer(
    question: str,
    context_text: str,
    fallback: str,
    chat_history: list | None = None,
) -> str:
    history_snippet = _build_history_snippet(chat_history) or "(sin historial previo)"
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


# ───────────────────────────────────────────────
# R5-MoA — ORQUESTADOR de memoria
# ───────────────────────────────────────────────

def _decide_memory(
    question: str,
    intents: list[str],
    chat_history: list | None = None,
) -> str:
    """D5: recibe intents ya detectados desde process_turn — no los re-detecta."""
    log.debug("R5-MoA: intents recibidos=%s para '%s'", intents, question[:60])

    if not intents:
        return _MEMORY_NOT_FOUND_MSG

    mem_ctx: MemoryContext = _retrieve_memory_context(question, intents)
    log.debug("R5-MoA: recuperador [sources=%s needs_llm=%s ctx_len=%d]",
              mem_ctx["sources"], mem_ctx["needs_llm"], len(mem_ctx["context_text"]))

    if not mem_ctx["needs_llm"]:
        return mem_ctx["fallback"]

    return _synthesize_memory_answer(
        question, mem_ctx["context_text"], mem_ctx["fallback"],
        chat_history=chat_history,
    )


# ───────────────────────────────────────────────
# R6-RAG — CACHÉ
# ───────────────────────────────────────────────

def _lookup_rag_cache(user_input: str, is_identity: bool) -> str | None:
    if is_identity:
        return None
    return cache_lookup(user_input)


# ───────────────────────────────────────────────
# R6-RAG — AGENTE RECUPERADOR RAG
# ───────────────────────────────────────────────

def _retrieve_rag_context(user_input: str, vectordb: Any, route: str) -> RagContext:
    """AGENTE RECUPERADOR RAG (R6-RAG).

    D3: usa experience_lookup_with_score() y aplica _MIN_EXPERIENCE_SCORE (0.70)
    como umbral propio — independiente del umbral interno de episode_store.
    Solo inyecta si score >= _MIN_EXPERIENCE_SCORE.
    """
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


# ───────────────────────────────────────────────
# R6-RAG — AGENTE GENERADOR RAG
# ───────────────────────────────────────────────

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
    chain = build_chain(QA_SYSTEM_PROMPT, rag_ctx["memory_context"])
    answer = chain.invoke({
        "question":     user_input,
        "context":      rag_ctx["context_text"],
        "chat_history": chat_history_text,
    })
    llm_ms = int((time.perf_counter() - t_llm_start) * 1000)

    is_faithful, score = verify_fidelity(answer, rag_ctx["source_docs"], question=user_input)
    if not is_faithful:
        log.warning("[R6-RAG] Respuesta bloqueada por fidelidad (score=%.3f): %s",
                    score, user_input[:60])
        return NO_EVIDENCE_MSG, rag_ctx["source_docs"], llm_ms, False, score

    return answer, rag_ctx["source_docs"], llm_ms, True, score


# ───────────────────────────────────────────────
# R6-RAG — ORQUESTADOR RAG
# ───────────────────────────────────────────────

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


# ───────────────────────────────────────────────
# Helpers — carril tool_list_files
# ───────────────────────────────────────────────

def _handle_list_files(question: str) -> str:
    files = list_project_files()
    question_lower = question.lower()
    wants_count = any(kw in question_lower for kw in _COUNT_KEYWORDS)

    if wants_count:
        if "python" in question_lower or ".py" in question_lower:
            py_files = [f for f in files if f.endswith(".py")]
            return f"El proyecto tiene {len(py_files)} archivos Python (.py)."
        if ".md" in question_lower or "markdown" in question_lower or "documentación" in question_lower:
            md_files = [f for f in files if f.endswith(".md")]
            return f"El proyecto tiene {len(md_files)} archivos Markdown (.md)."
        if ".json" in question_lower or "json" in question_lower:
            json_files = [f for f in files if f.endswith(".json")]
            return f"El proyecto tiene {len(json_files)} archivos JSON."
        return f"El proyecto tiene {len(files)} archivos en total."

    return "Archivos del proyecto:\n" + "\n".join(f"- {f}" for f in files)


# ───────────────────────────────────────────────
# Decisores — otros carriles (exit)
# ───────────────────────────────────────────────

def _compress_history(chat_history: list, max_line: int = _HISTORY_LINE_MAX) -> str:
    lines: list[str] = []
    for m in chat_history[-(MAX_TURNS * 2):]:
        role = "Usuario" if isinstance(m, HumanMessage) else "Lautaro"
        content = m.content.strip().replace("\n", " ")
        truncated = content[:max_line] + ("…" if len(content) > max_line else "")
        lines.append(f"{role}: {truncated}")
    return "\n".join(lines)


def _decide_exit(chat_history: list) -> DecisionResult:
    """D4-B: prompt reducido a 2 líneas y num_predict=45 para bajar latencia ~40% en CPU."""
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


# ───────────────────────────────────────────────
# Contrato público de la capa de inteligencia
# ───────────────────────────────────────────────

def process_turn(
    route_or_ctx: str | TurnContext,
    user_input: str | None = None,
    vectordb: Any = None,
    chat_history: list | None = None,
) -> DecisionResult:
    """Punto de entrada único de la capa de inteligencia.

    Acepta dos formas de llamada equivalentes:

    Forma nueva (TurnContext) — usada por chat_core:
        ctx = TurnContext(route="rag", query=user_input, vectordb=db, chat_history=hist)
        result = process_turn(ctx)
        answer = result["response"]
        docs   = result.get("source_docs", [])

    Forma legacy (4 args) — usada por tests existentes:
        result = process_turn(route, user_input, vectordb, chat_history)
        answer = result["response"]

    Retorna DecisionResult con campos explícitos:
        route, response, cached, source, source_docs,
        retrieval_ms, llm_ms, tokens_est
    """
    if isinstance(route_or_ctx, dict):
        ctx: TurnContext = route_or_ctx
        route        = ctx["route"]
        user_input   = ctx["query"]
        vectordb     = ctx["vectordb"]
        chat_history = ctx["chat_history"]
    else:
        route = route_or_ctx

    if chat_history is None:
        chat_history = []

    # ── exit ────────────────────────────────────────────────────────────────
    if route == "exit":
        result = _decide_exit(chat_history)
        _record_metric(route="exit", intent_type="exit")
        return result

    # ── identity ────────────────────────────────────────────────────────
    if route == "identity":
        _record_metric(route="identity", intent_type="identity")
        return DecisionResult(
            route="identity",
            response=_IDENTITY_MSG,
            cached=False,
            source="direct",
            source_docs=[],
            retrieval_ms=0,
            llm_ms=0,
            tokens_est=0,
        )

    # ── tool_list_files ─────────────────────────────────────────────────────
    if route == "tool_list_files":
        answer = _handle_list_files(user_input)
        _record_metric(route=route, intent_type="tool_list_files")
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

    # ── tools registradas ───────────────────────────────────────────────────
    if route in TOOLS:
        t0 = time.perf_counter()
        answer = dispatch_tool(route, user_input)
        llm_ms = int((time.perf_counter() - t0) * 1000)
        _record_metric(route=route, intent_type=route, llm_ms=llm_ms)
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

    # ── memory ──────────────────────────────────────────────────────────────
    # Fix P5-Paso4: lee subtipo desde el carril si está disponible (Capa 1).
    # Fallback a detect_memory_intents si el carril es 'memory' plano (Capa 2).
    if route == "memory" or route.startswith("memory:"):
        t0 = time.perf_counter()

        # Extraer subtipo del carril (ej. 'memory:tasks' → 'tasks')
        if ":" in route:
            subtype = route.split(":", 1)[1]
            intents = [subtype]
            log.debug("[memory] subtipo desde carril: %s", subtype)
        else:
            # Capa 2 o legacy — re-detectar como antes
            intents = detect_memory_intents(user_input)
            log.debug("[memory] subtipo re-detectado: %s", intents)

        memory_intent = intents[0] if intents else "memory_query"
        if len(intents) > 1:
            memory_intent = "multi:" + "+".join(intents)

        answer = _decide_memory(user_input, intents=intents, chat_history=chat_history)
        llm_ms = int((time.perf_counter() - t0) * 1000)
        tokens_est = int(len(answer.split()) * 1.3)

        # Normalizar route a "memory" para métricas consistentes
        _record_metric(route="memory", intent_type=memory_intent,
                       llm_ms=llm_ms, tokens_est=tokens_est)
        return DecisionResult(
            route="memory",
            response=answer,
            cached=False,
            source="json",
            source_docs=[],
            retrieval_ms=0,
            llm_ms=llm_ms,
            tokens_est=tokens_est,
        )

    # ── unsupported ─────────────────────────────────────────────────────────
    if route == "unsupported":
        _record_metric(route=route, intent_type="unsupported")
        return DecisionResult(
            route=route,
            response=_UNSUPPORTED_MSG,
            cached=False,
            source="direct",
            source_docs=[],
            retrieval_ms=0,
            llm_ms=0,
            tokens_est=0,
        )

    # ── rag (fallback) ───────────────────────────────────────────────────────
    answer, source_docs, retrieval_ms, llm_ms, cached = _decide_rag(
        user_input, vectordb, chat_history, route=route
    )
    tokens_est = int(len(answer.split()) * 1.3)
    _record_metric(
        route=route, intent_type=route,
        retrieval_ms=retrieval_ms, llm_ms=llm_ms,
        tokens_est=tokens_est,
        cached=cached, num_docs=len(source_docs),
    )
    return DecisionResult(
        route=route,
        response=answer,
        cached=cached,
        source="cache" if cached else "chroma",
        source_docs=source_docs,
        retrieval_ms=retrieval_ms,
        llm_ms=llm_ms,
        tokens_est=tokens_est,
    )
