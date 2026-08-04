"""
Script para indexar documentos en Chroma.

Ejecutar:
    python indexacion.py                  # indexa documentos RAG (comportamiento normal)
    python indexacion.py --only-episodes  # re-indexa solo los episodios en experience_index
    python indexacion.py --all            # indexa documentos RAG Y re-indexa episodios
"""
import sys
from pathlib import Path

from app.indexing_core import (
    ensure_directories,
    load_documents,
    split_documents,
    reset_vectorstore,
    build_vectorstore,
)

PROJECT_ROOT = Path(__file__).resolve().parent

EXCLUDED_FILES = {
    "data/docs/proyecto/estado_proyecto.md",
    "data/docs/proyecto/roadmap.md",
}

EXCLUDED_PATH_PARTS = {
    "data/docs/proyecto/historico/",
    "data/docs/adr/borradores/",
    ".pytest_cache/",
}

INCLUDED_PREFIXES = (
    "data/docs/proyecto/",
    "data/docs/referencia/",
    "data/docs/adr/",
)


def normalize_source(source: str) -> str:
    return source.replace("\\", "/").strip()


def should_include(doc) -> bool:
    source = normalize_source(str(doc.metadata.get("source", "")))

    if not source:
        return False

    if not source.startswith(INCLUDED_PREFIXES):
        return False

    if source in EXCLUDED_FILES:
        return False

    if any(part in source for part in EXCLUDED_PATH_PARTS):
        return False

    return True


def index_documents() -> None:
    ensure_directories()

    print("INFO: Cargando documentos...")
    docs = load_documents()
    print(f"INFO: Documentos cargados (raw): {len(docs)}")

    filtered_docs = [doc for doc in docs if should_include(doc)]
    excluded_count = len(docs) - len(filtered_docs)

    print(f"INFO: Documentos incluidos: {len(filtered_docs)}")
    print(f"INFO: Documentos excluidos por política: {excluded_count}")

    print("INFO: Dividiendo en chunks...")
    chunks = split_documents(filtered_docs)
    print(f"INFO: Total de chunks: {len(chunks)}")

    print("INFO: Reiniciando índice anterior...")
    reset_vectorstore()

    print("INFO: Construyendo vector store...")
    build_vectorstore(chunks)

    print("OK: Indexación de documentos completada.")


def index_episodes() -> None:
    from app.episode_store import reindex_all, episode_index_stats

    print("INFO: Re-indexando episodios en experience_index...")
    count = reindex_all()
    stats = episode_index_stats()
    print(f"OK: {count} episodios indexados. Total en índice: {stats['indexed_count']}")


def main() -> None:
    args = set(sys.argv[1:])

    only_episodes = "--only-episodes" in args
    index_all = "--all" in args

    if only_episodes:
        index_episodes()
    elif index_all:
        index_documents()
        index_episodes()
    else:
        index_documents()


if __name__ == "__main__":
    main()