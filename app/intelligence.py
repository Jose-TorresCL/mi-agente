"""Capa de inteligencia — orquestador de decisión.

Responsabilidad única: dado un carril ya clasificado, decidir qué hacer
y devolver (respuesta, source_docs).

NO conoce chat.py ni chat_ui.py.
NO persiste historial de conversación — eso es responsabilidad de chat_core.
SÍ usa la capa de memoria (memory_manager) y los módulos de inteligencia
(rag_engine, fidelity_check, tool_registry, semantic_cache).

Contrato público
─────────────────
    process_turn(route, user_input, vectordb, chat_history) -> (str, list)
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, AIMessage

from app.config import MAX_TURNS
from app.logger import get_logger
from app.memory_manager import (
    get_selective_context,
    get_profile,
    get_project_facts,
    get_tasks,
    get_work_state,
    record_episode,
)
from app.rag_engine import retrieve_context, build_chain
from app.semantic_cache import cache_lookup, cache_save
from app.fidelity_check import verify_fidelity, NO_EVIDENCE_MSG
from app.router import classify_memory_query
from app.tool_registry import TOOLS, dispatch_tool
from app.prompts import QA_SYSTEM_PROMPT

log = get_logger(__name__)


# ─────────────────────────────────────────────
# Helpers de formato — carril memory
# ─────────────────────────────────────────────

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


def _format_project_facts_answer(facts: dict) -> str:
    lines = ["**Hechos persistentes del proyecto:**"]
    for key, value in facts.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def _format_tasks_answer(tasks_data: dict) -> str:
    tasks = tasks_data.get("tasks", [])
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


def _format_work_state_answer(work_state: dict) -> str:
    lines = ["**Estado actual de trabajo:**"]
    lines.append(f"- Foco actual: {work_state.get('current_focus', 'sin definir')}")
    lines.append(f"- Último paso completado: {work_state.get('last_completed', 'sin registrar')}")
    lines.append(f"- Siguiente paso: {work_state.get('next_step', 'sin definir')}")
    blockers = work_state.get("current_blockers", [])
    if blockers:
        lines.append(f"- Bloqueos: {', '.join(blockers)}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# Decisores internos por carril
# ─────────────────────────────────────────────

def _decide_memory(question: str) -> str | None:
    """Responde desde memoria estructurada. Devuelve None si no aplica."""
    kind = classify_memory_query(question)
    log.debug("Carril memory clasificado como: %s", kind)
    if kind == "profile":
        p = get_profile()
        return _format_profile_answer(p) if p else "No encontré información de perfil."
    if kind == "project_facts":
        f = get_project_facts()
        return _format_project_facts_answer(f) if f else "No encontré hechos del proyecto."
    if kind == "tasks":
        t = get_tasks()
        return _format_tasks_answer(t) if t else "No encontré tareas registradas."
    if kind == "work_state":
        w = get_work_state()
        return _format_work_state_answer(w) if w else "No encontré estado de trabajo."
    return None


def _decide_exit(chat_history: list) -> tuple[str, list]:
    """Genera resumen episódico y señala cierre de sesión."""
    turns = len(chat_history) // 2
    if turns > 0:
        from app.config import MODEL_NAME, OLLAMA_URL
        import requests
        log.info("Guardando resumen episódico (%d turnos)", turns)
        history_text = "\n".join(
            f"{'Usuario' if isinstance(m, HumanMessage) else 'Lautaro'}: {m.content}"
            for m in chat_history[-(MAX_TURNS * 2):]
        )
        prompt = (
            "Eres un asistente que resume sesiones de trabajo.\n"
            "Resume la siguiente conversación en exactamente 3 líneas en español.\n"
            "Línea 1: tema principal tratado.\n"
            "Línea 2: qué se logró o decidió.\n"
            "Línea 3: cuál es el siguiente paso pendiente.\n"
            "Sin bullet points ni numeración. Solo 3 líneas.\n\n"
            f"Conversación:\n{history_text}\n\nResumen:"
        )
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 120},
                },
                timeout=30,
            )
            summary = response.json().get("response", "Resumen no disponible.").strip()
        except Exception as exc:
            log.warning("No se pudo generar resumen de sesión: %s", exc)
            summary = "Resumen no disponible (Ollama no respondió al cerrar)."
        record_episode(summary=summary, turns=turns)
        log.info("Episodio guardado correctamente")
    return "__EXIT__", []


def _decide_rag(
    user_input: str,
    vectordb: Any,
    chat_history: list,
    route: str,
) -> tuple[str, list]:
    """Recupera contexto RAG, invoca LLM y verifica fidelidad."""
    # 1. Caché semántica
    cached = cache_lookup(user_input)
    if cached is not None:
        log.debug("Respuesta servida desde caché semántica")
        return cached, []

    # 2. Contexto de memoria selectivo según carril (ADR-004)
    memory_context = get_selective_context(route)
    context_text, source_docs = retrieve_context(user_input, vectordb)

    chat_history_text = "\n".join(
        f"{'Usuario' if isinstance(m, HumanMessage) else 'Lautaro'}: {m.content}"
        for m in chat_history
    ) or "(sin historial previo)"

    # 3. Invocar LLM
    chain = build_chain(QA_SYSTEM_PROMPT, memory_context)
    answer = chain.invoke({
        "question":     user_input,
        "context":      context_text,
        "chat_history": chat_history_text,
    })

    # 4. Fidelity check con umbral dinámico (ADR-004)
    is_faithful, score = verify_fidelity(answer, source_docs, question=user_input)
    if not is_faithful:
        log.warning(
            "Respuesta bloqueada por fidelidad (score=%.3f): %s",
            score, user_input[:60],
        )
        return NO_EVIDENCE_MSG, source_docs

    # 5. Guardar en caché
    cache_save(user_input, answer)
    return answer, source_docs


# ─────────────────────────────────────────────
# Contrato público de la capa de inteligencia
# ─────────────────────────────────────────────

def process_turn(
    route: str,
    user_input: str,
    vectordb: Any,
    chat_history: list,
) -> tuple[str, list]:
    """Punto de entrada único de la capa de inteligencia.

    Recibe el carril ya clasificado y devuelve (respuesta, source_docs).
    No persiste historial — esa responsabilidad pertenece a chat_core.

    Flujo:
        exit   → _decide_exit
        tool   → dispatch_tool
        memory → _decide_memory  (fallback a RAG si no resuelve)
        resto  → _decide_rag
    """
    if route == "exit":
        return _decide_exit(chat_history)

    if route in TOOLS:
        return dispatch_tool(route, user_input), []

    if route == "memory":
        answer = _decide_memory(user_input)
        if answer is not None:
            return answer, []
        # fallback: la pregunta de memoria no resolvió → RAG con contexto completo
        log.debug("memory no resolvió, fallback a RAG")
        return _decide_rag(user_input, vectordb, chat_history, route="memory")

    # carriles: rag, estado, conversación, y cualquier otro no reconocido
    return _decide_rag(user_input, vectordb, chat_history, route=route)
