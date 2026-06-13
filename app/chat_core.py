"""Núcleo de la sesión de chat — orquestador de turno por turno.

Responsabilidades:
  - Inicializar la sesión (vectordb, historial, estado).
  - Construir el TurnContext para cada turno y delegarlo a intelligence.py.
  - Actualizar el historial de conversación después de cada turno.
  - Emitir el resumen episódico al cerrar la sesión.

NO conoce la UI (chat_ui.py, telegram_bot.py) — solo recibe strings
y devuelve strings. La capa de presentación es responsabilidad del llamador.

Contrato público:
  run_session(channel)          → bucle interactivo de CLI
  handle_turn(ctx) → str        → procesa un turno y devuelve la respuesta
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, AIMessage

from app.intelligence import process_turn
from app.logger import get_logger
from app.memory_manager import main_memory_flow
from app.schemas import TurnContext

log = get_logger(__name__)

_MAX_HISTORY = 20   # líneas totales (10 turnos usuario+asistente)


def _init_vectordb():
    """Inicializa y devuelve el vectorstore Chroma.

    Importación tardía para evitar cargar Chroma en tests unitarios
    que no necesitan el vectordb. Devuelve None si Chroma no está
    disponible o si el índice todavía no existe.

    Returns:
        Instancia de Chroma lista para consultar, o None si falla.
    """
    try:
        from app.indexing_core import load_vectordb
        return load_vectordb()
    except Exception as exc:
        log.warning("No se pudo cargar vectordb: %s", exc)
        return None


def _trim_history(history: list, max_lines: int = _MAX_HISTORY) -> list:
    """Recorta el historial al máximo de líneas configurado.

    Mantiene siempre los mensajes más recientes (últimos max_lines).
    Necesario para no superar el context window del LLM en sesiones largas.

    Args:
        history:   Lista de HumanMessage / AIMessage de LangChain.
        max_lines: Máximo de mensajes a conservar. Por defecto _MAX_HISTORY (20).

    Returns:
        Lista con como máximo max_lines mensajes (los más recientes).
    """
    if len(history) > max_lines:
        return history[-max_lines:]
    return history


def handle_turn(
    user_input: str,
    chat_history: list,
    vectordb,
    channel: str = "cli",
    session: session_state.SessionState | None = None,
) -> tuple[str, bool]:
    """Procesa un turno completo y devuelve la respuesta del asistente.

    Construye el TurnContext, invoca process_turn() de intelligence.py
    y actualiza el historial de conversación con el par usuario/asistente.

    Args:
        user_input:   Texto del mensaje del usuario.
        chat_history: Lista mutable de mensajes (se modifica in-place).
        vectordb:     Instancia de Chroma o None si no está disponible.
        channel:      Canal de origen ('cli', 'telegram'). Por defecto 'cli'.
        session:      Estado de sesión opcional (para tracking de estadísticas).

    Returns:
        Tuple (response, should_exit):
          response     → str con la respuesta del asistente.
          should_exit  → True si el carril fue 'exit' y la sesión debe cerrarse.

    Nunca lanza excepciones — los errores se capturan y se devuelve un
    mensaje de error genérico al usuario.
    """
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
        result = process_turn(ctx)
        response = result["response"]
        should_exit = result["route"] == "exit"

        if not should_exit:
            chat_history.append(HumanMessage(content=user_input))
            chat_history.append(AIMessage(content=response))
            _trim_history(chat_history)

        return response, should_exit

    except Exception as exc:
        log.error("handle_turn error inesperado: %s", exc, exc_info=True)
        return "Ocurrió un error interno. Por favor, intenta de nuevo.", False


def run_session(channel: str = "cli") -> None:
    """Inicia y mantiene el bucle de sesión interactiva desde CLI.

    Secuencia de arranque:
      1. Inicializa vectordb (Chroma).
      2. Ejecuta main_memory_flow() para sugerir tareas desde episodios.
      3. Entra en el bucle interactivo: leer input → handle_turn → imprimir.
      4. Cierra al recibir señal de exit o KeyboardInterrupt.

    Args:
        channel: Canal de la sesión ('cli' por defecto). Se pasa a handle_turn
                 para que las métricas reflejen el canal correcto.

    Esta función es el punto de entrada para `python -m app.chat_core`
    y para scripts de prueba manual. La UI de Telegram usa handle_turn
    directamente sin llamar a run_session.
    """
    vectordb     = _init_vectordb()
    chat_history: list = []
    session      = SessionState()

    # Flujo de mantenimiento de memoria al arranque
    try:
        new_tasks = main_memory_flow()
        if new_tasks:
            log.info("main_memory_flow: %d tarea(s) nueva(s) registrada(s)", new_tasks)
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

        response, should_exit = handle_turn(
            user_input, chat_history, vectordb,
            channel=channel, session=session,
        )
        print(f"Lautaro: {response}")

        if should_exit:
            break

    log.info("Sesión terminada. Turnos: %d", session.turns if session else 0)
