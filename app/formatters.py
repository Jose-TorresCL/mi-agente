"""Funciones de formato para respuestas de memoria y contexto.

Extraídas de intelligence.py (refactor R-F1) para mantener
intelligence.py como orquestador puro sin lógica de presentación.

Funciones públicas:
  format_profile_answer(profile)         → str con perfil en lenguaje natural
  format_tasks_answer(tasks_data, ...)   → str con tareas en lenguaje natural
  build_history_snippet(chat_history)    → str con últimas 3 líneas de historial
  format_episodes_context(episodes)      → str con resúmenes episódicos formateados

Fix conversacional: las tres funciones de formato ahora devuelven texto
en primera persona y lenguaje natural en vez de serializar campos con
**Label:** valor. Esto evita que el fallback de síntesis suene robótico
cuando generate_raw no está disponible.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage

_HISTORY_TURNS = 3
_HISTORY_LINE_MAX = 80


def format_profile_answer(profile: dict) -> str:
    """Devuelve el perfil del usuario en lenguaje natural conversacional.

    Args:
        profile: Dict tal como lo devuelve memory_store.load_profile().
                 Campos esperados: user_name, user_level, project_type,
                 learning_style, preferred_language.

    Returns:
        String en primera persona, listo para mostrar al usuario.
        Devuelve string vacío si profile es None o vacío.

    Ejemplo de salida:
        Te llamo José Torres. Sos desarrollador junior y estás trabajando
        en tu asistente IA local. Preferís aprender entendiendo el fondo,
        con analogías y ejemplos antes/después.
    """
    if not profile:
        return ""

    name    = profile.get("user_name", "")
    level   = profile.get("user_level", "")
    project = profile.get("project_type", "")
    style   = profile.get("learning_style", {})

    parts = []

    # Nombre
    if name:
        parts.append(f"Tu nombre es **{name}**.")

    # Nivel y proyecto
    nivel_proyecto = ""
    if level and project:
        nivel_proyecto = f"Sos **{level}** y estás trabajando en **{project}**."
    elif level:
        nivel_proyecto = f"Sos **{level}**."
    elif project:
        nivel_proyecto = f"Estás trabajando en **{project}**."
    if nivel_proyecto:
        parts.append(nivel_proyecto)

    # Estilo de aprendizaje — solo si tiene campos útiles
    if isinstance(style, dict) and style:
 n        style_items = []
        if style.get("wants_to_understand"):
            style_items.append("entender el fondo")
        if style.get("prefers_analogies"):
            style_items.append("analogías")
        if style.get("prefers_before_after_examples"):
            style_items.append("ejemplos antes/después")
        if style.get("not_just_copy_commands"):
            style_items.append("no solo copiar comandos")
        if style_items:
            parts.append(f"Tu estilo de aprendizaje: preferís {', '.join(style_items)}.")

    return " ".join(parts) if parts else ""


def format_tasks_answer(tasks_data: dict, question: str = "") -> str:
    """Devuelve las tareas del usuario en lenguaje natural.

    Detecta si la pregunta pide tareas completadas o pendientes.
    Muestra máximo 10 ítems. Oculta los IDs técnicos internos.

    Args:
        tasks_data: Dict tal como lo devuelve memory_store.load_tasks().
        question:   Pregunta del usuario para detectar intención.

    Returns:
        String conversacional con la lista de tareas.

    Ejemplo de salida:
        Tenés 3 tareas abiertas:
        · actualizar plan-robustecimiento.md (alta prioridad)
        · documentar fase 9 (prioridad media)
        · revisar storage en git (prioridad media)
    """
    if not tasks_data:
        return "No encontré tareas registradas."

    tasks = tasks_data.get("tasks", [])
    if not tasks:
        return "No encontré tareas registradas."

    question_lower = question.lower() if question else ""
    wants_done = any(kw in question_lower for kw in
                     ("hechas", "completadas", "terminadas", "done", "completé"))

    priority_label = {"high": "alta prioridad", "medium": "prioridad media", "low": "baja prioridad"}

    if wants_done:
        filtered = [t for t in tasks if t.get("status") in ("done", "completed")]
        if not filtered:
            return "No hay tareas completadas aún."
        intro = f"Completaste {len(filtered)} tarea{'s' if len(filtered) != 1 else ''}:"
    else:
        filtered = [t for t in tasks if t.get("status") not in ("done", "completed")]
        if not filtered:
            return "No hay tareas pendientes. ¡Todo al día!"
        intro = f"Tenés {len(filtered)} tarea{'s' if len(filtered) != 1 else ''} abierta{'s' if len(filtered) != 1 else ''}:"

    lines = [intro]
    for t in filtered[:10]:
        title    = t.get("title", "(sin título)")
        priority = t.get("priority", "medium")
        label    = priority_label.get(priority, priority)
        lines.append(f"· {title} ({label})")

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
        String con intro conversacional seguida de un bloque por episodio:
            Esto es lo que recuerdo de tus sesiones anteriores:

            Sesión YYYY-MM-DD HH:MM (N turnos):
            <resumen>
        Bloques separados por línea en blanco.
    """
    if not episodes:
        return ""

    blocks: list[str] = []
    for ep in episodes:
        date_str = f"{ep.get('date', '')} {ep.get('time', '')}".strip()
        turns    = ep.get("turns", 0)
        summary  = ep.get("summary", "").strip()
        header   = f"Sesión {date_str} ({turns} turnos):"
        blocks.append(f"{header}\n{summary}")

    intro = "Esto es lo que recuerdo de tus sesiones anteriores:"
    return intro + "\n\n" + "\n\n".join(blocks)
