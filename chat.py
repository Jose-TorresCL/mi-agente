"""Punto de entrada del asistente.

Arranca el loop de conversación, gestiona el vectorstore
y delega cada turno a chat_core.handle_query().

Auto-reindex: al arrancar detecta si hay docs más nuevos que el índice
y re-indexa automáticamente antes de abrir el chat.
"""
from __future__ import annotations

from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

from app.config import CHROMA_DIR, OLLAMA_URL
from app.indexing_core import needs_reindex, run_full_index
from app.chat_core import build_memory, handle_query
from app.chat_ui import print_welcome, print_sources, format_answer
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
    """Decide si hay que re-indexar y devuelve el vectorstore listo.

    Flujo:
      1. needs_reindex() compara mtime de docs vs mtime del índice.
      2. Si hay docs nuevos → avisa al usuario → run_full_index().
      3. Si está al día → carga el existente directamente.
    """
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


def main() -> None:
    print_welcome()

    vectordb     = _boot_vectorstore()
    chat_history = build_memory()

    while True:
        try:
            user_input = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 ¡Hasta luego!")
            break

        if not user_input:
            continue

        answer, source_docs = handle_query(user_input, vectordb, chat_history)

        if answer == "__EXIT__":
            print("\n👋 ¡Hasta luego!")
            break

        print(format_answer(answer))
        print_sources(source_docs)


if __name__ == "__main__":
    main()
