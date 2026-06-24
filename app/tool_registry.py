"""Registro centralizado de tools — B4 / R6-A

Cada entrada en TOOLS tiene:
  fn:          La función de app/tools.py a invocar.
  carril:      El nombre del carril devuelto por el router.
  descripcion: Descripción breve para !ayuda y futuras UIs.
  risk:        RiskLevel — clasificación de riesgo (R6-A).
               READ   → solo lectura, sin efectos secundarios.
               WRITE  → escribe en storage/ interno del agente.
               SYSTEM → accede a recursos externos.
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
  soporte explícito de confirmación humana (no implementado aún).

  EXCEPCIÓN: tool_analizar_mercado tiene risk=SYSTEM pero es de solo lectura
  (solo llama a consulta_mercado.py, nunca ejecuta órdenes).
  Para habilitarla: cambiar su entry a risk=RiskLevel.READ una vez que el
  subprocess esté probado manualmente con:
    C:\\Users\\lenovo\\Proyectos\\bot_trading\\.venv\\Scripts\\python.exe consulta_mercado.py --symbol BTCUSDT
  y confirmes que devuelve JSON válido.
"""
from __future__ import annotations

import re

from app.tools import (
    list_project_files,
    read_project_file,
    extract_file_path,
    tool_save_fact,
    tool_create_task,
    tool_complete_task,
    tool_update_work_state,
    tool_analizar_mercado,
    suggest_next_step,
    extract_task_id,
)
from app.schemas import RiskLevel, ToolResult, tool_result_to_str
from app import memory_manager


# ── Handlers ──────────────────────────────────────────────

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
        "agregar tarea:", "agregar tarea",
    ]:
        if text.startswith(prefix):
            raw = user_input[len(prefix):].strip()
            priority = "medium"

            match = re.search(
                r",?\s*prioridad\s+(alta|high|baja|low|media|medium)\b",
                raw,
                flags=re.IGNORECASE,
            )
            if match:
                p = match.group(1).lower()
                priority = {"alta": "high", "baja": "low", "media": "medium"}.get(p, p)
                raw = re.sub(
                    r",?\s*prioridad\s+\S+", "", raw, flags=re.IGNORECASE
                ).strip().rstrip(",;\u2014 ").strip()
            else:
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


def _handle_list_files(user_input: str) -> str:
    files = list_project_files()
    if not files:
        return "No encontré archivos en las carpetas permitidas."

    ext_filter = None
    u = user_input.lower()
    if ".md" in u or "markdown" in u:
        ext_filter = ".md"
    elif ".py" in u or "python" in u:
        ext_filter = ".py"
    elif ".json" in u:
        ext_filter = ".json"

    if ext_filter:
        files = [f for f in files if f.lower().endswith(ext_filter)]
        if not files:
            return f"No encontré archivos {ext_filter} en las carpetas permitidas."
        return f"Archivos {ext_filter} del proyecto:\n" + "\n".join(f"- {f}" for f in files)

    return "Archivos del proyecto:\n" + "\n".join(f"- {f}" for f in files)


def _handle_read_file(user_input: str) -> str:
    path = extract_file_path(user_input)
    if not path:
        return "No pude identificar qué archivo querías leer."
    return read_project_file(path)


def _handle_set_session_goal(user_input: str) -> str:
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


def _handle_analizar_mercado(user_input: str) -> str:
    """Extrae el símbolo del texto libre y llama a tool_analizar_mercado.

    Normaliza: 'btc', 'bitcoin', 'BTC', 'BTCUSDT' → todo pasa por _normalizar_simbolo.
    Fallback a BTCUSDT si no detecta símbolo.

    Keywords que activan esta tool via router (configuradas en router_config.py):
      mercado, precio, btc, bitcoin, eth, ethereum, señal, indicadores,
      trading, binance, cripto, criptomoneda
    """
    from app.tools_trading import _normalizar_simbolo

    # Buscar ticker en el texto
    u = user_input.lower()
    symbol = "BTCUSDT"  # fallback
    for term, ticker in [
        ("btcusdt", "BTCUSDT"), ("ethusdt", "ETHUSDT"), ("bnbusdt", "BNBUSDT"),
        ("bitcoin", "BTCUSDT"), ("ethereum", "ETHUSDT"),
        ("btc", "BTCUSDT"), ("eth", "ETHUSDT"), ("bnb", "BNBUSDT"),
        ("sol", "SOLUSDT"), ("solana", "SOLUSDT"),
        ("xrp", "XRPUSDT"), ("ada", "ADAUSDT"), ("doge", "DOGEUSDT"),
    ]:
        if term in u:
            symbol = ticker
            break

    result = tool_analizar_mercado(symbol=symbol)
    return tool_result_to_str(result)


# ── Registro ────────────────────────────────────────────────

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
    "tool_analizar_mercado": {
        "fn":          tool_analizar_mercado,
        "carril":      "tool_analizar_mercado",
        "descripcion": "Consulta precio, indicadores y señal del mercado vía bot_trading",
        "risk":        RiskLevel.SYSTEM,   # ← cambiar a READ después de probar el subprocess
        "handler":     _handle_analizar_mercado,
        "keywords":    ["mercado", "precio", "btc", "bitcoin", "eth", "ethereum",
                        "señal", "indicadores", "trading", "binance", "cripto"],
    },
}


def dispatch_tool(carril: str, user_input: str) -> ToolResult | None:
    """Despacha user_input al handler del carril indicado.

    R6-A: retorna ToolResult estructurado en vez de str.

    Seguridad: rechaza tools con risk=SYSTEM (ninguna en producción actualmente).
    La tool_analizar_mercado está en SYSTEM hasta que el subprocess
    sea probado manualmente y se cambie a READ.

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

    if entry.get("risk") == RiskLevel.SYSTEM:
        return ToolResult(
            ok=False,
            message=(
                f"⛔ La tool '{carril}' está en modo SYSTEM (acceso externo). "
                "Para habilitarla: probar el subprocess manualmente y cambiar "
                "risk a RiskLevel.READ en tool_registry.py."
            ),
            error_code="SYSTEM_TOOL_BLOCKED",
            tool_name=carril,
        )

    try:
        result_str = entry["handler"](user_input)
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
    """Wrapper de compatibilidad: retorna str en vez de ToolResult."""
    result = dispatch_tool(carril, user_input)
    if result is None:
        return None
    return tool_result_to_str(result)
