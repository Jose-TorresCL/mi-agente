"""Orquestador de conversación.

Responsabilidad única: gestionar el flujo de sesión y el historial.
Delega TODO el procesamiento de intención a la capa de inteligencia.

Contrato público
─────────────────
    build_memory()   -> list[Message]
    handle_query(user_input, vectordb, chat_history) -> (str, list)

Dirección de dependencias:
    chat_core  →  intelligence  →  memory_manager / rag_engine / ...
    chat_core  NO importa router, rag_engine, fidelity_check ni tools directamente.

E3: process_turn ahora devuelve DecisionResult (TypedDict).
    handle_query desempaqueta result["response"] y result.get("source_docs", []).
    El contrato público de handle_query (str, list) no cambia.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import MAX_TURNS
from app.logger import get_logger
from app.intelligence import process_turn
from app.memory_manager import validate_memory_file
from app.schemas import TurnContext

from langchain_core.messages import HumanMessage, AIMessage

log = get_logger(__name__)

MEMORY_FILE = Path("storage/memory.json")


# ─────────────────────────────────────────────
# Historial de conversación
# ─────────────────────────────────────────────

def build_memory() -> list:
    """Lee el historial desde memory.json."""
    validate_memory_file()
    if not MEMORY_FILE.exists():
        return []
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        messages = []
        for m in data.get("messages", [])[-(MAX_TURNS * 2):]:
            if m.get("role") == "human":
                messages.append(HumanMessage(content=m["content"]))
            elif m.get("role") == "ai":
                messages.append(AIMessage(content=m["content"]))
        return messages
    except Exception as exc:
        log.warning("No se pudo leer memory.json: %s", exc)
        return []


def _persist_turn(user_input: str, answer: str) -> None:
    """Agrega un turno al historial persistente."""
    if MEMORY_FILE.exists():
        try:
            data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(data.get("messages"), list):
                data = {"messages": []}
        except Exception:
            data = {"messages": []}
    else:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"messages": []}
    data["messages"].append({"role": "human", "content": user_input})
    data["messages"].append({"role": "ai",    "content": answer})
    if len(data["messages"]) > MAX_TURNS * 2:
        data["messages"] = data["messages"][-(MAX_TURNS * 2):]
    MEMORY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ─────────────────────────────────────────────
# Punto de entrada público
# ─────────────────────────────────────────────

def handle_query(
    user_input: str,
    vectordb: Any,
    chat_history: list,
    channel: str = "cli",
) -> tuple[str, list]:
    """Clasifica la consulta, construye TurnContext y delega a process_turn().

    TurnContext agrupa los 4 parámetros del turno en un dict tipado.
    process_turn() devuelve DecisionResult — se desempaquetan response y
    source_docs para mantener el contrato público (str, list) de handle_query.

    Returns:
        (respuesta, source_docs)  — source_docs puede ser lista vacía.
    """
    from app.router import route_query
    route = route_query(user_input)
    log.debug("Ruta asignada: '%s' para: %s", route, user_input[:60])

    # Construir TurnContext — contrato de entrada tipado
    ctx = TurnContext(
        route=route,
        query=user_input,
        vectordb=vectordb,
        chat_history=chat_history,
        channel=channel,
    )

    # Delegar procesamiento completo a la capa de inteligencia
    # E3: process_turn devuelve DecisionResult — desempaquetar campos explícitos
    result      = process_turn(ctx)
    answer      = result["response"]
    source_docs = result.get("source_docs", [])

    # Log de métricas disponibles desde DecisionResult
    log.debug(
        "[handle_query] route=%s source=%s cached=%s llm_ms=%s retrieval_ms=%s",
        result.get("route"), result.get("source"), result.get("cached"),
        result.get("llm_ms"), result.get("retrieval_ms"),
    )

    # Persistir historial solo si no es exit ni respuesta de error de fidelidad
    if answer != "__EXIT__":
        _persist_turn(user_input, answer)
        chat_history.append(HumanMessage(content=user_input))
        chat_history.append(AIMessage(content=answer))
        while len(chat_history) > MAX_TURNS * 2:
            chat_history.pop(0)

    return answer, source_docs
