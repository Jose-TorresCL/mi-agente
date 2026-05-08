"""Construcción del contexto de memoria estructurada para el prompt RAG.

Responsabilidad única: leer los JSON de storage/ y devolver
un string listo para inyectar en el system prompt.

Diferencia clave respecto a build_structured_memory_context() anterior:
  - Muestra TODOS los campos de project_facts dinámicamente.
  - Si se agrega una clave nueva a project_facts.json, el LLM la ve
    automáticamente sin necesidad de tocar este archivo.
"""
from __future__ import annotations

from app.memory_store import (
    load_profile,
    load_project_facts,
    load_tasks,
    load_work_state,
    load_last_episode,
)


def build_memory_context() -> str:
    """Lee todos los JSON y construye el texto de contexto para el LLM."""
    profile       = load_profile()
    project_facts = load_project_facts()
    work_state    = load_work_state()
    tasks_data    = load_tasks()
    tasks         = tasks_data.get("tasks", []) if tasks_data else []
    pending_tasks = [t for t in tasks if t.get("status") not in ("done", "completed")][:3]

    lines: list[str] = []

    # ── Perfil ────────────────────────────────────────────────────────────
    if profile:
        lines.append("Perfil del usuario:")
        lines.append(f"- Nombre: {profile.get('user_name', 'desconocido')}")
        lines.append(f"- Nivel: {profile.get('user_level', 'desconocido')}")
        lines.append(f"- Proyecto: {profile.get('project_type', 'desconocido')}")

    # ── Hechos del proyecto (dinámico — todos los campos) ─────────────────
    if project_facts:
        lines.append("")
        lines.append("Hechos persistentes del proyecto:")
        for key, value in project_facts.items():
            lines.append(f"- {key}: {value}")

    # ── Estado de trabajo ─────────────────────────────────────────────────
    if work_state:
        lines.append("")
        lines.append("Estado actual de trabajo:")
        lines.append(f"- Foco actual: {work_state.get('current_focus', '')}")
        lines.append(f"- Último paso completado: {work_state.get('last_completed', '')}")
        lines.append(f"- Siguiente paso: {work_state.get('next_step', '')}")
        blockers = work_state.get("current_blockers", [])
        if blockers:
            lines.append(f"- Bloqueos: {', '.join(blockers)}")

    # ── Tareas pendientes (máx. 3) ────────────────────────────────────────
    if pending_tasks:
        lines.append("")
        lines.append("Tareas pendientes prioritarias:")
        for task in pending_tasks:
            lines.append(
                f"- {task.get('id', '')}: {task.get('title', '')} "
                f"(prioridad: {task.get('priority', 'media')}, "
                f"estado: {task.get('status', 'pending')})"
            )

    # ── Episodio anterior ─────────────────────────────────────────────────
    episode = load_last_episode()
    if episode:
        lines.append("")
        lines.append("Contexto de la sesión anterior:")
        lines.append(
            f"- {episode['date']} {episode['time']} "
            f"({episode['turns']} turnos): {episode['summary']}"
        )

    return "\n".join(lines).strip()
