"""Registro centralizado de tools — B4 / R6-A

Cada entrada en TOOLS tiene:
  fn:          La función de app/tools.py a invocar.
  carril:      El nombre del carril devuelto por el router.
  descripcion: Descripción breve para !ayuda y futuras UIs.
  risk:        RiskLevel — clasificación de riesgo (R6-A).
               READ   → solo lectura, sin efectos secundarios.
               WRITE  → escribe en storage/ interno del agente.
               SYSTEM → accede a recursos externos (no hay ninguna actualmente).
  handler:     Función (user_input: str) -> str con toda la lógica de parseo
               y construcción de respuesta. Retorna str para compatibilidad
               con intelligence.py (via dispatch_tool_str).

API pública (R6-A):
  dispatch_tool(carril, user_input) -> ToolResult | None
      Retorna el ToolResult estructurado. Usar en tests y métricas.

  dispatch_tool_str(carril, user_input) -> str | None
      Wrapper de compatibilidad — convierte ToolResult.message a str.
      Usar en intelligence.py y cualquier caller que espere str.

Convención:
  - Los handlers reciben el user_input crudo y retornan la respuesta final.
  - suggest_next_step() es responsabilidad del handler de tool_update_work_state.
  - Cualquier fallo interno debe retornar un ToolResult con ok=False, nunca lanzar.

Regla de seguridad (R6-A):
  dispatch_tool() rechaza tools con risk=SYSTEM a menos que se agregue
  soporte explícito de confirmación humana (no implementado aún — hay
  0 tools SYSTEM en producción actualmente).
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
from app.schemas import RiskLevel, ToolResult, tool_result_to_str
from app import memory_manager


# ── Handlers ────────────────────────────────────────────────────────────────
# Los handlers convierten el texto libre del usuario a llamadas de tool
# y retornan str para la capa de presentación.
# Internamente llaman a la tool (que ahora retorna ToolResult) y
# extraen .message para mantener compatibilidad hacia afuera.

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
    return tool_result_to_str(tool_save_fact(content))


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
            return tool_result_to_str(tool_create_task(title=raw, priority=priority))
    return tool_result_to_str(tool_create_task(title=user_input, priority="medium"))


def _handle_complete_task(user_input: str) -> str:
    task_id = extract_task_id(user_input)
    if not task_id:
        return "No encontré el ID de la tarea. Indícalo así: 'marca T-002 como completada'"
    return tool_result_to_str(tool_complete_task(task_id))


def _handle_update_work_state(user_input: str) -> str:
    result = tool_update_work_state(user_input)
    suggestion = suggest_next_step()
    return tool_result_to_str(result) + suggestion


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
    """Extrae el objetivo del texto libre y lo guarda en work_state.

    Limpia los prefijos de activación para guardar solo el contenido real.
    Ejemplo: 'mi objetivo hoy es cerrar el Eje 1' → guarda 'cerrar el Eje 1'.
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
    for prefix in sorted(prefixes, key=len, reverse=True):
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
        "risk":        RiskLevel.READ,
        "handler":     _handle_list_files,
    },
    "tool_read_file": {
        "fn":          read_project_file,
        "carril":      "tool_read_file",
        "descripcion": "Lee el contenido de un archivo",
        "risk":        RiskLevel.READ,
        "handler":     _handle_read_file,
    },
    "tool_save_fact": {
        "fn":          tool_save_fact,
        "carril":      "tool_save_fact",
        "descripcion": "Guarda un hecho en project_facts.json",
        "risk":        RiskLevel.WRITE,
        "handler":     _handle_save_fact,
    },
    "tool_create_task": {
        "fn":          tool_create_task,
        "carril":      "tool_create_task",
        "descripcion": "Crea una tarea en tasks.json",
        "risk":        RiskLevel.WRITE,
        "handler":     _handle_create_task,
    },
    "tool_complete_task": {
        "fn":          tool_complete_task,
        "carril":      "tool_complete_task",
        "descripcion": "Marca una tarea como completada",
        "risk":        RiskLevel.WRITE,
        "handler":     _handle_complete_task,
    },
    "tool_update_work_state": {
        "fn":          tool_update_work_state,
        "carril":      "tool_update_work_state",
        "descripcion": "Actualiza work_state.json",
        "risk":        RiskLevel.WRITE,
        "handler":     _handle_update_work_state,
    },
    "tool_set_session_goal": {
        "fn":          memory_manager.set_session_goal,
        "carril":      "tool_set_session_goal",
        "descripcion": "Guarda el objetivo de la sesión actual en work_state.json",
        "risk":        RiskLevel.WRITE,
        "handler":     _handle_set_session_goal,
    },
}


def dispatch_tool(carril: str, user_input: str) -> ToolResult | None:
    """Despacha user_input al handler del carril indicado.

    R6-A: retorna ToolResult estructurado en vez de str.
    Usar en tests, métricas y cualquier código que necesite saber
    si la tool tuvo éxito de forma programática.

    Seguridad: rechaza tools con risk=SYSTEM (ninguna en producción actualmente).

    Args:
        carril:     Nombre del carril (ej. 'tool_save_fact').
        user_input: Texto crudo del usuario.

    Returns:
        ToolResult con ok=True/False, message, data, etc.
        None si el carril no está registrado en TOOLS.

    Never raises.
    """
    entry = TOOLS.get(carril)
    if entry is None:
        return None

    # Bloquear tools SYSTEM sin confirmación explícita
    if entry.get("risk") == RiskLevel.SYSTEM:
        return ToolResult(
            ok=False,
            message=f"⛔ La tool '{carril}' es de riesgo SYSTEM y requiere confirmación humana explícita.",
            error_code="SYSTEM_TOOL_BLOCKED",
            tool_name=carril,
        )

    try:
        result_str = entry["handler"](user_input)
        # Los handlers retornan str — envolvemos en ToolResult para consistencia
        return ToolResult(
            ok=True,
            message=result_str,
            tool_name=carril,
        )
    except Exception as exc:
        return ToolResult(
            ok=False,
            message=f"Error interno en {carril}: {exc}",
            error_code="INTERNAL_ERROR",
            tool_name=carril,
        )


def dispatch_tool_str(carril: str, user_input: str) -> str | None:
    """Wrapper de compatibilidad: retorna str en vez de ToolResult.

    Usar en intelligence.py y cualquier caller que espere str.
    Equivale al dispatch_tool() original antes de R6-A.

    Args:
        carril:     Nombre del carril.
        user_input: Texto crudo del usuario.

    Returns:
        str con la respuesta lista para mostrar al usuario.
        None si el carril no está registrado en TOOLS.

    Never raises.
    """
    result = dispatch_tool(carril, user_input)
    if result is None:
        return None
    return tool_result_to_str(result)
