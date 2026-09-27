from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from app.intelligence import process_turn
from app.logger import get_logger
from app.memory_manager import main_memory_flow
from app.metrics import record_turn
from app.schemas import DecisionResult, SourceRef, TurnContext, TurnResult
from app.session_state import SessionState


log = get_logger(__name__)

_MAX_HISTORY = 20


def _init_vectordb():
    try:
        from app.indexing_core import build_vectorstore

        return build_vectorstore()
    except Exception as exc:
        log.warning("No se pudo cargar vectordb: %s", exc)
        return None


def _trim_history(history: list, max_lines: int = _MAX_HISTORY) -> list:
    if len(history) > max_lines:
        return history[-max_lines:]
    return history


def _map_source_docs_to_refs(source_docs: list) -> list[SourceRef]:
    mapped: list[SourceRef] = []

    for doc in source_docs or []:
        metadata = getattr(doc, "metadata", {}) or {}

        mapped.append(
            SourceRef(
                source=metadata.get("source", "desconocido"),
                doc_type=metadata.get("doc_type", ""),
                section=metadata.get("section", ""),
            )
        )

    return mapped


def _estimate_tokens(text: str) -> int:
    """Estimación simple y estable para métricas locales."""
    if not text:
        return 0

    return int(len(text.split()) * 1.3)


def _record_turn_metrics(
    *,
    route: str,
    intent_type: str,
    channel: str,
    retrieval_ms: int,
    llm_ms: int,
    fidelity_ms: int,
    fidelity_status: str,
    cached: bool,
    num_docs: int,
    response: str,
) -> None:
    """Adaptador entre handle_turn() y el contrato actual de record_turn()."""
    try:
        record_turn(
            route=route,
            intent_type=intent_type,
            channel=channel,
            retrieval_ms=retrieval_ms,
            llm_ms=llm_ms,
            tokens_est=_estimate_tokens(response),
            cached=cached,
            num_docs=num_docs,
            fidelity_ms=fidelity_ms,
            fidelity_status=fidelity_status,
        )
    except Exception as exc:
        log.warning("No se pudo registrar métricas del turno: %s", exc)

def normalize_severity(value: str | None) -> str:
    mapping = {
        None: "normal",
        "normal": "normal",
        "warning": "warning",
        "warn": "warning",
        "peligro": "warning",
        "error": "error",
    }
    return mapping.get(str(value).strip().lower(), "normal")


def normalize_fidelity(value: str | None) -> str:
    mapping = {
        None: "not_applicable",
        "verified": "verified",
        "verificado": "verified",
        "unverified": "unverified",
        "no_verificado": "unverified",
        "unverifiable": "unverified",
        "not_applicable": "not_applicable",
        "not-applicable": "not_applicable",
        "no_aplicable": "not_applicable",
        "notapplicable": "not_applicable",
        "notrun": "not_applicable",
    }
    return mapping.get(str(value).strip().lower(), "not_applicable")

def handle_turn(
    user_input: str,
    chat_history: list,
    vectordb,
    channel: str = "cli",
    session: SessionState | None = None,
) -> TurnResult:
    from app.router import route_query

    try:
        route = route_query(user_input)

        ctx = TurnContext(
            route=route,
            query=user_input,
            vectordb=vectordb,
            chat_history=chat_history,
            channel=channel,
        )

        result: DecisionResult = process_turn(ctx)

        response = result.get("response", "")
        final_route = result.get("route", route)
        should_exit = final_route == "exit"
        source_docs = result.get("source_docs", [])
        sources = _map_source_docs_to_refs(source_docs)

        metadata = result.get("metadata", {}) or {}

        retrieval_ms = int(metadata.get("retrieval_ms", result.get("retrieval_ms", 0)) or 0)
        llm_ms = int(metadata.get("llm_ms", result.get("llm_ms", 0)) or 0)
        fidelity_ms = int(metadata.get("fidelity_ms", 0) or 0)

        severity = normalize_severity(metadata.get("severity"))
        fidelity_status = normalize_fidelity(metadata.get("fidelity_status"))
        intent_type = metadata.get("intent_type", final_route)
        cached = bool(result.get("cached", False))
        num_docs = len(source_docs)

        turn_result = TurnResult(
            text=response,
            should_exit=should_exit,
            severity=severity,
            route=final_route,
            fidelity=fidelity_status,
            sources=sources,
            cached=cached,
        )

        if session is not None and not should_exit:
            session.track_turn(final_route, tareas_nuevas=0)

        if not should_exit:
            chat_history.append(HumanMessage(content=user_input))
            chat_history.append(AIMessage(content=response))

            trimmed = _trim_history(chat_history)
            if trimmed is not chat_history:
                chat_history[:] = trimmed

        _record_turn_metrics(
            route=final_route,
            intent_type=intent_type,
            channel=channel,
            retrieval_ms=retrieval_ms,
            llm_ms=llm_ms,
            fidelity_ms=fidelity_ms,
            fidelity_status=fidelity_status,
            cached=cached,
            num_docs=num_docs,
            response=response,
        )

        return turn_result

    except Exception as exc:
        log.error("handle_turn error inesperado: %s", exc, exc_info=True)

        _record_turn_metrics(
            route="error",
            intent_type="error",
            channel=channel,
            retrieval_ms=0,
            llm_ms=0,
            fidelity_ms=0,
            fidelity_status="not_applicable",
            cached=False,
            num_docs=0,
            response="",
        )

        return TurnResult(
            text="Ocurrió un error interno. Por favor, intenta de nuevo.",
            should_exit=False,
            severity="error",
            route="error",
            fidelity="not_applicable",
            sources=[],
            cached=False,
        )


def handle_turn_legacy(
    user_input: str,
    chat_history: list,
    vectordb,
    channel: str = "cli",
    session: SessionState | None = None,
) -> tuple[str, bool]:
    """Compatibilidad temporal para consumidores que aún esperan tupla.

    Eliminar cuando CLI, Telegram y scripts migren completamente a TurnResult.
    """
    result = handle_turn(
        user_input=user_input,
        chat_history=chat_history,
        vectordb=vectordb,
        channel=channel,
        session=session,
    )

    return result.text, result.should_exit


def run_session(channel: str = "cli") -> None:
    vectordb = _init_vectordb()
    chat_history: list = []
    session = SessionState()

    try:
        new_tasks = main_memory_flow()

        if new_tasks:
            log.info(
                "main_memory_flow: %d tarea(s) nueva(s) registrada(s)",
                new_tasks,
            )
    except Exception as exc:
        log.warning("main_memory_flow falló al arrancar (no bloquea): %s", exc)

    print("Lautaro listo. Escribe 'salir' para terminar.")

    while True:
        try:
            user_input = input("Tú: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSesión interrumpida.")
            break

        if not user_input:
            continue
        result = handle_turn(
            user_input=user_input,
            chat_history=chat_history,
            vectordb=vectordb,
            channel=channel,
            session=session,
        )
        print(f"Lautaro: {result.text}")
        if result.should_exit:
            break

    log.info("Sesión terminada. Turnos=%d", session.turns)