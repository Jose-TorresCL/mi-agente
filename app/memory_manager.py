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

Anotaciones MemoryType (8D):
  Cada función pública indica qué capa de memoria accede.
  Ver app.schemas.MemoryType para la definición del enum.

Fix N1-MM:
  detect_memory_intents ahora usa _normalize() importada desde app.text_utils.
  Mismo normalizador que Capa 1: minúsculas + sin tildes + espacios comprimidos.
  Eliminados pares duplicados (con/sin tilde) de _INTENT_SIGNALS.

Nivel 4 (este commit):
  _classify_session_state: patrones momentum y recovering basados en
  last_ep.exitoso. Permiten que el briefing de arranque use la memoria
  episódica para contextualizar el estado — sin LLM.
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
    save_project_fact,
    add_task,
    update_task_status,
    update_work_state,
    update_session_goal,
    save_episode,
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
    """Compone contexto de múltiples capas de memoria."""
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

    momentum y recovering se evalúan después de blocked para no interferir
    con bloqueos activos, pero antes de overloaded/stale para que la señal
    episódica tenga peso cuando la sesión está relativamente limpia.
    """
    blockers   = ws.get("current_blockers", [])
    all_open   = task_classes["all_open"]
    stale_list = task_classes["stale"]
    foco       = ws.get("current_focus", "").strip()

    if blockers:
        return "blocked"

    # Nivel 4: usar campo exitoso del episodio anterior
    if last_ep is not None:
        ep_exitoso = last_ep.get("exitoso", "unmarked")
        if ep_exitoso is True or ep_exitoso == "true":
            if foco:  # solo momentum si hay foco activo
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


def get_session_briefing() -> dict:
    """Paso D: construye el estado completo de arranque de sesión.

    Reúne datos de las 3 capas de memoria y los clasifica sin LLM.
    Diseñado para ejecutarse en < 200ms (solo lectura de JSON).

    Returns dict con:
      foco           → str: foco actual de work_state
      session_goal   → str: objetivo específico de esta sesión (puede estar vacío)
      next_step      → str: siguiente paso registrado
      last_completed → str: último completado
      blockers       → list[str]: bloqueos activos
      tasks          → dict: clasificación fresh/aging/stale/all_open
      last_episode   → dict | None: episodio anterior con todos sus campos
                        incluyendo exitoso y carril_dominante (Paso A)
      session_state  → str: patrón clasificado
      suggestion     → str: acción concreta sugerida según el patrón
    """
    ws         = load_work_state()
    tasks_data = load_tasks()
    tasks      = tasks_data.get("tasks", []) if tasks_data else []
    last_ep    = load_last_episode()  # Paso A: incluye exitoso + carril_dominante

    task_classes = _classify_tasks(tasks)
    state        = _classify_session_state(ws, task_classes, last_ep)

    suggestion = _build_suggestion(state, ws, task_classes)

    return {
        "foco":           ws.get("current_focus", ""),
        "session_goal":   ws.get("session_goal", ""),
        "next_step":      ws.get("next_step", ""),
        "last_completed": ws.get("last_completed", ""),
        "blockers":       ws.get("current_blockers", []),
        "tasks":          task_classes,
        "last_episode":   last_ep,
        "session_state":  state,
        "suggestion":     suggestion,
    }


def _build_suggestion(state: str, ws: dict, task_classes: dict) -> str:
    """Construye la propuesta de acción concreta para el estado clasificado."""
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

    # drifting
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
    """Paso B: guarda el objetivo específico de esta sesión.

    Wrapper de memory_manager → memory_store para mantener
    la arquitectura de capas. Nunca llama a memory_store directamente
    desde fuera de este módulo.
    """
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
