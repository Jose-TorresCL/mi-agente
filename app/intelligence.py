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

R1 — contratos internos (CERRADO):
  R1-A (schemas.py):
    - DecisionResult: TypedDict con la semántica de process_turn().
    - RagResult: TypedDict con la semántica de _decide_rag().
  R1-B (este archivo):
    - process_turn()  -> tuple[str, list]        (tipado explícito)
    - _decide_rag()   -> tuple[str, list, int, int, bool]  (tipado explícito)
  R1-C (test_architecture.py):
    - intelligence.py NO importa memory_store directamente.
  R1-D (test_architecture.py):
    - tools.py NO importa memory_store directamente.
  R1-E (test_architecture.py):
    - router.py NO importa chromadb ni langchain_chroma directamente.
  Verificar con: pytest tests/test_architecture.py -v

R2-connect — intent_type y num_docs en record_turn() (CERRADO):
  process_turn() pasa intent_type a _record_metric() en todos los carriles.
  metrics.jsonl registra ambos campos desde este commit.

R4-B — composición multi-capa de memoria (CERRADO):
  _decide_memory() ahora usa detect_memory_intents() en vez de classify_memory_query().
  Cuando la pregunta cruza dos tipos (ej: episode + work_state), ambas capas se
  abren y se compone el contexto antes de pasarlo al LLM.
  Modelo 'reactivo' (1 cajón) → modelo 'adaptativo' (N cajones).

Fix B3 — timeout síntesis subido de 10s a 30s:
  Evita WARNING 'Síntesis de memoria falló' cuando Ollama está ocupado.

Fix B4 — _format_tasks_answer distingue tareas hechas vs pendientes:
  'lista todas las tareas hechas' ya no devuelve pendientes.

Fix C1 — chat_history en _synthesize_memory_answer:
  Se pasan los últimos 3 turnos del historial de conversación al prompt
  de síntesis de memoria. Antes el LLM respondía sin saber qué se habló
  en la sesión, produciendo respuestas desconectadas del contexto.

Fix C2 — cliente LLM unificado (CERRADO):
  _synthesize_memory_answer y _decide_exit ya NO usan requests.post() directo.
  Ambas usan generate_raw() de rag_engine, que aprovecha el mismo ChatOllama
  singleton que build_chain(). Un único cliente LLM en todo el proyecto.
  Se elimina el import de 'requests' de este archivo.

R5-MoA — separación recuperador / sintetizador en _decide_memory (CERRADO):
  Aplica el patrón Mixture-of-Agents (Together AI, 2024) a escala de módulo:
  no requiere múltiples modelos — requiere múltiples roles claros.

  Antes: _decide_memory() mezclaba en un solo punto detectar intents,
  abrir cajones JSON, formatear texto y llamar al LLM. Un único punto de falla.

  Ahora:
    _retrieve_memory_context(question)     ← AGENTE RECUPERADOR
      - Detecta intents.
      - Abre cajones (profile, tasks, project_facts, work_state, episode).
      - Formatea el texto de contexto.
      - Devuelve MemoryContext (TypedDict) con {context_text, fallback, sources}.
      - No sabe nada del LLM.

    _synthesize_memory_answer(...)         ← AGENTE SINTETIZADOR
      - Recibe contexto limpio + historial.
      - Construye el prompt y llama a generate_raw().
      - No sabe nada de JSON ni de qué cajón se abrió.

    _decide_memory(question, chat_history) ← ORQUESTADOR
      - Llama al recuperador, obtiene MemoryContext.
      - Si el contexto está vacío devuelve fallback directo sin tocar el LLM.
      - Si el tipo es profile o tasks (estructurado), formatea sin LLM.
      - Si necesita síntesis, llama al sintetizador con el contexto limpio.

  Beneficio: agregar un sexto tipo de memoria (ej: 'rules') solo requiere
  tocar _retrieve_memory_context(). El sintetizador no cambia.
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
from app.prompts import QA_SYSTEM_PROMPT
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
# TypedDict del resultado de recuperación de memoria (R5-MoA)
# ───────────────────────────────────────────────

class MemoryContext(TypedDict):
    """Contrato de salida del AGENTE RECUPERADOR (_retrieve_memory_context).

    context_text : texto plano con los datos recuperados de los cajones JSON.
                   Listo para inyectar en el prompt del sintetizador.
    fallback     : respuesta estructurada (sin LLM) que se usa si el
                   sintetizador falla o si el tipo no necesita LLM
                   (por ejemplo, profile y tasks).
    sources      : lista de tipos de memoria abiertos. Útil para logging
                   y para que el orquestador decida si necesita LLM.
    needs_llm    : True si la respuesta requiere síntesis LLM.
                   False si el fallback estructurado es suficiente.
    """
    context_text: str
    fallback: str
    sources: list[str]
    needs_llm: bool


# ───────────────────────────────────────────────
# Helpers de formato (sin LLM)
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
    """Fix B4: distingue tareas hechas vs pendientes según keywords en la pregunta."""
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
# R5-MoA — AGENTE RECUPERADOR
# ───────────────────────────────────────────────

def _retrieve_memory_context(question: str, intents: list[str]) -> MemoryContext:
    """AGENTE RECUPERADOR (R5-MoA): abre cajones de memoria y devuelve contexto limpio.

    No sabe nada del LLM. Solo recupera, formatea y empaqueta.
    El orquestador (_decide_memory) decide si enviar el resultado al
    sintetizador o devolver el fallback directamente.

    Args:
        question: pregunta original del usuario.
        intents:  lista de tipos de memoria detectados (no vacía).

    Returns:
        MemoryContext con context_text, fallback, sources y needs_llm.
    """
    # ─── Multi-capa: si hay más de un intent, composición de cajones ───
    if len(intents) > 1:
        composed = get_composed_context(intents)
        if not composed.strip():
            return MemoryContext(
                context_text="",
                fallback=_MEMORY_NOT_FOUND_MSG,
                sources=intents,
                needs_llm=False,
            )
        return MemoryContext(
            context_text=composed,
            fallback=f"Información de memoria:\n{composed}",
            sources=intents,
            needs_llm=True,
        )

    kind = intents[0]

    # ─── profile: estructurado, sin LLM ───
    if kind == "profile":
        p = get_profile()
        if not p:
            return MemoryContext(
                context_text="",
                fallback="No encontré información de perfil.",
                sources=["profile"],
                needs_llm=False,
            )
        return MemoryContext(
            context_text="",  # profile usa fallback directo
            fallback=_format_profile_answer(p),
            sources=["profile"],
            needs_llm=False,
        )

    # ─── tasks: estructurado, sin LLM ───
    if kind == "tasks":
        t = get_tasks()
        if not t:
            return MemoryContext(
                context_text="",
                fallback="No encontré tareas registradas.",
                sources=["tasks"],
                needs_llm=False,
            )
        return MemoryContext(
            context_text="",  # tasks usa fallback directo
            fallback=_format_tasks_answer(t, question=question),
            sources=["tasks"],
            needs_llm=False,
        )

    # ─── project_facts: texto plano, necesita síntesis LLM ───
    if kind == "project_facts":
        f = get_project_facts()
        if not f:
            return MemoryContext(
                context_text="",
                fallback="No encontré hechos del proyecto.",
                sources=["project_facts"],
                needs_llm=False,
            )
        context_text = "\n".join(f"- {k}: {v}" for k, v in f.items())
        return MemoryContext(
            context_text=context_text,
            fallback="**Hechos del proyecto:**\n" + context_text,
            sources=["project_facts"],
            needs_llm=True,
        )

    # ─── work_state: texto plano, necesita síntesis LLM ───
    if kind == "work_state":
        w = get_work_state()
        if not w:
            return MemoryContext(
                context_text="",
                fallback="No encontré estado de trabajo.",
                sources=["work_state"],
                needs_llm=False,
            )
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
        return MemoryContext(
            context_text=context_text,
            fallback="**Estado de trabajo:**\n" + context_text,
            sources=["work_state"],
            needs_llm=True,
        )

    # ─── episode: recupera desde Chroma, necesita síntesis LLM ───
    if kind == "episode":
        episodes: list[dict] = []
        try:
            from app.episode_store import search_episodes
            episodes = search_episodes(question, k=3)
        except Exception as exc:
            log.warning("[episode] search_episodes falló: %s", exc)

        _EMPTY_MARKER = "Resumen no disponible"
        episodes_with_content = [
            ep for ep in episodes
            if _EMPTY_MARKER not in ep.get("summary", "")
        ]

        if episodes_with_content:
            context_text = _format_episodes_context(episodes_with_content)
            return MemoryContext(
                context_text=context_text,
                fallback=f"Sesiones encontradas:\n{context_text}",
                sources=["episode"],
                needs_llm=True,
            )

        # Fallback: JSON plano
        json_context = get_context_for("episode")
        if json_context:
            return MemoryContext(
                context_text="",
                fallback=json_context,
                sources=["episode"],
                needs_llm=False,
            )
        return MemoryContext(
            context_text="",
            fallback="No encontré sesiones anteriores registradas con información relevante.",
            sources=["episode"],
            needs_llm=False,
        )

    # tipo desconocido
    log.debug("_retrieve_memory_context: tipo no reconocido '%s'", kind)
    return MemoryContext(
        context_text="",
        fallback=_MEMORY_NOT_FOUND_MSG,
        sources=[kind],
        needs_llm=False,
    )


# ───────────────────────────────────────────────
# R5-MoA — AGENTE SINTETIZADOR
# ───────────────────────────────────────────────

def _synthesize_memory_answer(
    question: str,
    context_text: str,
    fallback: str,
    chat_history: list | None = None,
) -> str:
    """AGENTE SINTETIZADOR (R5-MoA): recibe contexto limpio y genera la respuesta.

    No sabe nada de JSON ni de qué cajón se abrió.
    Solo construye el prompt, llama a generate_raw() y devuelve texto.

    Fix C1: inyecta últimos turnos del historial en el prompt.
    Fix C2: usa generate_raw() (ChatOllama singleton), no requests.post().
    """
    history_snippet = _build_history_snippet(chat_history)
    history_block = (
        f"\nConversación reciente (contexto de la sesión):\n{history_snippet}\n"
        if history_snippet else ""
    )

    prompt = (
        "Eres Lautaro, asistente técnico local del proyecto 'mi-agente'.\n"
        "Tienes acceso a los siguientes datos del proyecto:\n\n"
        f"{context_text}\n"
        f"{history_block}\n"
        "Responde la siguiente pregunta de forma natural, clara y concisa "
        "en español. No listes todos los campos — sintetiza lo más relevante "
        "para la pregunta, considerando el contexto de la conversación reciente "
        "si es relevante. Máximo 4 oraciones.\n\n"
        f"Pregunta: {question}\n\nRespuesta:"
    )

    answer = generate_raw(
        prompt,
        temperature=0.3,
        num_predict=150,
        timeout=_MEMORY_SYNTHESIS_TIMEOUT,
    )
    if answer:
        return answer

    log.warning("_synthesize_memory_answer: generate_raw devolvió None, usando fallback")
    return fallback


# ───────────────────────────────────────────────
# R5-MoA — ORQUESTADOR de memoria
# ───────────────────────────────────────────────

def _decide_memory(question: str, chat_history: list | None = None) -> str:
    """ORQUESTADOR (R5-MoA): coordina recuperador y sintetizador.

    Flujo:
      1. Detecta intents (tipos de memoria).
      2. Llama al recuperador para obtener MemoryContext.
      3. Si no hay contexto ni necesita LLM, devuelve fallback directo.
      4. Si needs_llm=False (profile, tasks), devuelve fallback estructurado.
      5. Si needs_llm=True, delega al sintetizador con el contexto limpio.
    """
    intents = detect_memory_intents(question)
    log.debug("R5-MoA: intents detectados=%s para '%s'", intents, question[:60])

    if not intents:
        log.debug("memory: ningún tipo detectado — devolviendo not-found")
        return _MEMORY_NOT_FOUND_MSG

    # PASO 1: recuperador obtiene el contexto
    mem_ctx: MemoryContext = _retrieve_memory_context(question, intents)
    log.debug(
        "R5-MoA: recuperador terminó [sources=%s needs_llm=%s ctx_len=%d]",
        mem_ctx["sources"], mem_ctx["needs_llm"], len(mem_ctx["context_text"]),
    )

    # PASO 2: orquestador decide si necesita sintetizador
    if not mem_ctx["needs_llm"]:
        # profile, tasks, episodio vacío — respuesta directa sin LLM
        return mem_ctx["fallback"]

    # PASO 3: sintetizador recibe contexto limpio
    return _synthesize_memory_answer(
        question,
        mem_ctx["context_text"],
        mem_ctx["fallback"],
        chat_history=chat_history,
    )


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
# Decisores internos — otros carriles
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
    """Genera resumen episódico y señala cierre de sesión.

    Fix C2: usa generate_raw() de rag_engine en vez de requests.post() directo.
    """
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

        generated = generate_raw(
            prompt,
            temperature=0.2,
            num_predict=80,
            timeout=_EPISODE_TIMEOUT,
        )
        if generated:
            summary = generated
        else:
            log.warning("No se pudo generar resumen de sesión")

    record_episode(summary=summary, turns=turns)
    log.info("Episodio guardado correctamente (turns=%d)", turns)
    return "__EXIT__", []


def _decide_rag(
    user_input: str,
    vectordb: Any,
    chat_history: list,
    route: str,
) -> tuple[str, list, int, int, bool]:
    """Recupera contexto RAG, inyecta experiencias previas y llama al LLM."""
    input_lower = user_input.lower()
    is_identity = any(kw in input_lower for kw in _IDENTITY_KEYWORDS)

    if not is_identity:
        cached = cache_lookup(user_input)
        if cached is not None:
            log.debug("Respuesta servida desde caché semántica")
            return cached, [], 0, 0, True

    t_ret_start = time.perf_counter()
    memory_context = get_selective_context(route)
    context_text, source_docs = retrieve_context(user_input, vectordb)
    retrieval_ms = int((time.perf_counter() - t_ret_start) * 1000)

    experience_injected = False
    try:
        from app.episode_store import experience_lookup
        experience_snippet = experience_lookup(user_input)
        if experience_snippet:
            context_text = experience_snippet + "\n\n---\n\n" + context_text
            experience_injected = True
            log.debug("[8B-v2] Experiencia previa inyectada en contexto RAG")
    except Exception as exc:
        log.warning("[8B-v2] experience_lookup falló (no bloquea): %s", exc)

    chat_history_text = "\n".join(
        f"{'Usuario' if isinstance(m, HumanMessage) else 'Lautaro'}: {m.content}"
        for m in chat_history
    ) or "(sin historial previo)"

    t_llm_start = time.perf_counter()
    chain = build_chain(QA_SYSTEM_PROMPT, memory_context)
    answer = chain.invoke({
        "question":     user_input,
        "context":      context_text,
        "chat_history": chat_history_text,
    })
    llm_ms = int((time.perf_counter() - t_llm_start) * 1000)

    is_faithful, score = verify_fidelity(answer, source_docs, question=user_input)
    if not is_faithful:
        log.warning(
            "Respuesta bloqueada por fidelidad (score=%.3f): %s",
            score, user_input[:60],
        )
        return NO_EVIDENCE_MSG, source_docs, retrieval_ms, llm_ms, False

    can_cache = not is_identity and not experience_injected and score >= _CACHE_MIN_SCORE
    if can_cache:
        log.debug("Guardando en caché (score=%.3f >= %.2f)", score, _CACHE_MIN_SCORE)
        cache_save(user_input, answer)
    elif not is_identity:
        reason = "con inyección episódica" if experience_injected else f"score={score:.3f} < {_CACHE_MIN_SCORE}"
        log.debug("Respuesta NO cacheada (%s)", reason)

    return answer, source_docs, retrieval_ms, llm_ms, False


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
        _record_metric(
            route=route,
            intent_type=route,
            llm_ms=int((time.perf_counter() - t0) * 1000),
        )
        return answer, []

    if route == "memory":
        t0 = time.perf_counter()
        intents = detect_memory_intents(user_input)
        memory_intent = intents[0] if intents else "memory_query"
        if len(intents) > 1:
            memory_intent = "multi:" + "+".join(intents)
        answer = _decide_memory(user_input, chat_history=chat_history)
        _record_metric(
            route=route,
            intent_type=memory_intent,
            llm_ms=int((time.perf_counter() - t0) * 1000),
            tokens_est=int(len(answer.split()) * 1.3),
        )
        return answer, []

    if route == "unsupported":
        log.debug("Carril unsupported — respondiendo sin LLM")
        _record_metric(route=route, intent_type="unsupported")
        return _UNSUPPORTED_MSG, []

    answer, source_docs, retrieval_ms, llm_ms, cached = _decide_rag(
        user_input, vectordb, chat_history, route=route
    )
    _record_metric(
        route=route,
        intent_type=route,
        retrieval_ms=retrieval_ms,
        llm_ms=llm_ms,
        tokens_est=int(len(answer.split()) * 1.3),
        cached=cached,
        num_docs=len(source_docs),
    )
    return answer, source_docs
