"""Funciones de formato para respuestas de memoria y contexto.

Extraídas de intelligence.py (refactor R-F1) para mantener
intelligence.py como orquestador puro sin lógica de presentación.

Funciones públicas:
  format_profile_answer(profile)         → str con perfil formateado en Markdown
  format_tasks_answer(tasks_data, ...)   → str con lista de tareas pendientes/hechas
  build_history_snippet(chat_history)    → str con últimas 3 líneas de historial
  format_episodes_context(episodes)      → str con resúmenes episódicos formateados
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage

_HISTORY_TURNS = 3
_HISTORY_LINE_MAX = 80


def format_profile_answer(profile: dict) -> str:
    """Formatea el dict de perfil del usuario en texto Markdown legible.

    Args:
        profile: Dict tal como lo devuelve memory_store.load_profile().
                 Campos esperados: user_name, user_level, project_type,
                 learning_style, preferred_language.

    Returns:
        String con los campos disponibles en formato '**Label:** valor',
        uno por línea. Devuelve string vacío si profile es None o vacío.

    Ejemplo de salida:
        **Nombre:** José
        **Nivel:** junior
        **Proyecto:** asistente IA local
    """
    if not profile:
        return ""
    lines = []
    field_labels = [
        ("user_name",          "Nombre"),
        ("user_level",         "Nivel"),
        ("project_type",       "Proyecto"),
        ("learning_style",     "Estilo de aprendizaje"),
        ("preferred_language", "Lenguaje preferido"),
    ]
    for key, label in field_labels:
        value = profile.get(key, "")
        if value:
            lines.append(f"**{label}:** {value}")
    return "\n".join(lines)


def format_tasks_answer(tasks_data: dict, question: str = "") -> str:
    """Formatea la lista de tareas en texto legible según la pregunta del usuario.

    Detecta si la pregunta pregunta por tareas 'hechas' (completadas) o por
    tareas pendientes (comportamiento por defecto). Muestra máximo 10 ítems
    para no saturar la respuesta.

    Args:
        tasks_data: Dict tal como lo devuelve memory_store.load_tasks().
                    Debe contener la clave 'tasks' con lista de dicts de tarea.
        question:   Texto de la pregunta del usuario (para detectar si pide
                    tareas completadas). Por defecto muestra pendientes.

    Returns:
        String con la lista de tareas en formato '- [ID] título (prioridad)',
        precedido por un encabezado. Devuelve mensaje informativo si no hay tareas.

    Ejemplo de salida (pendientes):
        **Tareas pendientes:**
        - [T-001] Documentar memory_manager (high)
        - [T-002] Agregar tests fidelidad (medium)
    """
    if not tasks_data:
        return "No encontré tareas registradas."

    tasks = tasks_data.get("tasks", [])
    if not tasks:
        return "No encontré tareas registradas."

    question_lower = question.lower() if question else ""
    wants_done = any(kw in question_lower for kw in
                     ("hechas", "completadas", "terminadas", "done", "completé", "completé"))

    if wants_done:
        filtered = [t for t in tasks if t.get("status") in ("done", "completed")]
        header = "**Tareas completadas:**"
        empty_msg = "No hay tareas completadas aún."
    else:
        filtered = [t for t in tasks if t.get("status") not in ("done", "completed")]
        header = "**Tareas pendientes:**"
        empty_msg = "No hay tareas pendientes. ¡Todo al día!"

    if not filtered:
        return empty_msg

    lines = [header]
    for t in filtered[:10]:
        task_id = t.get("id", "?")
        title = t.get("title", "(sin título)")
        priority = t.get("priority", "medium")
        lines.append(f"- [{task_id}] {title} ({priority})")

    if len(filtered) > 10:
        lines.append(f"... y {len(filtered) - 10} más.")

    return "\n".join(lines)


def build_history_snippet(chat_history: list | None, max_turns: int = _HISTORY_TURNS) -> str:
    """Construye un snippet comprimido de las últimas N rondas del historial.

    Usada por _synthesize_memory_answer() para inyectar contexto conversacional
    en el prompt de síntesis sin exceder el contexto del LLM.

    Args:
        chat_history: Lista de mensajes LangChain (HumanMessage / AIMessage).
                      Puede ser None — en ese caso devuelve string vacío.
        max_turns:    Número de turnos (rondas usuario+asistente) a incluir.
                      Por defecto 3 (últimas 6 líneas del historial).

    Returns:
        String con formato 'Usuario: ...' / 'Lautaro: ...' por línea,
        truncado a _HISTORY_LINE_MAX chars por línea. Devuelve '' si
        chat_history es None o vacío.
    """
    if not chat_history:
        return ""
    lines: list[str] = []
    for m in chat_history[-(max_turns * 2):]:
        role = "Usuario" if isinstance(m, HumanMessage) else "Lautaro"
        content = m.content.strip().replace("\n", " ")
        truncated = content[:_HISTORY_LINE_MAX] + ("…" if len(content) > _HISTORY_LINE_MAX else "")
        lines.append(f"{role}: {truncated}")
    return "\n".join(lines)


def format_episodes_context(episodes: list[dict]) -> str:
    """Formatea una lista de episodios de sesión en texto legible para el LLM.

    Usada en _retrieve_memory_context() cuando hay episodios con contenido
    real (no marcados como 'Resumen no disponible').

    Args:
        episodes: Lista de dicts de episodio con campos:
                  date (str), time (str), turns (int), summary (str).
                  Se espera que ya estén filtrados — sin episodios vacíos.

    Returns:
        String con un bloque por episodio en formato:
            Sesión YYYY-MM-DD HH:MM (N turnos):
            <resumen>
        Bloques separados por línea en blanco.
    """
    blocks: list[str] = []
    for ep in episodes:
        date_str = f"{ep.get('date', '')} {ep.get('time', '')}".strip()
        turns = ep.get("turns", 0)
        summary = ep.get("summary", "").strip()
        header = f"Sesión {date_str} ({turns} turnos):"
        blocks.append(f"{header}\n{summary}")
    return "\n\n".join(blocks)
