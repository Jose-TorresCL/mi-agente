"""Registro centralizado de tools — B4

Cada entrada en TOOLS tiene:
  fn:          La función de app/tools.py a invocar.
  carril:      El nombre del carril devuelto por el router.
  descripcion: Descripción breve para !ayuda y futuras UIs.
  handler:     Función (user_input: str) -> str con toda la lógica de parseo
               y construcción de respuesta. Centraliza lo que antes vivía
               disperso en los if/elif de chat_core.handle_query.

Convención:
  - Los handlers reciben el user_input crudo y retornan la respuesta final.
  - suggest_next_step() es responsabilidad del handler de tool_update_work_state.
  - Cualquier fallo interno debe retornar un str descriptivo, nunca lanzar.

Fix B2:
  _handle_save_fact retorna mensaje claro si content queda vacío tras
  limpiar prefijos, en lugar de pasar string vacío a memory_manager.

Brecha 2 (este commit):
  _handle_set_session_goal extrae el objetivo del texto libre del usuario
  y llama a memory_manager.set_session_goal(). intelligence.py no necesita
  cambio porque el bloque 'if route in TOOLS' ya maneja el carril.
"""
from __future__ import annotations

from app.tools import (
    list_project_files,
    read_project_file,
    extract_file_path,
    tool_save_fact,
    tool_create_task,
    tool_complete_task,
    tool_update_work_state,
    suggest_next_step,
    extract_task_id,
)
from app import memory_manager


# ── Handlers ────────────────────────────────────────────────────────────────

def _handle_save_fact(user_input: str) -> str:
    prefixes = [
        "guarda como hecho que", "guarda como hecho:", "guarda como hecho",
        "guardar hecho que", "registra que", "anota que",
        "guarda el hecho que", "registra el hecho que",
        "guarda esto como hecho:", "guarda esto como hecho",
    ]
    content = user_input.strip()
    for prefix in prefixes:
        if content.lower().startswith(prefix):
            content = content[len(prefix):].strip()
            break

    if not content:
        return (
            "No entendí qué hecho querías guardar. "
            "Prueba con: 'guarda como hecho que el router ya está probado'."
        )
    return tool_save_fact(content)


def _handle_create_task(user_input: str) -> str:
    text = user_input.lower()
    for prefix in [
        "crea una tarea:", "crea una tarea", "crear tarea:", "crear tarea",
        "agrega una tarea:", "agrega una tarea", "nueva tarea:", "nueva tarea",
        "áñade una tarea:", "áñade una tarea", "anota una tarea:", "anota una tarea",
        "registra una tarea:", "registra una tarea",
    ]:
        if text.startswith(prefix):
            raw = user_input[len(prefix):].strip()
            priority = "medium"
            for p in ["alta", "high", "baja", "low", "media", "medium"]:
                if raw.lower().endswith(p):
                    raw = raw[:-len(p)].strip().rstrip(",;")
                    priority = {"alta": "high", "baja": "low", "media": "medium"}.get(p, p)
                    break
            return tool_create_task(title=raw, priority=priority)
    return tool_create_task(title=user_input, priority="medium")


def _handle_complete_task(user_input: str) -> str:
    task_id = extract_task_id(user_input)
    if not task_id:
        return "No encontré el ID de la tarea. Indícalo así: 'marca T-002 como completada'"
    return tool_complete_task(task_id)


def _handle_update_work_state(user_input: str) -> str:
    update_msg = tool_update_work_state(user_input)
    suggestion  = suggest_next_step()
    return update_msg + suggestion


def _handle_list_files(user_input: str) -> str:  # noqa: ARG001
    files = list_project_files()
    if not files:
        return "No encontré archivos en las carpetas permitidas."
    return "Archivos del proyecto:\n" + "\n".join(f"- {f}" for f in files)


def _handle_read_file(user_input: str) -> str:
    path = extract_file_path(user_input)
    if not path:
        return "No pude identificar qué archivo querías leer."
    return read_project_file(path)


def _handle_set_session_goal(user_input: str) -> str:
    """Brecha 2: extrae el objetivo del texto libre y lo guarda en work_state.

    Limpia los prefijos de activación para guardar solo el contenido real.
    Ejemplo: 'mi objetivo hoy es cerrar el Eje 1' → guarda 'cerrar el Eje 1'.
    Los prefijos se evalúan de mayor a menor longitud para evitar coincidencias
    parciales (ej. 'mi objetivo hoy' no debe comer 'mi objetivo hoy es X').
    """
    prefixes = [
        "mi objetivo hoy es",
        "mi objetivo para hoy es",
        "objetivo de esta sesion es",
        "objetivo de esta sesión es",
        "objetivo de hoy es",
        "objetivo de hoy:",
        "quiero lograr hoy",
        "quiero lograr esta sesion",
        "quiero lograr esta sesión",
        "meta de hoy es",
        "meta de esta sesion es",
        "meta de esta sesión es",
        "hoy quiero",
        "en esta sesion quiero",
        "en esta sesión quiero",
        "define mi objetivo:",
        "define mi objetivo",
        "guarda mi objetivo:",
        "guarda mi objetivo",
        "mi meta hoy es",
        "mi meta hoy",
        "mi objetivo hoy",
        "objetivo de hoy",
    ]
    content = user_input.strip()
    content_lower = content.lower()
    for prefix in sorted(prefixes, key=len, reverse=True):  # más largos primero
        if content_lower.startswith(prefix):
            content = content[len(prefix):].strip().lstrip(":").strip()
            break

    if not content:
        return (
            "No entendí cuál es tu objetivo. "
            "Prueba con: 'mi objetivo hoy es cerrar el Eje 1'."
        )

    memory_manager.set_session_goal(content)
    return f"✅ Objetivo de sesión guardado: '{content}'"


# ── Registro ──────────────────────────────────────────────────────────────────

TOOLS: dict[str, dict] = {
    "tool_list_files": {
        "fn":          list_project_files,
        "carril":      "tool_list_files",
        "descripcion": "Lista archivos del proyecto",
        "handler":     _handle_list_files,
    },
    "tool_read_file": {
        "fn":          read_project_file,
        "carril":      "tool_read_file",
        "descripcion": "Lee el contenido de un archivo",
        "handler":     _handle_read_file,
    },
    "tool_save_fact": {
        "fn":          tool_save_fact,
        "carril":      "tool_save_fact",
        "descripcion": "Guarda un hecho en project_facts.json",
        "handler":     _handle_save_fact,
    },
    "tool_create_task": {
        "fn":          tool_create_task,
        "carril":      "tool_create_task",
        "descripcion": "Crea una tarea en tasks.json",
        "handler":     _handle_create_task,
    },
    "tool_complete_task": {
        "fn":          tool_complete_task,
        "carril":      "tool_complete_task",
        "descripcion": "Marca una tarea como completada",
        "handler":     _handle_complete_task,
    },
    "tool_update_work_state": {
        "fn":          tool_update_work_state,
        "carril":      "tool_update_work_state",
        "descripcion": "Actualiza work_state.json",
        "handler":     _handle_update_work_state,
    },
    "tool_set_session_goal": {
        "fn":          memory_manager.set_session_goal,
        "carril":      "tool_set_session_goal",
        "descripcion": "Guarda el objetivo de la sesión actual en work_state.json",
        "handler":     _handle_set_session_goal,
    },
}


def dispatch_tool(carril: str, user_input: str) -> str | None:
    """Despacha user_input al handler del carril indicado.

    Args:
        carril:     Nombre del carril (ej. 'tool_save_fact').
        user_input: Texto crudo del usuario.

    Returns:
        str con la respuesta lista para mostrar al usuario,
        o None si el carril no está registrado en TOOLS.

    Never raises.
    """
    entry = TOOLS.get(carril)
    if entry is None:
        return None
    try:
        return entry["handler"](user_input)
    except Exception as exc:
        return f"Error interno en {carril}: {exc}"
