"""Punto de entrada del asistente.

Arranca el loop de conversación, gestiona el vectorstore
y delega cada turno a chat_core.handle_query().

Auto-reindex: al arrancar detecta si hay docs más nuevos que el índice
y re-indexa automáticamente antes de abrir el chat.

8C: al cerrar sesión (exit normal o Ctrl+C) llama a
    episode_store.close_session_episode() para preguntar al usuario si
    la sesión fue productiva y marcar el episodio en experience_index.

Session Intelligence (Pasos A-D):
    Tras el banner y antes del primer input, construye y muestra
    el session briefing con estado clasificado, tareas y episodio anterior.
    Sin LLM — solo lectura de JSON. Objetivo: < 200ms adicionales.
"""
from __future__ import annotations

from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

from app.config import CHROMA_DIR, OLLAMA_URL
from app.indexing_core import needs_reindex, run_full_index
from app.chat_core import build_memory, handle_query
from app.chat_ui import print_welcome, print_sources, format_answer, mostrar_briefing
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


def _session_close() -> None:
    """Hook de cierre de sesión (8C)."""
    try:
        from app.episode_store import close_session_episode
        close_session_episode()
    except Exception as exc:
        log.debug("[chat] _session_close: %s", exc)


def main() -> None:
    print_welcome()

    # Session Intelligence: mostrar briefing antes del primer input
    # Sin LLM — solo JSON. Si falla, no bloquea el arranque.
    try:
        briefing = get_session_briefing()
        mostrar_briefing(briefing)
    except Exception as exc:
        log.debug("[chat] session briefing no disponible: %s", exc)

    vectordb     = _boot_vectorstore()
    chat_history = build_memory()

    while True:
        try:
            user_input = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            _session_close()
            print("\n👋 ¡Hasta luego!")
            break

        if not user_input:
            continue

        answer, source_docs = handle_query(user_input, vectordb, chat_history)

        if answer == "__EXIT__":
            _session_close()
            print("\n👋 ¡Hasta luego!")
            break

        print(format_answer(answer))
        print_sources(source_docs)


if __name__ == "__main__":
    main()
