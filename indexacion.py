"""
Script para indexar documentos en Chroma.

Ejecutar:
    python indexacion.py                  # indexa documentos RAG (comportamiento normal)
    python indexacion.py --only-episodes  # re-indexa solo los episodios en experience_index
    python indexacion.py --all            # indexa documentos RAG Y re-indexa episodios
"""
import sys

from app.indexing_core import (
    ensure_directories,
    load_documents,
    split_documents,
    reset_vectorstore,
    build_vectorstore,
)


def index_documents() -> None:
    """Indexa los documentos RAG en Chroma (comportamiento original)."""
    ensure_directories()

    print("INFO: Cargando documentos...")
    docs = load_documents()
    print(f"INFO: Documentos cargados: {len(docs)}")

    print("INFO: Dividiendo en chunks...")
    chunks = split_documents(docs)
    print(f"INFO: Total de chunks: {len(chunks)}")

    print("INFO: Reiniciando índice anterior...")
    reset_vectorstore()

    print("INFO: Construyendo vector store...")
    build_vectorstore(chunks)

    print("OK: Indexación de documentos completada.")


def index_episodes() -> None:
    """Re-indexa todos los episodios de episodic_memory.json en experience_index."""
    from app.episode_store import reindex_all, episode_index_stats

    print("INFO: Re-indexando episodios en experience_index...")
    count = reindex_all()
    stats = episode_index_stats()
    print(f"OK: {count} episodios indexados. Total en índice: {stats['indexed_count']}")


def main() -> None:
    args = set(sys.argv[1:])

    only_episodes = "--only-episodes" in args
    index_all     = "--all" in args

    if only_episodes:
        index_episodes()
    elif index_all:
        index_documents()
        index_episodes()
    else:
        # Comportamiento por defecto: solo documentos RAG (sin cambios)
        index_documents()


if __name__ == "__main__":
    main()
