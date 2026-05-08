"""Orquestador principal del chat.

Responsabilidad única: coordinar el flujo de una consulta.
No contiene lógica de infraestructura — delega en módulos especializados:
  - app.config          → constantes globales
  - app.memory_context  → construir contexto de memoria para el LLM
  - app.rag_engine      → recuperación RAG y chain LangChain
  - app.router          → clasificación de intención
  - app.tool_registry   → despacho de tools
  - app.semantic_cache  → caché semántica
  - app.fidelity_check  → verificación de fidelidad
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import MAX_TURNS, MODEL_NAME, OLLAMA_URL
from app.logger import get_logger
from app.memory_store import (
    load_profile,
    load_project_facts,
    load_tasks,
    load_work_state,
    save_episode,
)
from app.memory_context import build_memory_context
from app.rag_engine import retrieve_context, build_chain, load_vector_store
from app.semantic_cache import cache_lookup, cache_save
from app.fidelity_check import verify_fidelity, NO_EVIDENCE_MSG
from app.router import route_query, classify_memory_query
from app.tool_registry import TOOLS, dispatch_tool
from app.prompts import QA_SYSTEM_PROMPT

from langchain_core.messages import HumanMessage, AIMessage

log = get_logger(__name__)

MEMORY_FILE = Path("storage/memory.json")


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
# Carril memory
# ─────────────────────────────────────────────

def answer_from_memory(question: str) -> str | None:
    kind = classify_memory_query(question)
    log.debug("Carril memory clasificado como: %s", kind)
    if kind == "profile":
        p = load_profile()
        return _format_profile_answer(p) if p else "No encontré información de perfil."
    if kind == "project_facts":
        f = load_project_facts()
        return _format_project_facts_answer(f) if f else "No encontré hechos del proyecto."
    if kind == "tasks":
        t = load_tasks()
        return _format_tasks_answer(t) if t else "No encontré tareas registradas."
    if kind == "work_state":
        w = load_work_state()
        return _format_work_state_answer(w) if w else "No encontré estado de trabajo."
    return None


# ─────────────────────────────────────────────
# Historial de conversación
# ─────────────────────────────────────────────

def build_memory() -> list:
    """Lee el historial desde memory.json."""
    if not MEMORY_FILE.exists():
        return []
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        messages = []
        for m in data.get("messages", [])[-(MAX_TURNS * 2):]:
            if m.get("role") == "human":
                messages.append(HumanMessage(content=m["content"]))
            elif m.get("role") == "ai":
                messages.append(AIMessage(content=m["content"]))
        return messages
    except Exception as exc:
        log.warning("No se pudo leer memory.json: %s", exc)
        return []


def _format_chat_history(messages: list) -> str:
    if not messages:
        return "(sin historial previo)"
    return "\n".join(
        f"{'Usuario' if isinstance(m, HumanMessage) else 'Lautaro'}: {m.content}"
        for m in messages
    )


def _persist_turn(user_input: str, answer: str) -> None:
    if MEMORY_FILE.exists():
        try:
            data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(data.get("messages"), list):
                data = {"messages": []}
        except Exception:
            data = {"messages": []}
    else:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"messages": []}
    data["messages"].append({"role": "human", "content": user_input})
    data["messages"].append({"role": "ai",    "content": answer})
    if len(data["messages"]) > MAX_TURNS * 2:
        data["messages"] = data["messages"][-(MAX_TURNS * 2):]
    MEMORY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ─────────────────────────────────────────────
# Resumen episódico (SimpleMem)
# ─────────────────────────────────────────────

def generate_session_summary(chat_history: list) -> str:
    if not chat_history:
        return "Sesión sin mensajes registrados."
    import requests
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
        return response.json().get("response", "Resumen no disponible.").strip()
    except Exception as exc:
        log.warning("No se pudo generar resumen de sesión: %s", exc)
        return "Resumen no disponible (Ollama no respondió al cerrar)."


# ─────────────────────────────────────────────
# Handlers internos
# ─────────────────────────────────────────────

def _handle_exit(chat_history: list) -> tuple[str, list]:
    turns = len(chat_history) // 2
    if turns > 0:
        log.info("Guardando resumen episódico (%d turnos)", turns)
        summary = generate_session_summary(chat_history)
        save_episode(summary=summary, turns=turns)
        log.info("Episodio guardado correctamente")
    return "__EXIT__", []


def _handle_rag(
    user_input: str,
    vectordb: Any,
    chat_history: list,
) -> tuple[str, list]:
    # 1. Caché semántica
    cached = cache_lookup(user_input)
    if cached is not None:
        log.debug("Respuesta servida desde caché semántica")
        _persist_turn(user_input, cached)
        chat_history.append(HumanMessage(content=user_input))
        chat_history.append(AIMessage(content=cached))
        while len(chat_history) > MAX_TURNS * 2:
            chat_history.pop(0)
        return cached, []

    # 2. Recuperar contexto RAG
    memory_context = build_memory_context()
    context_text, source_docs = retrieve_context(user_input, vectordb)
    chat_history_text = _format_chat_history(chat_history)

    # 3. Invocar LLM
    chain  = build_chain(QA_SYSTEM_PROMPT, memory_context)
    answer = chain.invoke({
        "question":     user_input,
        "context":      context_text,
        "chat_history": chat_history_text,
    })

    # 4. Fidelity check
    is_faithful, score = verify_fidelity(answer, source_docs)
    if not is_faithful:
        log.warning(
            "Respuesta bloqueada por fidelidad (score=%.3f): %s",
            score, user_input[:60],
        )
        return NO_EVIDENCE_MSG, source_docs

    # 5. Persistir turno
    cache_save(user_input, answer)
    _persist_turn(user_input, answer)
    chat_history.append(HumanMessage(content=user_input))
    chat_history.append(AIMessage(content=answer))
    while len(chat_history) > MAX_TURNS * 2:
        chat_history.pop(0)

    return answer, source_docs


# ─────────────────────────────────────────────
# Punto de entrada público
# ─────────────────────────────────────────────

def handle_query(
    user_input: str,
    vectordb: Any,
    chat_history: list,
) -> tuple[str, list]:
    """Clasifica la consulta y la despacha al carril correcto.

    Returns:
        (respuesta, source_docs)  — source_docs puede ser lista vacía.
    """
    route = route_query(user_input)
    log.debug("Ruta asignada: '%s' para: %s", route, user_input[:60])

    if route == "exit":    return _handle_exit(chat_history)
    if route in TOOLS:     return dispatch_tool(route, user_input), []
    if route == "memory":
        answer = answer_from_memory(user_input)
        if answer is not None: return answer, []

    return _handle_rag(user_input, vectordb, chat_history)
