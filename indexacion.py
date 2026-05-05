"""
Script para indexar documentos en Chroma.

Ejecutar:
    python indexacion.py
"""

from app.indexing_core import (
    ensure_directories,
    load_documents,
    split_documents,
    reset_vectorstore,
    build_vectorstore,
)


def main():
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

    print("OK: Indexación completada.")


if __name__ == "__main__":
    main()