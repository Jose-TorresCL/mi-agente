"""Herramientas que modifican el estado del asistente.

Este módulo contiene SOLO las funciones tool_* que leen/escriben memoria.
Las utilidades de parseo y filesystem viven en tool_helpers.py.

Funciones públicas (sin cambio de interfaz):
  tool_save_fact()          — guarda hecho en project_facts.json
  tool_create_task()        — crea tarea en tasks.json
  tool_complete_task()      — marca tarea como completada
  tool_update_work_state()  — actualiza work_state.json
  suggest_next_step()       — sugerencia post-actualización

Re-exporta desde tool_helpers para compatibilidad con imports existentes:
  list_project_files, extract_file_path, read_project_file,
  extract_task_id, parse_work_state_update, VALID_PRIORITIES

Nota de arquitectura:
  Todas las operaciones de memoria pasan por memory_manager,
  no por memory_store directamente. memory_manager es el
  guardián de la capa de memoria.
"""
from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime

from app.memory_manager import (
    save_fact as _mm_save_fact,
    create_task as _mm_create_task,
    complete_task as _mm_complete_task,
    get_tasks as _mm_get_tasks,
)

# Re-exportar helpers — mantiene compatibilidad con todos los imports existentes
from app.tool_helpers import (  # noqa: F401
    list_project_files,
    extract_file_path,
    read_project_file,
    extract_task_id,
    parse_work_state_update,
    _parse_key_value,
    VALID_PRIORITIES,
    _VALUE_PREFIXES,
)


# ─────────────────────────────────────────────
# Tool: guardar hecho
# ─────────────────────────────────────────────

def tool_save_fact(content: str) -> str:
    """Guarda un hecho en project_facts.json.

    D3: rechaza contenido vacío antes de llamar a memory_manager.save_fact.

    Args:
        content: Texto del hecho a guardar (ya limpio, sin prefijos de navegación).

    Returns:
        str con confirmación del hecho guardado, o mensaje de error.

    Never raises.
    """
    content = content.strip()

    if not content:
        return "No pude guardar el hecho: el contenido está vacío."

    kv = _parse_key_value(content)
    if kv:
        key, value = kv
        ok = _mm_save_fact(key, value)
        if ok:
            return f"✓ Hecho guardado: {key} = \"{value}\""
        return "No pude guardar el hecho: clave o valor vacíos."

    key = f"hecho_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    ok = _mm_save_fact(key, content)
    if ok:
        return f"✓ Hecho guardado: \"{content}\""
    return "No pude guardar el hecho: contenido vacío."


# ─────────────────────────────────────────────
# Tool: crear tarea
# ─────────────────────────────────────────────

def tool_create_task(title: str, priority: str = "medium", notes: str = "") -> str:
    """Crea una nueva tarea en tasks.json.

    Args:
        title:    Título de la tarea.
        priority: 'low' | 'medium' | 'high'. Default 'medium'.
        notes:    Notas adicionales. Default ''.

    Returns:
        str con confirmación y el ID generado.

    Never raises.
    """
    title = title.strip()
    priority = priority.strip().lower()
    notes = notes.strip()

    if not title:
        return "No pude crear la tarea: falta el título."

    task_id = _mm_create_task(title=title, priority=priority, notes=notes)
    if not task_id:
        return "No pude crear la tarea: título vacío."
    return f"✓ Tarea creada: [{task_id}] {title} (prioridad: {priority})"


# ─────────────────────────────────────────────
# Tool: completar tarea
# ─────────────────────────────────────────────

def tool_complete_task(task_id: str) -> str:
    """Marca una tarea existente como completada dado su ID.

    Args:
        task_id: ID de la tarea (ej: 'T-0506132952').

    Returns:
        str con confirmación, o mensaje de error si no se encontró.

    Never raises.
    """
    if not task_id:
        return "No pude identificar el ID de la tarea. Indícalo así: T-001, T-002..."

    tasks_data = _mm_get_tasks()
    tasks = tasks_data.get("tasks", [])

    found = False
    for task in tasks:
        if task.get("id", "").upper() == task_id.upper():
            if task.get("status") == "completed":
                return f"ℹ️  La tarea {task_id} ya estaba marcada como completada."
            found = True
            break

    if not found:
        available = [t.get("id") for t in tasks]
        return f"❌ No encontré la tarea '{task_id}'. Tareas disponibles: {available}"

    _mm_complete_task(task_id)
    return f"✅ Tarea {task_id} marcada como completada."


# ─────────────────────────────────────────────
# Tool: actualizar work_state
# ─────────────────────────────────────────────

def tool_update_work_state(
    texto: str = "",
    *,
    current_focus: str | None = None,
    next_step: str | None = None,
    last_completed_step: str | None = None,
) -> str:
    """Actualiza work_state.json desde conversación libre o desde kwargs directos.

    D3: todos los valores vacíos o solo-espacios se ignoran.

    Modo A — texto libre:     tool_update_work_state("actualiza el foco a fase 4")
    Modo B — kwargs directos: tool_update_work_state(next_step="escribir tests")

    Returns:
        str con confirmación de los campos actualizados,
        o advertencia si no se detectó ningún cambio.

    Never raises.
    """
    import json

    path = Path("storage/work_state.json")
    try:
        state: dict = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        state = {}

    cambios: list[str] = []

    # ── Modo B: kwargs directos ──────────────────────────────
    if current_focus is not None:
        val = current_focus.strip()
        if val:
            state["current_focus"] = val
            cambios.append(f"current_focus → '{val}'")

    if next_step is not None:
        val = next_step.strip()
        if val:
            state["next_step"] = val
            cambios.append(f"next_step → '{val}'")

    if last_completed_step is not None:
        val = last_completed_step.strip()
        if val:
            fecha = datetime.now().strftime("%d/%m/%Y")
            state["last_completed"] = f"{val} — {fecha}"
            cambios.append(f"last_completed → '{val}'")

    # ── Modo A: texto libre ───────────────────────────────────
    if texto:
        texto_lower = texto.lower()

        if current_focus is None:
            patrones_foco = [r"(?:actualiza el foco a|foco(?:\s+es)?(?:\s*:)?|enf[oó]cate en)\s+(.+)"]
            for pat in patrones_foco:
                m = re.search(pat, texto_lower)
                if m:
                    valor = m.group(1).strip().rstrip(".,")
                    if valor:
                        state["current_focus"] = valor
                        cambios.append(f"current_focus → '{valor}'")
                    break

        if last_completed_step is None:
            patrones_completado = [
                r"(?:complet[eé]|termin[eé]|acab[eé]|ya hice|ya termin[eé]|logramos|listo)\s+(?:de\s+|con\s+)?(.+)"
            ]
            for pat in patrones_completado:
                m = re.search(pat, texto_lower)
                if m:
                    valor = m.group(1).strip().rstrip(".,")
                    if valor:
                        fecha = datetime.now().strftime("%d/%m/%Y")
                        state["last_completed"] = f"{valor} — {fecha}"
                        cambios.append(f"last_completed → '{valor}'")
                    break

        if next_step is None:
            patrones_siguiente = [
                r"(?:el siguiente paso es|siguiente paso[:\s]+|sigue[:\s]+|pr[oó]ximo paso[:\s]+)\s+(.+)"
            ]
            for pat in patrones_siguiente:
                m = re.search(pat, texto_lower)
                if m:
                    valor = m.group(1).strip().rstrip(".,")
                    if valor:
                        state["next_step"] = valor
                        cambios.append(f"next_step → '{valor}'")
                    break

    if not cambios:
        return "⚠️ No entendí qué campo actualizar. Usa: 'foco a X', 'completé X' o 'siguiente paso es X'."

    state["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return f"⚠️ Cambios detectados pero no pude escribir work_state.json: {e}"

    return "✅ work_state actualizado:\n" + "\n".join(f"  • {c}" for c in cambios)


# ─────────────────────────────────────────────
# Sugerencia automática post-actualización
# ─────────────────────────────────────────────

def suggest_next_step() -> str:
    """Lee work_state.json y tasks.json y devuelve una sugerencia del siguiente paso."""
    import json

    ws_path = Path("storage/work_state.json")
    state = json.loads(ws_path.read_text(encoding="utf-8")) if ws_path.exists() else {}

    next_step     = state.get("next_step", "")
    current_focus = state.get("current_focus", "")
    last_done     = state.get("last_completed", "")

    tasks_data = _mm_get_tasks()
    pending = [
        t for t in tasks_data.get("tasks", [])
        if t.get("status") not in ("done", "completed")
    ]

    lines = ["", "─── Sugerencia post-actualización ───"]

    if next_step:
        lines.append(f"  ➡️  Siguiente paso registrado: {next_step}")
    elif pending:
        t = pending[0]
        lines.append(
            f"  ➡️  Tarea pendiente: [{t['id']}] {t['title']} "
            f"({t.get('priority', 'medium')})"
        )
    else:
        lines.append("  ➡️  No hay pasos ni tareas pendientes registradas.")

    if current_focus:
        lines.append(f"  🎯  Foco actual: {current_focus}")

    if last_done:
        lines.append(f"  ✅  Último completado: {last_done}")

    return "\n".join(lines)
