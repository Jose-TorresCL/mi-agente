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

Cambios Día 3:
  _decide_exit():
    - El episodio se guarda SIEMPRE, incluso si el resumen falla.
      Antes: si requests.post lanzaba timeout, record_episode() nunca se llamaba.
    - Historial comprimido: se pasa al LLM solo la última línea de cada turno
      (máx. 80 chars). Menos tokens → respuesta más rápida → menos timeouts.
    - Timeout reducido de 30s a 20s: el resumen es corto (3 líneas, 120 tokens);
      si Ollama no responde en 20s en el cierre, probablemente no responderá.
    - num_predict reducido de 120 a 80 tokens: 3 líneas de resumen no necesitan más.

Cambios Día 4:
  _decide_memory():
    - Ya no hace dump crudo de project_facts/work_state al usuario.
    - Para preguntas de tipo 'project_facts' y 'work_state', el contexto se
      pasa al LLM para que genere una respuesta sintetizada y natural.
    - 'profile' y 'tasks' siguen con formato estructurado (son listas cortas
      y el usuario espera verlas como lista, no como prosa).
    - Timeout 25s para la llamada de síntesis (más corto que el RAG principal).
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, AIMessage

from app.config import MAX_TURNS, MODEL_NAME, OLLAMA_URL
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

# Timeout para la llamada de resumen episódico (en segundos).
_EPISODE_TIMEOUT = 20

# Timeout para la síntesis del carril memory (en segundos).
_MEMORY_SYNTHESIS_TIMEOUT = 25

# Longitud máxima por línea de historial comprimido (chars).
_HISTORY_LINE_MAX = 80


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


def _synthesize_memory_answer(question: str, context_text: str, fallback: str) -> str:
    """Llama al LLM para sintetizar una respuesta natural a partir del contexto
    de memoria estructurada.

    Día 4: reemplaza el dump crudo de project_facts/work_state por una respuesta
    sintetizada. Si Ollama falla o tarda más de _MEMORY_SYNTHESIS_TIMEOUT,
    devuelve el fallback con los datos en bruto.

    Args:
        question:     Pregunta original del usuario.
        context_text: Contexto de memoria serializado (project_facts o work_state).
        fallback:     Texto crudo a mostrar si la síntesis falla.

    Returns:
        Respuesta sintetizada o fallback.
    """
    import requests

    prompt = (
        "Eres Lautaro, asistente técnico local del proyecto 'mi-agente'.\n"
        "Tienes acceso a los siguientes datos del proyecto:\n\n"
        f"{context_text}\n\n"
        "Responde la siguiente pregunta de forma natural, clara y concisa "
        "en español. No listes todos los campos — sintetiza lo más relevante "
        "para la pregunta. Máximo 4 oraciones.\n\n"
        f"Pregunta: {question}\n\nRespuesta:"
    )

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 150},
            },
            timeout=_MEMORY_SYNTHESIS_TIMEOUT,
        )
        answer = response.json().get("response", "").strip()
        if answer:
            return answer
    except Exception as exc:
        log.warning("Síntesis de memoria falló, usando fallback: %s", exc)

    return fallback


# ─────────────────────────────────────────────
# Decisores internos por carril
# ─────────────────────────────────────────────

def _decide_memory(question: str) -> str | None:
    """Responde desde memoria estructurada. Devuelve None si no aplica.

    Día 4:
    - 'profile' y 'tasks' mantienen formato de lista (el usuario espera verlos así).
    - 'project_facts' y 'work_state' pasan por síntesis LLM para respuesta natural.
      Si la síntesis falla, se muestra el formato estructurado como fallback.
    """
    kind = classify_memory_query(question)
    log.debug("Carril memory clasificado como: %s", kind)

    if kind == "profile":
        p = get_profile()
        return _format_profile_answer(p) if p else "No encontré información de perfil."

    if kind == "tasks":
        t = get_tasks()
        return _format_tasks_answer(t) if t else "No encontré tareas registradas."

    if kind == "project_facts":
        f = get_project_facts()
        if not f:
            return "No encontré hechos del proyecto."
        # Día 4: sintetizar en lugar de listar todos los keys
        context_text = "\n".join(f"- {k}: {v}" for k, v in f.items())
        fallback = "**Hechos del proyecto:**\n" + context_text
        return _synthesize_memory_answer(question, context_text, fallback)

    if kind == "work_state":
        w = get_work_state()
        if not w:
            return "No encontré estado de trabajo."
        # Día 4: sintetizar en lugar de listar todos los campos
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
        fallback = "**Estado de trabajo:**\n" + context_text
        return _synthesize_memory_answer(question, context_text, fallback)

    return None


def _compress_history(chat_history: list, max_line: int = _HISTORY_LINE_MAX) -> str:
    """Comprime el historial de conversación para el prompt de resumen episódico."""
    lines: list[str] = []
    for m in chat_history[-(MAX_TURNS * 2):]:
        role = "Usuario" if isinstance(m, HumanMessage) else "Lautaro"
        content = m.content.strip().replace("\n", " ")
        truncated = content[:max_line] + ("…" if len(content) > max_line else "")
        lines.append(f"{role}: {truncated}")
    return "\n".join(lines)


def _decide_exit(chat_history: list) -> tuple[str, list]:
    """Genera resumen episódico y señala cierre de sesión.

    Día 3 — cambios clave:
      1. El episodio se guarda SIEMPRE (incluso si el resumen falla).
      2. Historial comprimido: solo los primeros 80 chars por turno.
      3. Timeout reducido a 20s y num_predict a 80 tokens.
    """
    import requests

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

        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 80},
                },
                timeout=_EPISODE_TIMEOUT,
            )
            summary = response.json().get("response", summary).strip()
        except Exception as exc:
            log.warning("No se pudo generar resumen de sesión: %s", exc)

    # Día 3: record_episode() se llama SIEMPRE (antes estaba dentro del try)
    record_episode(summary=summary, turns=turns)
    log.info("Episodio guardado correctamente (turns=%d)", turns)

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
        log.debug("memory no resolvió, fallback a RAG")
        return _decide_rag(user_input, vectordb, chat_history, route="memory")

    return _decide_rag(user_input, vectordb, chat_history, route=route)
