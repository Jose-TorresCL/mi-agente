"""Construcción del contexto de memoria estructurada para el prompt RAG.

Responsabilidad única: leer los JSON de storage/ y devolver
un string listo para inyectar en el system prompt.

Fuentes que combina build_memory_context()
──────────────────────────────────────────
  storage/profile.json          → perfil del usuario (nombre, nivel, tipo de proyecto)
  storage/project_facts.json    → hechos persistentes del proyecto (clave-valor libre)
  storage/work_state.json       → estado operativo actual (foco, último paso, siguiente
                                  paso, fase, objetivo de sesión, bloqueos)
  storage/tasks.json            → lista de tareas; se muestran solo las 3 primeras
                                  no completadas (status != 'done' / 'completed')
  storage/episodic_memory.json  → último episodio registrado (via load_last_episode())

Filtrado de campos vacíos (Día 2):
  Los campos de work_state se muestran solo si tienen valor no vacío.
  Esto evita líneas tipo "- Siguiente paso: " que confunden al LLM.

Fuentes que combina get_selective_context() por carril
───────────────────────────────────────────────────────
  memory   → todas las fuentes (contexto completo)
  rag      → solo profile.json + project_facts.json (3 campos clave)
  tool_*   → sin fuentes (las tools leen storage/ directamente)
  otros    → todas las fuentes (fallback seguro)

Cambios Día 2:
  - build_memory_context(): filtra campos vacíos en work_state para no
    contaminar el prompt con líneas tipo "- Siguiente paso: ".
  - get_selective_context(): añade work_state como fuente explícita cuando
    la consulta es de tipo 'memory', garantizando que el LLM siempre tenga
    foco/último-paso/siguiente-paso disponibles en ese carril.
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
    """Lee todos los JSON de storage/ y construye el texto de contexto para el LLM.

    Fuentes combinadas (en orden de aparición en el prompt):
      1. storage/profile.json        — nombre, nivel y tipo de proyecto del usuario.
      2. storage/project_facts.json  — hechos clave-valor persistentes del proyecto.
      3. storage/work_state.json     — estado operativo: foco actual, último paso
                                       completado, siguiente paso, fase, objetivo de
                                       sesión y bloqueos activos.
                                       Solo se incluyen campos con valor no vacío
                                       (filtro Día 2 — evita líneas huecas en el prompt).
      4. storage/tasks.json          — las 3 tareas pendientes con mayor prioridad
                                       (status != 'done' ni 'completed').
      5. storage/episodic_memory.json — el último episodio registrado (fecha, hora,
                                       turnos y resumen) para contextualizar la sesión.

    Returns:
        str — texto multilínea listo para inyectar en {memory_context} del prompt.
              Cadena vacía si no hay ninguna fuente disponible.

    Never raises: si un JSON no existe o falla la carga, esa sección se omite
    silenciosamente. El llamador siempre recibe un string válido.
    """
    profile       = load_profile()
    project_facts = load_project_facts()
    work_state    = load_work_state()
    tasks_data    = load_tasks()
    tasks         = tasks_data.get("tasks", []) if tasks_data else []
    pending_tasks = [t for t in tasks if t.get("status") not in ("done", "completed")][:3]

    lines: list[str] = []

    # ── Perfil ─────────────────────────────────────────────────────
    if profile:
        lines.append("Perfil del usuario:")
        lines.append(f"- Nombre: {profile.get('user_name', 'desconocido')}")
        lines.append(f"- Nivel: {profile.get('user_level', 'desconocido')}")
        lines.append(f"- Proyecto: {profile.get('project_type', 'desconocido')}")

    # ── Hechos del proyecto (dinámico) ──────────────────────────────
    if project_facts:
        lines.append("")
        lines.append("Hechos persistentes del proyecto:")
        for key, value in project_facts.items():
            lines.append(f"- {key}: {value}")

    # ── Estado de trabajo (solo campos con valor) ──────────────────────
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
            value = work_state.get(key, "").strip()
            if value:  # Día 2: omitir si vacío para no generar líneas huecas
                ws_lines.append(f"- {label}: {value}")

        blockers = work_state.get("current_blockers", [])
        if isinstance(blockers, list) and blockers:
            ws_lines.append(f"- Bloqueos: {', '.join(blockers)}")
        elif isinstance(blockers, str) and blockers.strip():
            ws_lines.append(f"- Bloqueos: {blockers.strip()}")

        if ws_lines:
            lines.append("")
            lines.append("Estado actual de trabajo:")
            lines.extend(ws_lines)

    # ── Tareas pendientes (máx. 3) ─────────────────────────────────
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
    episode = load_last_episode()
    if episode:
        lines.append("")
        lines.append("Contexto de la sesión anterior:")
        lines.append(
            f"- {episode['date']} {episode['time']} "
            f"({episode['turns']} turnos): {episode['summary']}"
        )

    return "\n".join(lines).strip()


def get_selective_context(route: str) -> str:
    """Devuelve contexto de memoria filtrado según el carril de enrutamiento.

    El objetivo es inyectar solo lo relevante para cada tipo de consulta,
    en lugar del contexto completo siempre. Esto reduce el tamaño del prompt
    y evita que información de estado operativo distraiga al LLM en consultas
    puramente documentales (carril 'rag').

    Decisión de diseño por carril:
      memory   → contexto completo (profile + facts + work_state + tasks + episodio).
                 El LLM necesita todo para responder sobre estado del proyecto.
                 Día 2: work_state garantizado en este carril.

      rag      → solo profile + facts (3 campos clave de project_facts).
                 El LLM sabe en qué proyecto trabaja el usuario, pero no recibe
                 estado operativo que no aporta al retrieval documental y podría
                 contaminar la síntesis de fuentes.

      tool_*   → sin contexto. Las tools leen storage/ directamente — inyectar
                 memoria en el prompt sería redundante y aumentaría la latencia.

      otros    → contexto completo como fallback seguro. Preferible sobre-informar
                 que dejar al LLM sin datos en un carril nuevo o no previsto.

    Args:
        route: carril devuelto por el router. Ejemplos: 'memory', 'rag',
               'tool_read_file', 'identity', 'episode'.

    Returns:
        str listo para inyectar en el system prompt. Puede ser cadena vacía
        para carriles tool_*.
    """
    if route == "memory":
        # Contexto completo: el LLM necesita todo para responder sobre estado
        return build_memory_context()

    if route == "rag":
        # Solo perfil y hechos: el LLM sabe el contexto del proyecto,
        # pero no contamina el prompt con estado operativo que no aporta al RAG
        profile       = load_profile()
        project_facts = load_project_facts()
        lines: list[str] = []
        if profile:
            lines.append("Perfil del usuario:")
            lines.append(f"- Nombre: {profile.get('user_name', 'desconocido')}")
            lines.append(f"- Nivel: {profile.get('user_level', 'desconocido')}")
        if project_facts:
            lines.append("")
            lines.append("Proyecto:")
            for key in ("project_name", "current_phase", "modelo_base"):
                value = project_facts.get(key, "").strip()
                if value:
                    lines.append(f"- {key}: {value}")
        return "\n".join(lines).strip()

    if route.startswith("tool_"):
        # Las tools no necesitan contexto de memoria en el prompt
        return ""

    # Fallback: contexto completo
    return build_memory_context()
