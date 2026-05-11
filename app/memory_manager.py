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
    get_full_context()            → perfil + facts + work_state + tareas + episodio
    get_selective_context(route)  → subconjunto según carril del router (ADR-004)
    get_working_context()         → solo work_state + tareas pendientes
    get_semantic_context()        → solo project_facts + perfil
    get_episodic_context()        → solo episodio anterior

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
"""
from __future__ import annotations

from app.logger import get_logger
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
# Lectura de contexto — para inyectar en prompts
# ─────────────────────────────────────────────

def get_full_context() -> str:
    """Contexto completo: perfil + facts + work_state + tareas + episodio.

    Usar en RAG y en respuestas que necesitan todo el contexto del proyecto.
    Never raises.
    """
    return build_memory_context()


def get_selective_context(route: str) -> str:
    """Contexto de memoria ajustado al carril del router (ADR-004).

    Objetivo: reducir tokens innecesarios en el prompt según el tipo
    de pregunta, sin perder información relevante.

    Mapeo de carriles:
      "rag"     → perfil mínimo (nombre, nivel, proyecto) — ~3 líneas.
                  El LLM necesita saber quién es el usuario, no su historial
                  de trabajo, cuando busca en documentos técnicos.
      "estado"  → get_working_context() — workstate + tareas pendientes.
                  Solo lo operacional: qué se está haciendo y qué sigue.
      "memoria" → get_semantic_context() + get_episodic_context().
                  Facts del proyecto + última sesión. Sin workstate.
      cualquier → get_full_context() como fallback seguro.

    Args:
        route: Carril devuelto por route_query(). Ej: 'rag', 'estado',
               'memoria', 'save_fact', 'add_task', etc.

    Returns:
        String listo para inyectar en el system prompt.
    Never raises.
    """
    if route == "rag":
        # Solo perfil mínimo — el contexto RAG ya aporta los chunks relevantes
        profile = load_profile()
        if not profile:
            return ""
        lines = []
        name = profile.get("user_name", "")
        level = profile.get("user_level", "")
        project = profile.get("project_type", "")
        if name:
            lines.append(f"Usuario: {name}")
        if level:
            lines.append(f"Nivel: {level}")
        if project:
            lines.append(f"Proyecto: {project}")
        return "\n".join(lines)

    if route == "estado":
        # Estado operacional: qué se hace y qué sigue
        return get_working_context()

    if route == "memoria":
        # Conocimiento estable + resumen de sesión anterior
        parts = [get_semantic_context(), get_episodic_context()]
        return "\n".join(p for p in parts if p)

    # Fallback: contexto completo para cualquier otro carril
    # (herramientas, general, memory, etc.)
    return get_full_context()


def get_working_context() -> str:
    """Contexto operacional: work_state + tareas pendientes.

    Usar cuando la pregunta es sobre qué hacer ahora.
    Never raises.
    """
    ws = load_work_state()
    tasks_data = load_tasks()
    tasks = tasks_data.get("tasks", []) if tasks_data else []
    pending = [t for t in tasks if t.get("status") not in ("done", "completed")][:3]

    lines: list[str] = []
    if ws:
        foco = ws.get("current_focus", "")
        siguiente = ws.get("next_step", "")
        ultimo = ws.get("last_completed", "")
        if foco:
            lines.append(f"Foco actual: {foco}")
        if siguiente:
            lines.append(f"Siguiente paso: {siguiente}")
        if ultimo:
            lines.append(f"\u00daltimo completado: {ultimo}")
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
    """Contexto de conocimiento estable: project_facts + perfil.

    Usar cuando la pregunta es sobre el proyecto en general.
    Never raises.
    """
    profile = load_profile()
    facts = load_project_facts()

    lines: list[str] = []
    if profile:
        name = profile.get("user_name", "")
        level = profile.get("user_level", "")
        if name or level:
            lines.append(f"Usuario: {name} ({level})")

    if facts:
        lines.append("Hechos del proyecto:")
        for k, v in facts.items():
            lines.append(f"  - {k}: {v}")

    return "\n".join(lines)


def get_episodic_context() -> str:
    """Contexto de sesión anterior: resumen del último episodio.

    Devuelve string vacío si no hay episodio previo.
    Never raises.
    """
    ep = load_last_episode()
    if not ep:
        return ""
    return (
        f"Sesión anterior ({ep.get('date', '')} {ep.get('time', '')}, "
        f"{ep.get('turns', 0)} turnos): {ep.get('summary', '')}"
    )


# ─────────────────────────────────────────────
# Lectura directa — para carriles memory en chat_core
# ─────────────────────────────────────────────

def get_profile() -> dict:
    """Devuelve el perfil del usuario. Dict vacío si no existe."""
    return load_profile()


def get_project_facts() -> dict:
    """Devuelve los hechos del proyecto. Dict vacío si no existe."""
    return load_project_facts()


def get_tasks() -> dict:
    """Devuelve el dict completo de tareas. {'tasks': [...]} si no existe."""
    return load_tasks() or {"tasks": []}


def get_work_state() -> dict:
    """Devuelve el estado de trabajo. Dict vacío si no existe."""
    return load_work_state()


def get_last_episode() -> dict | None:
    """Devuelve el último episodio o None si no existe."""
    return load_last_episode()


# ─────────────────────────────────────────────
# Escritura con reglas de negocio
# ─────────────────────────────────────────────

def save_fact(key: str, value: str) -> bool:
    """Guarda un hecho en project_facts.

    Reglas:
    1. key y value deben ser no-vacíos.
    2. Guardia anti-duplicado semántico: si ya existe algún hecho con
       exactamente el mismo valor (ignorando la key), no escribe y retorna False.
       Esto previene triplicados como hecho_20260510_XXXXXX con el mismo dato.
    3. Si la key ya existe con un valor distinto, actualiza (comportamiento previo).

    Args:
        key:   Nombre del hecho (ej: 'modelo_base').
        value: Valor del hecho (ej: 'llama3.2').

    Returns:
        True si se guardó correctamente.
        False si key o value están vacíos, o si el valor ya existe en otro hecho.

    Never raises.
    """
    if not key.strip() or not value.strip():
        log.warning("save_fact rechazado: key=%r value=%r", key, value)
        return False

    # Guardia anti-duplicado semántico
    existing_facts = load_project_facts()
    value_normalized = value.strip().lower()
    for existing_key, existing_value in existing_facts.items():
        if existing_value.strip().lower() == value_normalized:
            if existing_key == key.strip():
                log.debug(
                    "save_fact omitido (ya existe igual): %s = %s", key, value
                )
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
    """Actualiza un campo de work_state.

    Args:
        field: Campo a actualizar (ej: 'current_focus', 'next_step').
        value: Nuevo valor del campo.

    Never raises.
    """
    if not field.strip() or not value.strip():
        log.warning("update_state ignorado: field=%r value=%r", field, value)
        return
    update_work_state(field.strip(), value.strip())
    log.debug("work_state actualizado: %s = %s", field, value)


def create_task(title: str, priority: str = "medium", notes: str = "") -> str:
    """Crea una tarea nueva y devuelve su ID.

    Reglas:
    1. title debe ser no-vacío. priority inválido → 'medium'.
    2. Guardia anti-duplicado: si ya existe una tarea pendiente con el
       mismo título (comparación case-insensitive, sin espacios extras),
       retorna el ID de la tarea existente sin crear una nueva.

    Args:
        title:    Título de la tarea.
        priority: 'low' | 'medium' | 'high'. Default 'medium'.
        notes:    Notas adicionales. Default ''.

    Returns:
        str con el ID generado (ej: 'T-0510123456') o el ID existente si duplicado.

    Never raises.
    """
    title = title.strip()
    priority = priority.strip().lower()
    notes = notes.strip()

    if not title:
        log.warning("create_task ignorado: title vacío")
        return ""

    valid_priorities = {"low", "medium", "high"}
    if priority not in valid_priorities:
        priority = "medium"

    existing_tasks = load_tasks()
    title_normalized = title.lower()
    for task in existing_tasks.get("tasks", []):
        if (
            task.get("title", "").strip().lower() == title_normalized
            and task.get("status") not in ("done", "completed")
        ):
            log.info(
                "create_task omitido (ya existe pendiente '%s'): %s",
                task["id"], title,
            )
            return task["id"]

    task_id = add_task(title=title, priority=priority, notes=notes)
    log.debug("Tarea creada: %s — %s", task_id, title)
    return task_id


def complete_task(task_id: str) -> None:
    """Marca una tarea como completada.

    Args:
        task_id: ID de la tarea (ej: 'T-0510123456').

    Never raises.
    """
    if not task_id.strip():
        log.warning("complete_task ignorado: task_id vacío")
        return
    update_task_status(task_id.strip(), "completed")
    log.debug("Tarea completada: %s", task_id)


def record_episode(summary: str, turns: int) -> None:
    """Guarda el resumen de la sesión actual como episodio.

    Args:
        summary: Resumen textual de la sesión.
        turns:   Número de turnos de la sesión.

    Never raises.
    """
    if not summary.strip():
        log.warning("record_episode ignorado: summary vacío")
        return
    save_episode(summary=summary.strip(), turns=turns)
    log.debug("Episodio registrado: %d turnos", turns)
