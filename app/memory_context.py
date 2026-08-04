from __future__ import annotations

import logging
from typing import Any

from app.memory_store import (
    load_profile,
    load_project_facts,
    load_tasks,
    load_work_state,
    load_last_episode,
)

logger = logging.getLogger(__name__)


def _safe_str(value) -> str:
    """Coerción defensiva: cualquier valor (None, número, lista) → str limpio."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)) and not value:
        return ""
    if isinstance(value, dict) and not value:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _safe_load(loader_fn, source_name: str):
    """Ejecuta un loader; si falla, loguea y devuelve None sin propagar la excepción."""
    try:
        return loader_fn()
    except Exception as e:
        logger.warning(f"[memory_context] Fuente omitida por error: {source_name} → {e}")
        return None


def _format_profile(profile: dict[str, Any] | None) -> list[str]:
    """Formatea el bloque de perfil. Reutilizado por build_memory_context y get_selective_context."""
    if not profile:
        return []
    return [
        "Perfil del usuario:",
        f"- Nombre: {profile.get('user_name', 'desconocido')}",
        f"- Nivel: {profile.get('user_level', 'desconocido')}",
        f"- Proyecto: {profile.get('project_type', 'desconocido')}",
    ]


def build_memory_context() -> str:
    """... (docstring igual, ahora 'Never raises' es cierto de verdad) ..."""
    profile       = _safe_load(load_profile, "profile.json")
    project_facts = _safe_load(load_project_facts, "project_facts.json")
    work_state    = _safe_load(load_work_state, "work_state.json")
    tasks_data    = _safe_load(load_tasks, "tasks.json")
    tasks         = tasks_data.get("tasks", []) if tasks_data else []
    pending_tasks = [t for t in tasks if t.get("status") not in ("done", "completed")][:3]

    lines: list[str] = []

    # ── Perfil ─────────────────────────────────────────────────────
    profile_lines = _format_profile(profile)
    if profile_lines:
        lines.extend(profile_lines)

    # ── Hechos del proyecto ──────────────────────────────
    if project_facts:
        lines.append("")
        lines.append("Hechos persistentes del proyecto:")
        for key, value in project_facts.items():
            lines.append(f"- {key}: {_safe_str(value)}")

    # ── Estado de trabajo ──────────────────────
    if work_state:
        ws_lines: list[str] = []
        _ws_fields = [
            ("current_focus",   "Foco actual"),
            ("last_completed",  "Último paso completado"),
            ("next_step",       "Siguiente paso"),
            ("current_phase",   "Fase actual"),
            ("session_goal",    "Objetivo de sesión"),
        ]
        for key, label in _ws_fields:
            value = _safe_str(work_state.get(key))   # ← fix: coerción segura, no .strip() directo
            if value:
                ws_lines.append(f"- {label}: {value}")

        blockers = work_state.get("current_blockers", [])
        if isinstance(blockers, list) and blockers:
            ws_lines.append(f"- Bloqueos: {', '.join(_safe_str(b) for b in blockers)}")
        elif isinstance(blockers, str) and blockers.strip():
            ws_lines.append(f"- Bloqueos: {blockers.strip()}")

        if ws_lines:
            lines.append("")
            lines.append("Estado actual de trabajo:")
            lines.extend(ws_lines)

    # ── Tareas pendientes ─────────────────────────────
    if pending_tasks:
        lines.append("")
        lines.append("Tareas pendientes prioritarias:")
        for task in pending_tasks:
            lines.append(
                f"- {task.get('id', '')}: {task.get('title', '')} "
                f"(prioridad: {task.get('priority', 'media')}, "
                f"estado: {task.get('status', 'pending')})"
            )

    # ── Episodio anterior ───────────────────────────────────────
    episode = _safe_load(load_last_episode, "episodic_memory.json")
    if episode:
        lines.append("")
        lines.append("Contexto de la sesión anterior:")
        lines.append(
            f"- {episode['date']} {episode['time']} "
            f"({episode['turns']} turnos): {episode['summary']}"
        )

    return "\n".join(lines).strip()


def get_selective_context(route: str) -> str:
    """... (docstring igual) ..."""
    if route == "memory":
        return build_memory_context()

    if route == "rag":
        profile       = _safe_load(load_profile, "profile.json")
        project_facts = _safe_load(load_project_facts, "project_facts.json")
        lines: list[str] = _format_profile(profile)[:3]  # solo Nombre + Nivel 
        if project_facts:
            lines.append("")
            lines.append("Proyecto:")
            for key in ("project_name", "current_phase", "modelo_base"):
                value = _safe_str(project_facts.get(key))   # ← fix: coerción segura
                if value:
                    lines.append(f"- {key}: {value}")
        return "\n".join(lines).strip()

    if route.startswith("tool_"):
        return ""

    return build_memory_context()