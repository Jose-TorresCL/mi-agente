"""Punto de entrada del asistente.

Arranca el loop de conversación, gestiona el vectorstore
y delega cada turno a chat_core.handle_turn().

Auto-reindex: al arrancar detecta si hay docs más nuevos que el índice
y re-indexa automáticamente antes de abrir el chat.

8C: al cerrar sesión (exit normal o Ctrl+C) llama a
    episode_store.close_session_episode() para preguntar al usuario si
    la sesión fue productiva y marcar el episodio en experience_index.

Session Intelligence (Pasos A-D):
    Tras el banner y antes del primer input, construye y muestra
    el session briefing con estado clasificado, tareas y episodio anterior.
    Sin LLM — solo JSON. Si falla, no bloquea el arranque.
    Objetivo: < 200ms adicionales.

Cierre limpio:
    _session_close() guarda el episodio y libera el modelo LLM de RAM
    via 'ollama stop'. Esto complementa keep_alive=-1 en llm_client.py:
    el modelo vive en RAM durante la sesión y se descarga al salir.
"""
from __future__ import annotations

import subprocess

from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.messages import BaseMessage

from app.config import CHROMA_DIR, OLLAMA_URL, MODEL_NAME
from app.indexing_core import needs_reindex, run_full_index
from app.chat_core import handle_turn
from app.chat_ui import print_welcome, format_answer, mostrar_briefing
from app.memory_manager import get_session_briefing
from app.logger import get_logger

log = get_logger(__name__)

EMBED_MODEL = "nomic-embed-text"


def _load_vectorstore() -> Chroma:
    """Carga el vectorstore existente sin re-indexar."""
    embeddings = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_URL)
    return Chroma(
        persist_directory=CHROMA_DIR,
        embedding_function=embeddings,
    )


def _boot_vectorstore() -> Chroma:
    """Decide si hay que re-indexar y devuelve el vectorstore listo."""
    should_reindex, reason = needs_reindex()

    if should_reindex:
        print(f"\n🔄  Detectados cambios en data/docs/ ({reason})")
        print("    Actualizando el índice automáticamente...\n")
        db = run_full_index()
        print("✅  Índice actualizado. Iniciando chat...\n")
    else:
        log.info("[boot] %s — cargando índice existente", reason)
        db = _load_vectorstore()

    return db


def _stop_llm_model() -> None:
    """Descarga el modelo LLM de RAM al cerrar la sesión.

    Complementa keep_alive=-1: el modelo vive en RAM durante la sesión
    y se libera explícitamente aquí para no ocupar ~5.5 GB en segundo
    plano cuando Lautaro no está en uso.

    Falla silenciosamente — nunca bloquea el cierre del programa.
    """
    try:
        subprocess.run(
            ["ollama", "stop", MODEL_NAME],
            capture_output=True,
            timeout=5,
        )
        log.info("[chat] modelo %s descargado de RAM", MODEL_NAME)
    except Exception as exc:
        log.debug("[chat] ollama stop falló (no crítico): %s", exc)


def _session_close() -> None:
    """Hook de cierre de sesión (8C)."""
    try:
        from app.episode_store import close_session_episode
        close_session_episode()
    except Exception as exc:
        log.debug("[chat] _session_close: %s", exc)

    _stop_llm_model()


def main() -> None:
    print_welcome()

    # Session Intelligence: mostrar briefing antes del primer input
    # Sin LLM — solo JSON. Si falla, no bloquea el arranque.
    try:
        briefing = get_session_briefing()
        mostrar_briefing(briefing)
    except Exception as exc:
        log.debug("[chat] session briefing no disponible: %s", exc)

    vectordb: Chroma = _boot_vectorstore()
    chat_history: list[BaseMessage] = []

    while True:
        try:
            user_input = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            _session_close()
            print("\n👋 ¡Hasta luego!")
            break

        if not user_input:
            continue

        response, should_exit = handle_turn(
            user_input,
            chat_history,
            vectordb,
            channel="cli",
        )

        if should_exit:
            _session_close()
            print("\n👋 ¡Hasta luego!")
            break

        if response:
            print(format_answer(response))


if __name__ == "__main__":
    main()
