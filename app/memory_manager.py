"""Guardián de la capa de memoria — MemoryManager.

Punto único de acceso a memoria estructurada para el resto del sistema.
Ningún módulo externo debe llamar a memory_store directamente
para operaciones de negocio — solo memory_manager lo hace.

Arquitectura de capas:
  chat_core / tools / router
        ↓
  memory_manager   ← este módulo (reglas + selección)
        ↓
  memory_store     (I/O puro — lectura/escritura JSON)
        ↓
  storage/*.json

memory_store.py sigue siendo la capa de persistencia.
memory_manager.py es la capa de servicio.

Interfaces públicas:

  Lectura de contexto:
    get_full_context()                → perfil + facts + work_state + tareas + episodio
    get_selective_context(route)      → subconjunto según carril del router (ADR-004)
    get_context_for(intent_type)      → contexto exacto según tipo de consulta de memoria
    get_working_context()             → solo work_state + tareas pendientes
    get_semantic_context()            → solo project_facts + perfil
    get_episodic_context()            → solo episodio anterior

  Composición multi-capa (R4-B):
    detect_memory_intents(question)   → lista de tipos detectados en la pregunta
    get_composed_context(intents)     → contexto combinado de múltiples capas
                                        (concatenación pura — sin LLM).
                                        La síntesis LLM ocurre en intelligence.py
                                        (_synthesize_memory_answer) que recibe este
                                        texto como contexto y lo procesa con el
                                        MEMORY_SYNTHESIS_PROMPT oficial + historial.

  Lectura directa:
    get_profile()           → dict del perfil
    get_project_facts()     → dict de hechos
    get_tasks()             → dict con lista de tareas
    get_work_state()        → dict del estado de trabajo
    get_last_episode()      → dict del último episodio | None

  Session Intelligence (Paso D):
    get_session_briefing()  → dict con estado clasificado para mostrar al arranque

  Escritura con reglas:
    save_fact(key, value)           → bool (False si key/value vacíos o valor duplicado)
    update_state(field, value)      → None
    set_session_goal(goal)          → None  (Paso B)
    create_task(title, priority)    → str con ID generado (o ID existente si título duplicado)
    complete_task(task_id)          → None
    record_episode(summary, turns)  → None

  Flujo automático de memoria episódica:
    suggest_new_tasks(episodes)     → list[dict] de tareas sugeridas a partir de episodios
    add_task_to_memory(task)        → str con el ID de la tarea creada/existente
    main_memory_flow()              → int con cantidad de tareas nuevas registradas

Anotaciones MemoryType (8D):
  Cada función pública indica qué capa de memoria accede.
  Ver app.schemas.MemoryType para la definición del enum.

Fix N1-MM:
  detect_memory_intents ahora usa _normalize() importada desde app.text_utils.
  Mismo normalizador que Capa 1: minúsculas + sin tildes + espacios comprimidos.
  Eliminados pares duplicados (con/sin tilde) de _INTENT_SIGNALS.

Fix suggest_new_tasks:
  suggest_new_tasks ahora aplica _normalize(summary) antes de buscar señales
  de acción. Sin este fix, resúmenes sin tildes (frecuentes en modelos locales
  cuantizados) silenciaban todo el flujo episódico sin error visible.

Fix _days_since_iso:
  Eliminada closure _days_since_iso duplicada dentro de get_session_briefing.
  Se reutiliza _days_since() de nivel módulo, que tiene lógica idéntica.

Nivel 4 (este commit):
  _classify_session_state: patrones momentum y recovering basados en
  last_ep.exitoso. Permiten que el briefing de arranque use la memoria
  episódica para contextualizar el estado — sin LLM.

  Edge case exitoso: si last_ep["exitoso"] es None, ausente o "unmarked",
  ninguna rama episódica se activa y el estado cae a reglas de tareas
  (overloaded, stale, focused, drifting). Este comportamiento es intencional
  — se trata como "sin señal episódica disponible".

Sugerencia contextual por carril dominante:
  _get_smart_suggestion() cruza session_state + ep_carril del episodio
  anterior para generar sugerencias más específicas que el texto genérico.
  Tabla _SUGGESTION_BY_CARRIL cubre 10 combinaciones frecuentes.
  Fallback al comportamiento anterior si ep_carril no está en la tabla.

Detección de sesión retomada:
  _is_retomada(last_ep): devuelve True si el último episodio tiene fecha
  de hoy. get_session_briefing() expone el campo 'es_retomada' para que
  chat_ui.py active el modo compacto sin duplicar lógica de fechas.
"""
from __future__ import annotations

from datetime import datetime
from app.logger import get_logger
from app.text_utils import _normalize
from app.memory_store import (
    load_profile,
    load_project_facts,
    load_tasks,
    load_work_state,
    load_last_episode,
    load_episodes,
    save_project_fact,
    add_task,
    update_task_status,
    update_work_state,
    update_session_goal,
    save_episode,
    validate_memory_file,
)
from app.memory_context import build_memory_context

log = get_logger(__name__)


# ─────────────────────────────────────────────
# R4-B: Señales de co-ocurrencia por tipo
# Fix N1-MM: solo versiones SIN tilde — _normalize() equipara las variantes.
# ─────────────────────────────────────────────

_INTENT_SIGNALS: dict[str, list[str]] = {
    "profile": [
        "mi perfil", "como soy", "quien soy",
        "mi nombre", "mi nivel", "mi estilo",
    ],
    "work_state": [
        "foco actual", "foco", "siguiente paso",
        "en que estoy", "que estoy haciendo",
        "estado actual", "que hago", "en que vamos",
        "que sigue", "en que quedamos",
    ],
    "tasks": [
        "tareas", "pendientes", "tarea",
        "que tengo", "que debo",
    ],
    "project_facts": [
        "fase del proyecto", "fase actual",
        "hechos del proyecto", "nombre del proyecto",
        "datos del proyecto",
    ],
    "episode": [
        "sesion anterior", "ultima sesion",
        "que aprendi", "que trabajamos",
        "que avance", "la semana pasada", "ayer",
        "antes", "historial", "aprendimos",
    ],
}

_INTENT_ORDER = ["episode", "work_state", "tasks", "project_facts", "profile"]


def detect_memory_intents(question: str) -> list[str]:
    """Detecta todos los tipos de memoria relevantes para una pregunta."""
    q = _normalize(question)
    detected = set()
    for intent_type, signals in _INTENT_SIGNALS.items():
        if any(signal in q for signal in signals):
            detected.add(intent_type)
    return [t for t in _INTENT_ORDER if t in detected]


def get_composed_context(intents: list[str]) -> str:
    """Compone contexto de múltiples capas de memoria (concatenación pura).

    Recorre cada intent, obtiene el texto de su capa y lo une en secciones
    etiquetadas. No llama al LLM — es una función pura de recuperación.

    La síntesis LLM sobre este contexto ocurre en intelligence.py:
      _decide_memory() → needs_llm=True → _synthesize_memory_answer()
    que usa MEMORY_SYNTHESIS_PROMPT + historial de conversación.

    Args:
        intents: Lista de tipos de memoria a componer
                 (ej. ['tasks', 'work_state']).

    Returns:
        Texto con secciones etiquetadas listo para pasar al sintetizador.
        Cadena vacía si ninguna capa tiene contenido.
    """
    _LABELS = {
        "profile":       "Perfil del usuario",
        "work_state":    "Estado de trabajo",
        "tasks":         "Tareas pendientes",
        "project_facts": "Hechos del proyecto",
        "episode":       "Sesiones anteriores",
    }

    sections: list[str] = []
    for intent_type in intents:
        content = get_context_for(intent_type)
        if content and content.strip():
            label = _LABELS.get(intent_type, intent_type)
            sections.append(f"=== {label} ===\n{content.strip()}")

    return "\n\n".join(sections)


# ─────────────────────────────────────────────
# Lectura de contexto
# ─────────────────────────────────────────────

def get_full_context() -> str:
    return build_memory_context()


def get_context_for(intent_type: str) -> str:
    if intent_type in ("profile", "project_facts"):
        return get_semantic_context()
    if intent_type in ("work_state", "tasks"):
        return get_working_context()
    if intent_type == "episode":
        return get_episodic_context()
    log.debug("get_context_for: tipo desconocido '%s' — devolviendo vacío", intent_type)
    return ""


def get_selective_context(route: str) -> str:
    if route == "rag":
        profile = load_profile()
        if not profile:
            return ""
        lines = []
        name    = profile.get("user_name", "")
        level   = profile.get("user_level", "")
        project = profile.get("project_type", "")
        if name:    lines.append(f"Usuario: {name}")
        if level:   lines.append(f"Nivel: {level}")
        if project: lines.append(f"Proyecto: {project}")
        return "\n".join(lines)

    if route == "estado":
        return get_working_context()

    if route == "memoria":
        parts = [get_semantic_context(), get_episodic_context()]
        return "\n".join(p for p in parts if p)

    return get_full_context()


def get_working_context() -> str:
    ws         = load_work_state()
    tasks_data = load_tasks()
    tasks      = tasks_data.get("tasks", []) if tasks_data else []
    pending    = [t for t in tasks if t.get("status") not in ("done", "completed")][:3]

    lines: list[str] = []
    if ws:
        foco      = ws.get("current_focus", "")
        siguiente = ws.get("next_step", "")
        ultimo    = ws.get("last_completed", "")
        if foco:      lines.append(f"Foco actual: {foco}")
        if siguiente: lines.append(f"Siguiente paso: {siguiente}")
        if ultimo:    lines.append(f"Último completado: {ultimo}")
        blockers = ws.get("current_blockers", [])
        if blockers:
            lines.append(f"Bloqueos: {', '.join(blockers)}")

    if pending:
        lines.append("Tareas pendientes:")
        for t in pending:
            lines.append(
                f"  - [{t.get('id', '?')}] {t.get('title', '')} "
                f"({t.get('priority', 'medium')})"
            )

    return "\n".join(lines)


def get_semantic_context() -> str:
    profile = load_profile()
    facts   = load_project_facts()

    lines: list[str] = []
    if profile:
        name  = profile.get("user_name", "")
        level = profile.get("user_level", "")
        if name or level:
            lines.append(f"Usuario: {name} ({level})")

    if facts:
        lines.append("Hechos del proyecto:")
        for k, v in facts.items():
            lines.append(f"  - {k}: {v}")

    return "\n".join(lines)


def get_episodic_context() -> str:
    ep = load_last_episode()
    if not ep:
        return ""
    return (
        f"Sesión anterior ({ep.get('date', '')} {ep.get('time', '')}, "
        f"{ep.get('turns', 0)} turnos): {ep.get('summary', '')}"
    )


# ─────────────────────────────────────────────
# Session Intelligence — Paso D
# ─────────────────────────────────────────────

def _days_since(iso_date: str) -> int | None:
    """Calcula días desde una fecha ISO. Devuelve None si no puede parsear."""
    try:
        dt = datetime.fromisoformat(iso_date)
        return (datetime.now() - dt).days
    except (ValueError, TypeError):
        return None


def _is_retomada(last_ep: dict | None) -> bool:
    """True si ya existe un episodio guardado con fecha de hoy.

    Indica que esta no es la primera apertura del día sino una retomada.
    Usado por get_session_briefing() para activar el modo compacto en chat_ui.

    Args:
        last_ep: dict del último episodio o None si no hay episodios.

    Returns:
        True si last_ep tiene campo 'date' igual a la fecha de hoy.
        False en cualquier otro caso (primer arranque, sin episodios, error de parseo).

    Never raises.
    """
    if not last_ep:
        return False
    ep_date = last_ep.get("date", "")
    try:
        return datetime.fromisoformat(ep_date).date() == datetime.now().date()
    except (ValueError, TypeError):
        return False


def _classify_tasks(tasks: list[dict]) -> dict:
    """Clasifica tareas abiertas en fresh / aging / stale según updated_at o created_at."""
    open_tasks = [t for t in tasks if t.get("status") not in ("done", "completed")]
    fresh, aging, stale = [], [], []
    for t in open_tasks:
        ref_date = t.get("updated_at") or t.get("created_at", "")
        days = _days_since(ref_date)
        if days is None:
            aging.append(t)
        elif days <= 2:
            fresh.append(t)
        elif days <= 7:
            aging.append(t)
        else:
            stale.append(t)
    return {"fresh": fresh, "aging": aging, "stale": stale, "all_open": open_tasks}


def _classify_session_state(
    ws: dict,
    task_classes: dict,
    last_ep: dict | None,
) -> str:
    """Determina el patrón de sesión actual. Sin LLM — solo reglas sobre JSON.

    Patrones (en orden de prioridad):
      blocked    → hay bloqueos activos
      momentum   → sesión anterior exitosa + sin bloqueos + foco activo
      recovering → sesión anterior no exitosa + sin bloqueos
      overloaded → 5+ tareas abiertas
      stale      → hay tareas sin tocar en >7 días
      focused    → foco definido y pocas tareas
      drifting   → estado ambiguo, sin foco claro
    """
    blockers   = ws.get("current_blockers", [])
    all_open   = task_classes["all_open"]
    stale_list = task_classes["stale"]
    foco       = ws.get("current_focus", "").strip()

    if blockers:
        return "blocked"

    if last_ep is not None:
        ep_exitoso = last_ep.get("exitoso", "unmarked")
        if ep_exitoso is True or ep_exitoso == "true":
            if foco:
                return "momentum"
        elif ep_exitoso is False or ep_exitoso == "false":
            return "recovering"

    if len(all_open) >= 5:
        return "overloaded"
    if stale_list:
        return "stale"
    if foco and len(all_open) <= 3:
        return "focused"
    return "drifting"


# ─────────────────────────────────────────────
# Sugerencia contextual por carril dominante
# ─────────────────────────────────────────────

_SUGGESTION_BY_CARRIL: dict[tuple[str, str], str] = {
    ("momentum", "rag"):                    "Ayer en modo consulta (RAG). ¿Seguimos explorando la arquitectura o pasamos a acción?",
    ("momentum", "tool_create_task"):       "Ayer creaste tareas. Tenés pendientes abiertas. ¿Las revisamos o cerramos una?",
    ("momentum", "tool_complete_task"):     "Ayer completaste tareas. ¿Seguimos cerrando o abrimos algo nuevo?",
    ("momentum", "memory:tasks"):           "Ayer consultaste tareas varias veces. ¿Qué está estancado hoy?",
    ("momentum", "memory:work_state"):      "Ayer actualizaste el foco varias veces. ¿Sigue siendo el mismo hoy?",
    ("momentum", "tool_update_work_state"): "Ayer reorientaste el trabajo. ¿Cuál es el foco de hoy?",
    ("momentum", "episode"):                "Ayer revisaste el historial. ¿Qué aprendizaje querés aplicar hoy?",
    ("stale",    "rag"):                    "Tenés tareas estancadas. ¿Revisamos una antes de seguir en modo consulta?",
    ("stale",    "tool_create_task"):       "Creaste tareas pero hay estancadas. ¿Limpiamos la lista primero?",
    ("recovering", "rag"):                  "La sesión anterior no terminó bien. ¿Retomamos desde donde quedaste en el código?",
}


def _get_smart_suggestion(state: str, ep_carril: str, fallback: str) -> str:
    """Devuelve sugerencia contextual cruzando session_state y carril dominante.

    Busca el par (state, ep_carril) en _SUGGESTION_BY_CARRIL.
    Si no está mapeado, devuelve fallback (comportamiento anterior intacto).

    Never raises.
    """
    return _SUGGESTION_BY_CARRIL.get((state, ep_carril), fallback)


def get_session_briefing() -> dict:
    """Paso D: construye el estado completo de arranque de sesión.

    Reúne datos de las 3 capas de memoria y los clasifica sin LLM.
    Diseñado para ejecutarse en < 200ms (solo lectura de JSON).

    Returns dict con:
      foco           → str
      session_goal   → str
      next_step      → str
      last_completed → str
      blockers       → list[str]
      tasks          → dict: fresh/aging/stale/all_open
      last_episode   → dict | None
      session_state  → str
      suggestion     → str
      freshness_score→ float 0.0-1.0
      es_retomada    → bool: True si ya hay episodio de hoy (segunda+ apertura)
    """
    ws         = load_work_state()
    tasks_data = load_tasks()
    tasks      = tasks_data.get("tasks", []) if tasks_data else []
    last_ep    = load_last_episode()

    task_classes = _classify_tasks(tasks)
    state        = _classify_session_state(ws, task_classes, last_ep)
    es_retomada  = _is_retomada(last_ep)

    ep_carril  = last_ep.get("carril_dominante", "unknown") if last_ep else "unknown"
    fallback   = _build_suggestion(state, ws, task_classes)
    suggestion = _get_smart_suggestion(state, ep_carril, fallback)

    freshness = 0.0
    last_ep_date = last_ep.get("date") if last_ep else None
    days = _days_since(last_ep_date)
    if days is not None:
        freshness = max(0.0, 1.0 - min(days, 30) / 30.0)
    else:
        task_dates = [t.get("updated_at") or t.get("created_at") for t in tasks]
        task_days = [d for d in (_days_since(d) for d in task_dates) if d is not None]
        if task_days:
            freshness = max(0.0, 1.0 - min(task_days) / 30.0)

    return {
        "foco":            ws.get("current_focus", ""),
        "session_goal":    ws.get("session_goal", ""),
        "next_step":       ws.get("next_step", ""),
        "last_completed":  ws.get("last_completed", ""),
        "blockers":        ws.get("current_blockers", []),
        "tasks":           task_classes,
        "last_episode":    last_ep,
        "session_state":   state,
        "suggestion":      suggestion,
        "freshness_score": round(freshness, 3),
        "es_retomada":     es_retomada,
    }


def _build_suggestion(state: str, ws: dict, task_classes: dict) -> str:
    """Construye la propuesta de acción concreta para el estado clasificado.

    Fallback genérico usado cuando no hay carril dominante disponible
    o el par (state, carril) no está en _SUGGESTION_BY_CARRIL.
    """
    if state == "blocked":
        blocker = ws["current_blockers"][0]
        return f"¿Empezamos por desbloquear '{blocker}'?"

    if state == "momentum":
        next_step = ws.get("next_step", "")
        if next_step:
            return f"Buena racha. ¿Seguimos con: '{next_step}'?"
        session_goal = ws.get("session_goal", "")
        if session_goal:
            return f"Buena racha. Objetivo de hoy: '{session_goal}'. ¿Comenzamos?"
        return "Buena racha. ¿Por dónde seguimos?"

    if state == "recovering":
        next_step = ws.get("next_step", "")
        if next_step:
            return f"La sesión anterior no se completó. ¿Retomamos con: '{next_step}'?"
        return "La sesión anterior no fue exitosa. ¿Revisamos qué quedó sin cerrar?"

    if state == "overloaded":
        all_open = task_classes["all_open"]
        oldest   = min(all_open, key=lambda t: t.get("created_at", ""), default=None)
        if oldest:
            return f"¿Cerramos o descartamos '{oldest['title']}'?"
        return "¿Hacemos limpieza de tareas pendientes?"

    if state == "stale":
        stale    = task_classes["stale"]
        oldest_s = min(stale, key=lambda t: t.get("updated_at") or t.get("created_at", ""), default=None)
        if oldest_s:
            return f"Tarea sin tocar hace más de 7 días: '{oldest_s['title']}' — ¿la cerramos o descartamos?"
        return "Hay tareas estancadas. ¿Las revisamos?"

    if state == "focused":
        next_step = ws.get("next_step", "")
        if next_step:
            return f"¿Arrancamos con: '{next_step}'?"
        session_goal = ws.get("session_goal", "")
        if session_goal:
            return f"Objetivo de hoy: '{session_goal}'. ¿Comenzamos?"
        return "Todo en orden. ¿Por dónde empezamos?"

    return "Foco no definido. ¿Quieres revisar el estado del proyecto o definir el objetivo de hoy?"


# ─────────────────────────────────────────────
# Lectura directa
# ─────────────────────────────────────────────

def get_profile() -> dict:             return load_profile()
def get_project_facts() -> dict:       return load_project_facts()
def get_tasks() -> dict:               return load_tasks() or {"tasks": []}
def get_work_state() -> dict:          return load_work_state()
def get_last_episode() -> dict | None: return load_last_episode()


# ─────────────────────────────────────────────
# Escritura con reglas de negocio
# ─────────────────────────────────────────────

def save_fact(key: str, value: str) -> bool:
    if not key.strip() or not value.strip():
        log.warning("save_fact rechazado: key=%r value=%r", key, value)
        return False

    existing_facts = load_project_facts()
    value_normalized = value.strip().lower()
    for existing_key, existing_value in existing_facts.items():
        existing_value_str = str(existing_value).strip().lower()
        if existing_value_str == value_normalized:
            if existing_key == key.strip():
                log.debug("save_fact omitido (ya existe igual): %s = %s", key, value)
            else:
                log.info(
                    "save_fact omitido (valor duplicado en '%s'): %s = %s",
                    existing_key, key, value,
                )
            return False

    save_project_fact(key.strip(), value.strip())
    log.debug("Hecho guardado: %s = %s", key, value)
    return True


def update_state(field: str, value: str) -> None:
    if not field.strip() or not value.strip():
        log.warning("update_state ignorado: field=%r value=%r", field, value)
        return
    update_work_state(field.strip(), value.strip())
    log.debug("work_state actualizado: %s = %s", field, value)


def set_session_goal(goal: str) -> None:
    goal = goal.strip()
    if not goal:
        log.warning("set_session_goal ignorado: goal vacío")
        return
    update_session_goal(goal)
    log.debug("session_goal actualizado: %s", goal)


def create_task(title: str, priority: str = "medium", notes: str = "") -> str:
    title    = title.strip()
    priority = priority.strip().lower()
    notes    = notes.strip()

    if not title:
        log.warning("create_task ignorado: title vacío")
        return ""

    valid_priorities = {"low", "medium", "high"}
    if priority not in valid_priorities:
        priority = "medium"

    existing_tasks   = load_tasks()
    title_normalized = title.lower()
    for task in existing_tasks.get("tasks", []):
        if (
            task.get("title", "").strip().lower() == title_normalized
            and task.get("status") not in ("done", "completed")
        ):
            log.info("create_task omitido (ya existe pendiente '%s'): %s", task["id"], title)
            return task["id"]

    task_id = add_task(title=title, priority=priority, notes=notes)
    log.debug("Tarea creada: %s — %s", task_id, title)
    return task_id


def complete_task(task_id: str) -> None:
    if not task_id.strip():
        log.warning("complete_task ignorado: task_id vacío")
        return
    update_task_status(task_id.strip(), "completed")
    log.debug("Tarea completada: %s", task_id)


def record_episode(summary: str, turns: int) -> None:
    if not summary.strip():
        log.warning("record_episode ignorado: summary vacío")
        return
    save_episode(summary=summary.strip(), turns=turns)
    log.debug("Episodio registrado: %d turnos", turns)


def create_task_from_episode(episode: dict) -> dict:
    summary = str(episode.get("summary", "")).strip()
    if not summary:
        return {}

    title = "Extraer acción de episodio"
    lower_summary = summary.lower()
    if "decisión" in lower_summary or "decisiones" in lower_summary:
        title = "Revisar decisión mencionada en episodio"
    elif "tarea" in lower_summary or "tareas" in lower_summary:
        title = "Registrar tarea detectada en episodio"

    first_sentence = summary.split(".")[0].strip()
    if first_sentence:
        title = f"{title}: {first_sentence}"
    if len(title) > 120:
        title = title[:117].rstrip() + "..."

    notes = f"Episodio {episode.get('date', '')} {episode.get('time', '')}. "
    notes += summary
    return {
        "title": title,
        "priority": "medium",
        "notes": notes,
    }


def suggest_new_tasks(episodes: list[dict]) -> list[dict]:
    new_tasks: list[dict] = []
    for episode in episodes:
        summary = _normalize(str(episode.get("summary", "")))
        if not summary:
            continue
        if "decision" in summary or "tarea" in summary or "accion" in summary:
            task = create_task_from_episode(episode)
            if task:
                new_tasks.append(task)
    return new_tasks


def add_task_to_memory(task: dict | str) -> str:
    if isinstance(task, str):
        return create_task(task)
    if not isinstance(task, dict):
        return ""
    return create_task(
        title=task.get("title", ""),
        priority=task.get("priority", "medium"),
        notes=task.get("notes", ""),
    )


def main_memory_flow() -> int:
    episodes = load_episodes()
    suggested_tasks = suggest_new_tasks(episodes)
    added = 0
    for task in suggested_tasks:
        task_id = add_task_to_memory(task)
        if task_id:
            added += 1
    log.debug("main_memory_flow: %d sugerencias de tarea procesadas", added)
    return added
