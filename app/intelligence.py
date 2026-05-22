"""Capa de inteligencia — orquestador de decisión.

Responsabilidad única: dado un carril ya clasificado, decidir qué hacer
y devolver (respuesta, source_docs).

NO conoce chat.py ni chat_ui.py.
NO persiste historial de conversación — eso es responsabilidad de chat_core.
SÍ usa la capa de memoria (memory_manager) y los módulos de inteligencia
(rag_engine, fidelity_check, tool_registry, semantic_cache).

Contrato público
─────────────────
    process_turn(route, user_input, vectordb, chat_history) -> tuple[str, list]

R1 — contratos internos (CERRADO)
R2-connect — intent_type y num_docs en record_turn() (CERRADO)
R4-B — composición multi-capa de memoria (CERRADO)
Fix B3 — timeout síntesis subido de 10s a 30s (CERRADO)
Fix B4 — _format_tasks_answer distingue tareas hechas vs pendientes (CERRADO)
Fix C1 — chat_history en _synthesize_memory_answer (CERRADO)
Fix C2 — cliente LLM unificado con generate_raw() (CERRADO)
D2 — prompt de síntesis movido a prompts.py (CERRADO)
D3 — umbral episódico explícito en _retrieve_rag_context (CERRADO):
  Antes: experience_lookup() inyectaba si score >= 0.80 (umbral del store).
         intelligence.py no tenía criterio propio — dependía ciegamente
         del umbral hardcodeado en episode_store.
  Ahora: _retrieve_rag_context() llama experience_lookup_with_score(),
         recibe (snippet, score) y aplica _MIN_EXPERIENCE_SCORE = 0.70.
         Si score < 0.70 → no inyectar, loggear motivo.
         El agente RAG controla su propio criterio de calidad.
         experience_lookup() sigue disponible para compatibilidad.
D5 — detect_memory_intents se llama UNA sola vez en process_turn (CERRADO):
  Antes: process_turn detectaba intents y luego _decide_memory los re-detectaba.
  Ahora: process_turn detecta, pasa intents a _decide_memory como parámetro.
  _decide_memory ya no llama detect_memory_intents internamente.

R5-MoA — separación recuperador/sintetizador en _decide_memory (CERRADO):
  _retrieve_memory_context() ← AGENTE RECUPERADOR
  _synthesize_memory_answer() ← AGENTE SINTETIZADOR
  _decide_memory()            ← ORQUESTADOR
  Contrato explícito: MemoryContext (TypedDict).

R6-RAG — separación de responsabilidades en _decide_rag (CERRADO):
  Antes: _decide_rag() tenía 5 responsabilidades mezcladas:
    caché lookup, recuperación vectorial, inyección episódica,
    llamada LLM y verificación de fidelidad. Un solo punto de falla.
    La regla 'no cachear con inyección episódica' estaba enterrada.

  Ahora:
    _lookup_rag_cache(user_input, is_identity)
        ← CACHÉ: devuelve hit (str) o None. Sin efectos secundarios.

    _retrieve_rag_context(user_input, vectordb, route)
        ← RECUPERADOR: recuperación vectorial + inyección episódica.
          Devuelve RagContext (TypedDict) con context_text, source_docs,
          memory_context, experience_injected y retrieval_ms.
          D3: aplica _MIN_EXPERIENCE_SCORE = 0.70 sobre el score de
          experience_lookup_with_score() antes de inyectar.

    _generate_rag_answer(user_input, rag_ctx, chat_history)
        ← GENERADOR: construye el prompt, llama al LLM vía build_chain(),
          corre verify_fidelity() y devuelve (answer, source_docs,
          llm_ms, is_faithful, score). No sabe nada de caché ni de
          cómo se recuperó el contexto.

    _decide_rag(user_input, vectordb, chat_history, route)
        ← ORQUESTADOR: coordina los tres. La decisión de cachear es
          transparente en este nivel: visible en una sola condición
          con comentario, no escondida dentro de los sub-pasos.

  Beneficio: cada sub-función tiene exactamente 1 responsabilidad y
  puede testearse, reemplazarse o desactivarse en aislamiento.
  Agregar un nuevo paso (ej: re-ranking) solo toca _retrieve_rag_context.
  Cambiar la política de caché solo toca _decide_rag.
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

log = get_logger(__name__)

# Timeout para la llamada de resumen episódico (en segundos).
_EPISODE_TIMEOUT = 20

# Fix B3: timeout de síntesis subido de 10s a 30s.
_MEMORY_SYNTHESIS_TIMEOUT = 30

# Longitud máxima por línea de historial comprimido (chars).
_HISTORY_LINE_MAX = 80

# Score mínimo de fidelidad para guardar una respuesta en caché.
_CACHE_MIN_SCORE = 0.55

# D3: score mínimo que debe tener una experiencia episódica para inyectarla
# en el contexto RAG. Criterio propio del agente RAG — independiente del
# umbral EXPERIENCE_INJECT_THRESHOLD del store (0.80).
# 0.70 = semánticamente relevante; por debajo, el riesgo de ruido supera
# el beneficio del contexto adicional.
_MIN_EXPERIENCE_SCORE = 0.70

# Palabras que indican que el usuario quiere un CONTEO, no una lista.
_COUNT_KEYWORDS = {"cuántos", "cuantos", "cuántas", "cuantas", "cuanto", "cuánto"}

# Preguntas de identidad — bypass del caché semántico.
_IDENTITY_KEYWORDS = {"quién eres", "quien eres", "cómo te llamas", "como te llamas",
                      "cuál es tu nombre", "cual es tu nombre", "quién soy", "quien soy"}

# Fix B4: palabras que indican tareas COMPLETADAS.
_DONE_TASK_KEYWORDS = {
    "hechas", "hecho", "completadas", "completada", "completado",
    "cerradas", "cerrada", "terminadas", "terminada", "listas", "lista",
    "done",
}

# Fix C1: turnos recientes del historial a inyectar en síntesis de memoria.
_MEMORY_HISTORY_TURNS = 3

# Mensaje estándar para consultas fuera del alcance del agente.
_UNSUPPORTED_MSG = (
    "Esa consulta está fuera del alcance de lo que puedo hacer por ahora. "
    "Puedo responder preguntas sobre el proyecto, buscar en la documentación, "
    "consultar tareas y estado de trabajo."
)

# Mensaje cuando route=memory pero sin tipo reconocido.
_MEMORY_NOT_FOUND_MSG = (
    "No encontré información relevante en la memoria para esa pregunta. "
    "Si buscas datos del proyecto, prueba con: '¿cuál es el estado del proyecto?', "
    "'¿qué tareas tengo pendientes?' o '¿cuál es mi perfil?'."
)


# ───────────────────────────────────────────────
# TypedDicts — contratos entre sub-funciones (R5-MoA, R6-RAG)
# ───────────────────────────────────────────────

class MemoryContext(TypedDict):
    """Contrato de salida del AGENTE RECUPERADOR de memoria (R5-MoA)."""
    context_text: str       # texto plano listo para el prompt del sintetizador
    fallback: str           # respuesta estructurada si falla el LLM o needs_llm=False
    sources: list[str]      # cajones de memoria abiertos (para logging)
    needs_llm: bool         # True si la respuesta requiere síntesis LLM


class RagContext(TypedDict):
    """Contrato de salida del AGENTE RECUPERADOR RAG (R6-RAG).

    context_text       : texto de los documentos recuperados por ChromaDB
                         (puede incluir experiencia episódica prepend).
    source_docs        : documentos originales (para fidelidad y metadata).
    memory_context     : contexto de memoria selectiva ya serializado.
    experience_injected: True si se preprendó experiencia episódica.
                         Hace explícita la regla de caché: respuestas con
                         experiencia inyectada NO se cachean (son personalizadas).
    retrieval_ms       : tiempo de recuperación en milisegundos.
    """
    context_text: str
    source_docs: list
    memory_context: str
    experience_injected: bool
    retrieval_ms: int


# ───────────────────────────────────────────────
# Helpers de formato (sin LLM) — carril memory
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
    """Fix B4: distingue tareas hechas vs pendientes según keywords."""
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
    """Fix C1: extrae los últimos N turnos del historial como texto compacto."""
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
    """Formatea episodios de Chroma en texto legible para el sintetizador."""
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
    """AGENTE RECUPERADOR (R5-MoA): abre cajones de memoria y devuelve MemoryContext.

    No sabe nada del LLM. Solo recupera, formatea y empaqueta.
    """
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
    """AGENTE SINTETIZADOR (R5-MoA): recibe contexto limpio y genera respuesta.

    No sabe nada de JSON ni de qué cajón se abrió.
    Fix C1: inyecta historial. Fix C2: usa generate_raw() (singleton LLM).
    D2: usa MEMORY_SYNTHESIS_PROMPT desde prompts.py.
    """
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
    """ORQUESTADOR (R5-MoA): coordina recuperador y sintetizador de memoria.

    D5: recibe intents ya detectados desde process_turn — no los re-detecta.
    """
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
    """CACHÉ (R6-RAG): devuelve hit semántico o None. Sin efectos secundarios.

    Las preguntas de identidad nunca se sirven desde caché porque la
    respuesta depende del contexto de la sesión, no de los documentos.
    """
    if is_identity:
        return None
    return cache_lookup(user_input)


# ───────────────────────────────────────────────
# R6-RAG — AGENTE RECUPERADOR RAG
# ───────────────────────────────────────────────

def _retrieve_rag_context(user_input: str, vectordb: Any, route: str) -> RagContext:
    """AGENTE RECUPERADOR RAG (R6-RAG): recuperación vectorial + inyección episódica.

    No sabe nada del LLM ni de la caché. Solo recupera y empaqueta.
    La regla de cacheabilidad queda explícita en el campo experience_injected
    del contrato RagContext, no enterrada en lógica interna.

    Pasos:
      1. get_selective_context() — memoria estructurada para el prompt.
      2. retrieve_context()      — recuperación vectorial MMR en ChromaDB.
      3. experience_lookup_with_score() — inyección episódica con umbral propio (D3).
         Solo inyecta si score >= _MIN_EXPERIENCE_SCORE = 0.70.
    """
    t_start = time.perf_counter()

    memory_context = get_selective_context(route)
    context_text, source_docs = retrieve_context(user_input, vectordb)

    experience_injected = False
    try:
        from app.episode_store import experience_lookup_with_score
        snippet, exp_score = experience_lookup_with_score(user_input)
        if snippet is not None:
            if exp_score >= _MIN_EXPERIENCE_SCORE:
                context_text = snippet + "\n\n---\n\n" + context_text
                experience_injected = True
                log.debug(
                    "[R6-RAG] Experiencia episódica inyectada (score=%.3f >= %.2f)",
                    exp_score, _MIN_EXPERIENCE_SCORE,
                )
            else:
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
    """AGENTE GENERADOR RAG (R6-RAG): construye prompt, llama LLM, verifica fidelidad.

    No sabe nada de caché ni de cómo se recuperó el contexto.
    Recibe RagContext limpio y devuelve (answer, source_docs, llm_ms, is_faithful, score).
    Si la fidelidad falla, devuelve NO_EVIDENCE_MSG como answer.
    """
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
    """ORQUESTADOR RAG (R6-RAG): coordina caché, recuperador y generador.

    Flujo:
      1. Determina si es pregunta de identidad (bypass caché).
      2. CACHÉ: busca hit semántico — si hay, devuelve inmediato.
      3. RECUPERADOR: abre ChromaDB + inyección episódica → RagContext.
      4. GENERADOR: construye prompt + LLM + fidelidad → respuesta.
      5. ORQUESTADOR decide caché: política explícita y visible en este nivel.
           No cachear si: identidad | experiencia inyectada | score bajo.

    Returns:
        (answer, source_docs, retrieval_ms, llm_ms, cached)
    """
    is_identity = any(kw in user_input.lower() for kw in _IDENTITY_KEYWORDS)

    # PASO 1: CACHÉ
    hit = _lookup_rag_cache(user_input, is_identity)
    if hit is not None:
        log.debug("[R6-RAG] Respuesta servida desde caché semántica")
        return hit, [], 0, 0, True

    # PASO 2: RECUPERADOR
    rag_ctx = _retrieve_rag_context(user_input, vectordb, route)

    # PASO 3: GENERADOR
    answer, source_docs, llm_ms, is_faithful, score = _generate_rag_answer(
        user_input, rag_ctx, chat_history
    )

    # PASO 4: ORQUESTADOR decide caché (política transparente)
    # Regla 1: no cachear preguntas de identidad (dependen del contexto de sesión)
    # Regla 2: no cachear si hay experiencia episódica inyectada (respuesta personalizada)
    # Regla 3: no cachear si la fidelidad es baja
    can_cache = (
        not is_identity
        and not rag_ctx["experience_injected"]
        and is_faithful
        and score >= _CACHE_MIN_SCORE
    )
    if can_cache:
        log.debug("[R6-RAG] Guardando en caché (score=%.3f)", score)
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


def _decide_exit(chat_history: list) -> tuple[str, list]:
    """Genera resumen episódico y señala cierre de sesión. Fix C2: usa generate_raw()."""
    turns = len(chat_history) // 2
    summary = "Resumen no disponible (sesión cerrada sin tiempo para generar)."

    if turns > 0:
        log.info("Guardando resumen episódico (%d turnos)", turns)
        history_text = _compress_history(chat_history)
        prompt = (
            "Eres un asistente que resume sesiones de trabajo.\n"
            "Resume la siguiente conversación en exactamente 3 líneas en español.\n"
            "Línea 1: tema principal tratado.\n"
            "Línea 2: qué se logró o decidió.\n"
            "Línea 3: cuál es el siguiente paso pendiente.\n"
            "Sin bullet points ni numeración. Solo 3 líneas.\n\n"
            f"Conversación:\n{history_text}\n\nResumen:"
        )
        generated = generate_raw(prompt, temperature=0.2, num_predict=80,
                                 timeout=_EPISODE_TIMEOUT)
        if generated:
            summary = generated
        else:
            log.warning("No se pudo generar resumen de sesión")

    record_episode(summary=summary, turns=turns)
    log.info("Episodio guardado correctamente (turns=%d)", turns)
    return "__EXIT__", []


# ───────────────────────────────────────────────
# Contrato público de la capa de inteligencia
# ───────────────────────────────────────────────

def process_turn(
    route: str,
    user_input: str,
    vectordb: Any,
    chat_history: list,
) -> tuple[str, list]:
    """Punto de entrada único de la capa de inteligencia."""
    t_start = time.perf_counter()

    if route == "exit":
        result = _decide_exit(chat_history)
        _record_metric(route="exit", intent_type="exit")
        return result

    if route == "tool_list_files":
        answer = _handle_list_files(user_input)
        _record_metric(route=route, intent_type="tool_list_files")
        return answer, []

    if route in TOOLS:
        t0 = time.perf_counter()
        answer = dispatch_tool(route, user_input)
        _record_metric(route=route, intent_type=route,
                       llm_ms=int((time.perf_counter() - t0) * 1000))
        return answer, []

    if route == "memory":
        t0 = time.perf_counter()
        # D5: detect_memory_intents se llama UNA sola vez aquí.
        # _decide_memory recibe los intents como parámetro — no los re-detecta.
        intents = detect_memory_intents(user_input)
        memory_intent = intents[0] if intents else "memory_query"
        if len(intents) > 1:
            memory_intent = "multi:" + "+".join(intents)
        answer = _decide_memory(user_input, intents=intents, chat_history=chat_history)
        _record_metric(route=route, intent_type=memory_intent,
                       llm_ms=int((time.perf_counter() - t0) * 1000),
                       tokens_est=int(len(answer.split()) * 1.3))
        return answer, []

    if route == "unsupported":
        log.debug("Carril unsupported — respondiendo sin LLM")
        _record_metric(route=route, intent_type="unsupported")
        return _UNSUPPORTED_MSG, []

    answer, source_docs, retrieval_ms, llm_ms, cached = _decide_rag(
        user_input, vectordb, chat_history, route=route
    )
    _record_metric(
        route=route, intent_type=route,
        retrieval_ms=retrieval_ms, llm_ms=llm_ms,
        tokens_est=int(len(answer.split()) * 1.3),
        cached=cached, num_docs=len(source_docs),
    )
    return answer, source_docs
