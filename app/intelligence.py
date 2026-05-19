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
    - Historial comprimido: se pasa al LLM solo la última línea de cada turno
      (máx. 80 chars). Menos tokens → respuesta más rápida → menos timeouts.
    - Timeout reducido de 30s a 20s.
    - num_predict reducido de 120 a 80 tokens.

Cambios Día 4:
  _decide_memory():
    - Ya no hace dump crudo de project_facts/work_state al usuario.
    - Para preguntas de tipo 'project_facts' y 'work_state', el contexto se
      pasa al LLM para que genere una respuesta sintetizada y natural.
    - 'profile' y 'tasks' siguen con formato estructurado.
    - Timeout 10s para la llamada de síntesis (bajado de 25s).

Fix Tarea 1 (post-pruebas):
  - _MEMORY_SYNTHESIS_TIMEOUT: 25s → 10s.
  - tool_list_files: detecta 'cuántos/cuántas' y devuelve conteo.
  - _decide_rag: bypass de caché para preguntas de identidad.

Fix Paso 2 (cache condicional):
  - _CACHE_MIN_SCORE = 0.55: solo se cachea si fidelity_score >= umbral.
  - Evita que respuestas genéricas/inventadas queden en caché entre sesiones.
  - Las respuestas que pasan el bloqueo de fidelidad pero con score bajo
    se recalculan en cada sesión en vez de propagarse como respuesta "oficial".

Fix carril unsupported:
  - process_turn: agrega elif para route == 'unsupported'.
  - Antes caía a _decide_rag disparando LLM + Chroma innecesariamente.
  - Ahora devuelve mensaje directo sin tocar el vectorstore ni el modelo.

Fix 6A — _decide_memory terminal:
  - _decide_memory ya no devuelve None cuando route=memory.
  - Si el tipo de consulta no es reconocido por classify_memory_query,
    devuelve mensaje explícito en lugar de caer silenciosamente a RAG.
  - Evita que preguntas de memoria mal clasificadas activen la caché
    semántica del carril RAG.
  - El fallback a RAG desde memory queda como safety net explícito y logueado.

Fix 6B — tipo 'episode' en classify_memory_query (ver router.py):
  - _decide_memory maneja el nuevo tipo 'episode' con get_episodic_context().
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
from app.tool_helpers import list_project_files

log = get_logger(__name__)

# Timeout para la llamada de resumen episódico (en segundos).
_EPISODE_TIMEOUT = 20

# Timeout para la síntesis del carril memory (en segundos).
# Fix Tarea 1: bajado de 25s a 10s — si Ollama tarda, cae al fallback
# antes sin congelar la conversación demasiado tiempo.
_MEMORY_SYNTHESIS_TIMEOUT = 10

# Longitud máxima por línea de historial comprimido (chars).
_HISTORY_LINE_MAX = 80

# Score mínimo de fidelidad para guardar una respuesta en caché.
# Fix Paso 2: antes se cacheaba cualquier respuesta que pasara el bloqueo.
# Ahora solo se cachea si el score es suficientemente alto, evitando que
# respuestas genéricas/inventadas se propaguen entre sesiones.
_CACHE_MIN_SCORE = 0.55

# Palabras que indican que el usuario quiere un CONTEO, no una lista.
_COUNT_KEYWORDS = {"cuántos", "cuantos", "cuántas", "cuantas", "cuanto", "cuánto"}

# Preguntas de identidad — bypass del caché semántico para evitar
# que respuestas de sesiones anteriores contaminen la respuesta.
_IDENTITY_KEYWORDS = {"quién eres", "quien eres", "cómo te llamas", "como te llamas",
                      "cuál es tu nombre", "cual es tu nombre", "quién soy", "quien soy"}

# Mensaje estándar para consultas fuera del alcance del agente.
_UNSUPPORTED_MSG = (
    "Esa consulta está fuera del alcance de lo que puedo hacer por ahora. "
    "Puedo responder preguntas sobre el proyecto, buscar en la documentación, "
    "consultar tareas y estado de trabajo."
)

# Fix 6A: mensaje cuando route=memory pero el tipo no es reconocido.
# En lugar de caer silenciosamente a RAG (y potencialmente activar la caché),
# se responde con un mensaje honesto y se loguea para diagnóstico.
_MEMORY_NOT_FOUND_MSG = (
    "No encontré información relevante en la memoria para esa pregunta. "
    "Si buscas datos del proyecto, prueba con: '¿cuál es el estado del proyecto?', "
    "'¿qué tareas tengo pendientes?' o '¿cuál es mi perfil?'."
)


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

    Fix Tarea 1: timeout reducido de 25s a 10s para evitar bloqueos largos.
    Si Ollama falla o tarda más de _MEMORY_SYNTHESIS_TIMEOUT, devuelve el
    fallback con los datos en bruto.
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
# Helpers — carril tool_list_files
# ─────────────────────────────────────────────

def _handle_list_files(question: str) -> str:
    """Devuelve conteo o lista según la intención de la pregunta.

    Fix Tarea 1: si la pregunta contiene 'cuántos/cuántas', devuelve un
    número en vez de la lista completa de archivos.

    Ejemplos:
      '¿Cuántos archivos Python tiene el proyecto?' → conteo de .py
      '¿Cuántos archivos tiene el proyecto?'        → conteo total
      'lista los archivos del proyecto'             → lista completa
    """
    files = list_project_files()
    question_lower = question.lower()

    wants_count = any(kw in question_lower for kw in _COUNT_KEYWORDS)

    if wants_count:
        # Detectar filtro por extensión
        if "python" in question_lower or ".py" in question_lower:
            py_files = [f for f in files if f.endswith(".py")]
            return f"El proyecto tiene {len(py_files)} archivos Python (.py)."
        if ".md" in question_lower or "markdown" in question_lower or "documentación" in question_lower:
            md_files = [f for f in files if f.endswith(".md")]
            return f"El proyecto tiene {len(md_files)} archivos Markdown (.md)."
        if ".json" in question_lower or "json" in question_lower:
            json_files = [f for f in files if f.endswith(".json")]
            return f"El proyecto tiene {len(json_files)} archivos JSON."
        # Sin filtro: contar todo
        return f"El proyecto tiene {len(files)} archivos en total."

    # Sin keyword de conteo: lista completa (comportamiento original)
    return "Archivos del proyecto:\n" + "\n".join(f"- {f}" for f in files)


# ─────────────────────────────────────────────
# Decisores internos por carril
# ─────────────────────────────────────────────

def _decide_memory(question: str) -> str:
    """Responde desde memoria estructurada.

    Fix 6A: ya no devuelve None. Siempre retorna un string.
    Si el tipo no es reconocido, devuelve _MEMORY_NOT_FOUND_MSG en lugar
    de caer silenciosamente al carril RAG (y potencialmente a la caché).

    Tipos reconocidos:
      'profile'       → formato de lista estructurada
      'tasks'         → formato de lista estructurada
      'project_facts' → síntesis LLM (fallback: formato bruto)
      'work_state'    → síntesis LLM (fallback: formato bruto)
      'episode'       → episodios de sesiones anteriores (fix 6B)
      None            → _MEMORY_NOT_FOUND_MSG (nunca cae a RAG)
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
        context_text = "\n".join(f"- {k}: {v}" for k, v in f.items())
        fallback = "**Hechos del proyecto:**\n" + context_text
        return _synthesize_memory_answer(question, context_text, fallback)

    if kind == "work_state":
        w = get_work_state()
        if not w:
            return "No encontré estado de trabajo."
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

    if kind == "episode":
        # Fix 6B: conectar a get_episodic_context() cuando esté disponible.
        # Por ahora, intento importar la función y caigo a mensaje informativo si no existe.
        try:
            from app.memory_manager import get_episodic_context
            episodes = get_episodic_context()
            if not episodes:
                return "No encontré episodios de sesiones anteriores registrados."
            return episodes
        except (ImportError, AttributeError):
            log.debug("get_episodic_context() no disponible aún — fix 6B-2 pendiente")
            return (
                "Los episodios de sesiones anteriores estarán disponibles pronto. "
                "Por ahora, el historial se guarda en storage/memory/episodes.json "
                "pero aún no tiene recuperación semántica activa."
            )

    # Fix 6A: tipo no reconocido → respuesta explícita, NO caída a RAG.
    log.debug("memory: tipo no reconocido para '%s' — devolviendo not-found", question[:60])
    return _MEMORY_NOT_FOUND_MSG


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

    record_episode(summary=summary, turns=turns)
    log.info("Episodio guardado correctamente (turns=%d)", turns)

    return "__EXIT__", []


def _decide_rag(
    user_input: str,
    vectordb: Any,
    chat_history: list,
    route: str,
) -> tuple[str, list]:
    """Recupera contexto RAG, invoca LLM y verifica fidelidad.

    Fix Tarea 1: bypass de caché semántica para preguntas de identidad.
    Evita que el caché devuelva respuestas de sesiones anteriores cuando
    el usuario pregunta '¿Quién eres?'.

    Fix Paso 2: solo se cachea si fidelity_score >= _CACHE_MIN_SCORE (0.55).
    Evita que respuestas genéricas del LLM queden guardadas y se sirvan
    como respuesta "oficial" en sesiones futuras con similitud alta.
    """
    # Bypass caché para preguntas de identidad
    input_lower = user_input.lower()
    is_identity = any(kw in input_lower for kw in _IDENTITY_KEYWORDS)

    if not is_identity:
        cached = cache_lookup(user_input)
        if cached is not None:
            log.debug("Respuesta servida desde caché semántica")
            return cached, []

    memory_context = get_selective_context(route)
    context_text, source_docs = retrieve_context(user_input, vectordb)

    chat_history_text = "\n".join(
        f"{'Usuario' if isinstance(m, HumanMessage) else 'Lautaro'}: {m.content}"
        for m in chat_history
    ) or "(sin historial previo)"

    chain = build_chain(QA_SYSTEM_PROMPT, memory_context)
    answer = chain.invoke({
        "question":     user_input,
        "context":      context_text,
        "chat_history": chat_history_text,
    })

    is_faithful, score = verify_fidelity(answer, source_docs, question=user_input)
    if not is_faithful:
        log.warning(
            "Respuesta bloqueada por fidelidad (score=%.3f): %s",
            score, user_input[:60],
        )
        return NO_EVIDENCE_MSG, source_docs

    # Fix Paso 2: guardar en caché SOLO si score supera el umbral mínimo.
    # Respuestas genéricas pasan el bloqueo de fidelidad pero no llegan
    # a cachearse, forzando recalculo en la próxima sesión.
    if not is_identity and score >= _CACHE_MIN_SCORE:
        log.debug("Guardando en caché (score=%.3f >= %.2f)", score, _CACHE_MIN_SCORE)
        cache_save(user_input, answer)
    elif not is_identity:
        log.debug("Respuesta NO cacheada (score=%.3f < %.2f)", score, _CACHE_MIN_SCORE)

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
        exit            → _decide_exit
        tool_list_files → _handle_list_files (con detección de conteo)
        tool            → dispatch_tool
        memory          → _decide_memory (TERMINAL — fix 6A: nunca cae a RAG)
        unsupported     → mensaje directo (sin LLM ni vectorstore)
        resto           → _decide_rag
    """
    if route == "exit":
        return _decide_exit(chat_history)

    # Fix Tarea 1: tool_list_files tiene su propio handler para detectar
    # si el usuario quiere conteo ('cuántos') o lista completa.
    if route == "tool_list_files":
        return _handle_list_files(user_input), []

    if route in TOOLS:
        return dispatch_tool(route, user_input), []

    if route == "memory":
        # Fix 6A: _decide_memory siempre retorna str — carril memory es terminal.
        # No hay fallback a RAG desde aquí: si la pregunta llega con route=memory,
        # memory responde (aunque sea con 'no encontré').
        answer = _decide_memory(user_input)
        return answer, []

    # Carril unsupported: consulta fuera del alcance del agente.
    # No se toca el vectorstore ni el LLM — respuesta instantánea.
    if route == "unsupported":
        log.debug("Carril unsupported — respondiendo sin LLM")
        return _UNSUPPORTED_MSG, []

    return _decide_rag(user_input, vectordb, chat_history, route=route)
