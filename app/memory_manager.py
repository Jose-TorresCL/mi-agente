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

  Escritura con reglas:
    save_fact(key, value)           → bool (False si key/value vacíos o valor duplicado)
    update_state(field, value)      → None
    create_task(title, priority)    → str con ID generado (o ID existente si título duplicado)
    complete_task(task_id)          → None
    record_episode(summary, turns)  → None

Anotaciones MemoryType (8D):
  Cada función pública indica qué capa de memoria accede.
  Ver app.schemas.MemoryType para la definición del enum.

Fix N1-MM:
  detect_memory_intents ahora usa _normalize() importada desde app.router.
  Mismo normalizador que Capa 1: minúsculas + sin tildes + espacios comprimidos.
  Eliminados pares duplicados (con/sin tilde) de _INTENT_SIGNALS.
"""
from __future__ import annotations

from app.logger import get_logger
from app.router import _normalize
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

# Orden de presentación cuando se componen múltiples tipos.
_INTENT_ORDER = ["episode", "work_state", "tasks", "project_facts", "profile"]


def detect_memory_intents(question: str) -> list[str]:
    """Detecta todos los tipos de memoria relevantes para una pregunta.

    R4-B: En vez de devolver UN tipo, detecta TODOS los tipos cuyas
    señales aparecen en la pregunta.

    Fix N1-MM: aplica _normalize() (mismo que Capa 1 del router) antes
    del matching. Elimina fallos por tildes, mayúsculas o espacios dobles.

    Ejemplo:
        '¿Qué aprendí la sesión pasada y cuál es el foco actual?'
        → ['episode', 'work_state']

        '¿Cuál es mi foco?'
        → ['work_state']

    Returns:
        Lista de tipos detectados en orden canónico (_INTENT_ORDER).
        Puede estar vacía. Nunca lanza excepciones.
    """
    q = _normalize(question)   # minúsculas + sin tildes + espacios comprimidos
    detected = set()
    for intent_type, signals in _INTENT_SIGNALS.items():
        if any(signal in q for signal in signals):
            detected.add(intent_type)
    return [t for t in _INTENT_ORDER if t in detected]


def get_composed_context(intents: list[str]) -> str:
    """Compone contexto de múltiples capas de memoria.

    R4-B: Ensamblador de contexto multi-capa.
    Cada sección se separa con un divisor legible para el LLM.

    Args:
        intents: Lista de tipos de memoria a componer.

    Returns:
        String de contexto listo para inyectar en prompt.
        Secciones vacías se omiten. Nunca lanza excepciones.
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
# Lectura de contexto — para inyectar en prompts
# ─────────────────────────────────────────────

def get_full_context() -> str:  # MemoryType: WORKING + SEMANTIC + EPISODIC
    """Contexto completo: perfil + facts + work_state + tareas + episodio."""
    return build_memory_context()


def get_context_for(intent_type: str) -> str:  # MemoryType: dispatch
    """Recuperación selectiva por tipo de consulta de memoria (6B)."""
    if intent_type in ("profile", "project_facts"):
        return get_semantic_context()
    if intent_type in ("work_state", "tasks"):
        return get_working_context()
    if intent_type == "episode":
        return get_episodic_context()
    log.debug("get_context_for: tipo desconocido '%s' — devolviendo vacío", intent_type)
    return ""


def get_selective_context(route: str) -> str:  # MemoryType: dispatch
    """Contexto de memoria ajustado al carril del router (ADR-004)."""
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


def get_working_context() -> str:  # MemoryType: WORKING
    """Contexto operacional: work_state + tareas pendientes."""
    ws         = load_work_state()
    tasks_data = load_tasks()
    tasks      = tasks_data.get("tasks", []) if tasks_data else []
    pending    = [t for t in tasks if t.get("status") not in ("done", "completed")][:3]

    lines: list[str] = []
    if ws:
        foco     = ws.get("current_focus", "")
        siguiente = ws.get("next_step", "")
        ultimo   = ws.get("last_completed", "")
        if foco:     lines.append(f"Foco actual: {foco}")
        if siguiente: lines.append(f"Siguiente paso: {siguiente}")
        if ultimo:   lines.append(f"Último completado: {ultimo}")
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


def get_semantic_context() -> str:  # MemoryType: SEMANTIC
    """Contexto de conocimiento estable: project_facts + perfil."""
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


def get_episodic_context() -> str:  # MemoryType: EPISODIC
    """Contexto de sesión anterior: resumen del último episodio."""
    ep = load_last_episode()
    if not ep:
        return ""
    return (
        f"Sesión anterior ({ep.get('date', '')} {ep.get('time', '')}, "
        f"{ep.get('turns', 0)} turnos): {ep.get('summary', '')}"
    )


# ─────────────────────────────────────────────
# Lectura directa
# ─────────────────────────────────────────────

def get_profile() -> dict:          return load_profile()
def get_project_facts() -> dict:    return load_project_facts()
def get_tasks() -> dict:            return load_tasks() or {"tasks": []}
def get_work_state() -> dict:       return load_work_state()
def get_last_episode() -> dict | None: return load_last_episode()


# ─────────────────────────────────────────────
# Escritura con reglas de negocio
# ─────────────────────────────────────────────

def save_fact(key: str, value: str) -> bool:  # MemoryType: SEMANTIC
    """Guarda un hecho en project_facts.

    Reglas:
    1. key y value deben ser no-vacíos.
    2. Guardia anti-duplicado: si ya existe el mismo valor, no escribe.
    3. Si la key ya existe con valor distinto, actualiza.

    Returns True si guardó, False si rechazó. Never raises.
    """
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


def update_state(field: str, value: str) -> None:  # MemoryType: WORKING
    """Actualiza un campo de work_state. Never raises."""
    if not field.strip() or not value.strip():
        log.warning("update_state ignorado: field=%r value=%r", field, value)
        return
    update_work_state(field.strip(), value.strip())
    log.debug("work_state actualizado: %s = %s", field, value)


def create_task(title: str, priority: str = "medium", notes: str = "") -> str:  # MemoryType: WORKING
    """Crea una tarea nueva y devuelve su ID.

    Reglas:
    1. title debe ser no-vacío. priority inválido → 'medium'.
    2. Anti-duplicado: mismo título pendiente → devuelve ID existente.

    Returns str con ID. Never raises.
    """
    title    = title.strip()
    priority = priority.strip().lower()
    notes    = notes.strip()

    if not title:
        log.warning("create_task ignorado: title vacío")
        return ""

    valid_priorities = {"low", "medium", "high"}
    if priority not in valid_priorities:
        priority = "medium"

    existing_tasks    = load_tasks()
    title_normalized  = title.lower()
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


def complete_task(task_id: str) -> None:  # MemoryType: WORKING
    """Marca una tarea como completada. Never raises."""
    if not task_id.strip():
        log.warning("complete_task ignorado: task_id vacío")
        return
    update_task_status(task_id.strip(), "completed")
    log.debug("Tarea completada: %s", task_id)


def record_episode(summary: str, turns: int) -> None:  # MemoryType: EPISODIC
    """Guarda el resumen de la sesión actual como episodio. Never raises."""
    if not summary.strip():
        log.warning("record_episode ignorado: summary vacío")
        return
    save_episode(summary=summary.strip(), turns=turns)
    log.debug("Episodio registrado: %d turnos", turns)
