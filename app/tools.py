"""Herramientas que modifican el estado del asistente.

Este módulo contiene SOLO las funciones tool_* que leen/escriben memoria.
Las utilidades de parseo y filesystem viven en tool_helpers.py.

Funciones públicas (sin cambio de interfaz externa — retornan ToolResult):
  tool_save_fact()          — guarda hecho en project_facts.json
  tool_create_task()        — crea tarea en tasks.json
  tool_complete_task()      — marca tarea como completada
  tool_update_work_state()  — actualiza work_state.json
  tool_set_session_goal()   — guarda objetivo de la sesión actual

Re-exporta desde tool_helpers para compatibilidad con imports existentes:
  list_project_files, extract_file_path, read_project_file,
  extract_task_id, parse_work_state_update, VALID_PRIORITIES

Cambio R6-A:
  Todas las tool_* retornan ToolResult (schemas.py) en lugar de str crudo.
  Esto permite detección programática de éxito/error sin parsear emojis.
  tool_registry.dispatch_tool_str() convierte a str para intelligence.py —
  la interfaz pública no cambia.

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
    set_session_goal as _mm_set_session_goal,
)
from app.schemas import ToolResult

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

def tool_save_fact(content) -> ToolResult:
    """Guarda un hecho en project_facts.json.

    Fix B2: acepta cualquier tipo en 'content' y fuerza str() antes de
    operar, evitando 'int object has no attribute strip'.

    D3: rechaza contenido vacío antes de llamar a memory_manager.save_fact.

    R6-A: retorna ToolResult con ok, message, data, side_effect, error_code.
    """
    content = str(content).strip()

    if not content:
        return ToolResult(
            ok=False,
            message="No pude guardar el hecho: el contenido está vacío.",
            error_code="EMPTY_CONTENT",
            tool_name="tool_save_fact",
        )

    kv = _parse_key_value(content)
    if kv:
        key, value = kv
        ok = _mm_save_fact(key, value)
        if ok:
            return ToolResult(
                ok=True,
                message=f'✓ Hecho guardado: {key} = "{value}"',
                data={"key": key, "value": value},
                side_effect="escrito project_facts.json",
                tool_name="tool_save_fact",
            )
        return ToolResult(
            ok=False,
            message="No pude guardar el hecho: clave o valor vacíos.",
            error_code="EMPTY_KEY_OR_VALUE",
            tool_name="tool_save_fact",
        )

    key = f"hecho_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    ok = _mm_save_fact(key, content)
    if ok:
        return ToolResult(
            ok=True,
            message=f'✓ Hecho guardado: "{content}"',
            data={"key": key, "value": content},
            side_effect="escrito project_facts.json",
            tool_name="tool_save_fact",
        )
    return ToolResult(
        ok=False,
        message="No pude guardar el hecho: contenido vacío.",
        error_code="EMPTY_CONTENT",
        tool_name="tool_save_fact",
    )


# ─────────────────────────────────────────────
# Tool: crear tarea
# ─────────────────────────────────────────────

def tool_create_task(title: str, priority: str = "medium", notes: str = "") -> ToolResult:
    """R6-A: retorna ToolResult con task_id en data."""
    title    = title.strip()
    priority = priority.strip().lower()
    notes    = notes.strip()

    if not title:
        return ToolResult(
            ok=False,
            message="No pude crear la tarea: falta el título.",
            error_code="EMPTY_TITLE",
            tool_name="tool_create_task",
        )

    task_id = _mm_create_task(title=title, priority=priority, notes=notes)
    if not task_id:
        return ToolResult(
            ok=False,
            message="No pude crear la tarea: título vacío.",
            error_code="EMPTY_TITLE",
            tool_name="tool_create_task",
        )
    return ToolResult(
        ok=True,
        message=f"✓ Tarea creada: [{task_id}] {title} (prioridad: {priority})",
        data={"task_id": task_id, "title": title, "priority": priority},
        side_effect=f"creado {task_id} en tasks.json",
        tool_name="tool_create_task",
    )


# ─────────────────────────────────────────────
# Tool: completar tarea
# ─────────────────────────────────────────────

def tool_complete_task(task_id: str) -> ToolResult:
    """R6-A: retorna ToolResult con was_already_completed en data."""
    if not task_id:
        return ToolResult(
            ok=False,
            message="No pude identificar el ID de la tarea. Indícalo así: T-001, T-002...",
            error_code="MISSING_TASK_ID",
            tool_name="tool_complete_task",
        )

    tasks_data = _mm_get_tasks()
    tasks = tasks_data.get("tasks", [])

    found = False
    for task in tasks:
        if task.get("id", "").upper() == task_id.upper():
            if task.get("status") == "completed":
                return ToolResult(
                    ok=True,
                    message=f"ℹ️  La tarea {task_id} ya estaba marcada como completada.",
                    data={"task_id": task_id, "was_already_completed": True},
                    tool_name="tool_complete_task",
                )
            found = True
            break

    if not found:
        available = [t.get("id") for t in tasks]
        return ToolResult(
            ok=False,
            message=f"❌ No encontré la tarea '{task_id}'. Tareas disponibles: {available}",
            error_code="TASK_NOT_FOUND",
            data={"task_id": task_id, "available_ids": available},
            tool_name="tool_complete_task",
        )

    _mm_complete_task(task_id)
    return ToolResult(
        ok=True,
        message=f"✅ Tarea {task_id} marcada como completada.",
        data={"task_id": task_id, "was_already_completed": False},
        side_effect=f"actualizado {task_id} en tasks.json",
        tool_name="tool_complete_task",
    )


# ─────────────────────────────────────────────
# Tool: actualizar work_state
# ─────────────────────────────────────────────

def tool_update_work_state(
    texto: str = "",
    *,
    current_focus: str | None = None,
    next_step: str | None = None,
    last_completed_step: str | None = None,
) -> ToolResult:
    """Actualiza work_state.json desde conversación libre o desde kwargs directos.

    R6-A: retorna ToolResult con lista de cambios en data.
    """
    import json

    path = Path("storage/work_state.json")
    try:
        state: dict = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        state = {}

    cambios: list[str] = []

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

    if texto:
        texto_lower = texto.lower()

        if current_focus is None:
            patrones_foco = [r"(?:actualiza el foco a|foco(?:\s+es)?(?:\s*:)?|enf[oó]cate en)\s+(.+)"]
            for pat in patrones_foco:
                m = re.search(pat, texto_lower)
                if m:
                    valor = m.group(1).strip().rstrip(".,'")
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
                    valor = m.group(1).strip().rstrip(".,'")
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
                    valor = m.group(1).strip().rstrip(".,'")
                    if valor:
                        state["next_step"] = valor
                        cambios.append(f"next_step → '{valor}'")
                    break

    if not cambios:
        return ToolResult(
            ok=False,
            message="⚠️ No entendí qué campo actualizar. Usa: 'foco a X', 'completé X' o 'siguiente paso es X'.",
            error_code="NO_FIELDS_DETECTED",
            tool_name="tool_update_work_state",
        )

    state["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return ToolResult(
            ok=False,
            message=f"⚠️ Cambios detectados pero no pude escribir work_state.json: {e}",
            error_code="WRITE_ERROR",
            data={"cambios_detectados": cambios},
            tool_name="tool_update_work_state",
        )

    return ToolResult(
        ok=True,
        message="✅ work_state actualizado:\n" + "\n".join(f"  • {c}" for c in cambios),
        data={"campos_actualizados": cambios},
        side_effect="escrito work_state.json",
        tool_name="tool_update_work_state",
    )


# ─────────────────────────────────────────────
# Tool: definir objetivo de sesión (Paso B)
# ─────────────────────────────────────────────

def tool_set_session_goal(content: str) -> ToolResult:
    """Guarda el objetivo específico para la sesión actual.

    R6-A: retorna ToolResult con goal en data.
    Never raises.
    """
    content = str(content).strip()
    if not content:
        return ToolResult(
            ok=False,
            message="No pude guardar el objetivo: el contenido está vacío.",
            error_code="EMPTY_CONTENT",
            tool_name="tool_set_session_goal",
        )

    _QUESTION_STARTS = (
        "cuál es", "cual es", "cuál", "qué es", "que es",
        "dime", "muéstrame", "muestrame", "cuéntame", "cuentame",
    )
    if content.lower().startswith(_QUESTION_STARTS) or content.endswith("?"):
        return ToolResult(
            ok=False,
            message="ℹ️ No detecté un objetivo concreto. Dime: 'mi objetivo hoy es…'",
            error_code="DETECTED_AS_QUESTION",
            tool_name="tool_set_session_goal",
        )

    _mm_set_session_goal(content)
    return ToolResult(
        ok=True,
        message=f"✅ Objetivo de sesión guardado: '{content}'",
        data={"goal": content},
        side_effect="escrito session_goal en work_state.json",
        tool_name="tool_set_session_goal",
    )


# ─────────────────────────────────────────────
# Sugerencia automática post-actualización
# (no es tool pública — retorna str, sin ToolResult)
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
