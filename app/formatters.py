"""Helpers de formato de respuesta — funciones puras sin efectos secundarios.

Extraídas de intelligence.py (refactor R-F1).
No importan nada de app/ excepto tipos de LangChain para isinstance().
No modifican estado. Reciben datos, devuelven string.

Funciones públicas
──────────────────
    format_profile_answer(profile)           → str
    format_tasks_answer(tasks_data, question) → str
    build_history_snippet(chat_history, max_turns) → str
    format_episodes_context(episodes)        → str
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage

_HISTORY_LINE_MAX = 80
_MEMORY_HISTORY_TURNS = 3

_DONE_TASK_KEYWORDS = {
    "hechas", "hecho", "completadas", "completada", "completado",
    "cerradas", "cerrada", "terminadas", "terminada", "listas", "lista",
    "done",
}


def format_profile_answer(profile: dict) -> str:
    """Formatea el perfil de usuario como lista legible."""
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


def format_tasks_answer(tasks_data: dict, question: str = "") -> str:
    """Formatea tareas pendientes o completadas según la pregunta."""
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


def build_history_snippet(
    chat_history: list | None,
    max_turns: int = _MEMORY_HISTORY_TURNS,
) -> str:
    """Devuelve las últimas N rondas del historial como texto compacto."""
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


def format_episodes_context(episodes: list[dict]) -> str:
    """Formatea una lista de episodios para incluir en contexto de respuesta."""
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
