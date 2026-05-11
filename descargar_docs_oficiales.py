"""
Descarga documentación oficial y la guarda como .md en data/docs/referencia/
Ejecutar UNA sola vez: python descargar_docs_oficiales.py
"""
from pathlib import Path
from langchain_community.document_loaders import WebBaseLoader

REFERENCIA_DIR = Path("data/docs/referencia")
REFERENCIA_DIR.mkdir(parents=True, exist_ok=True)

DOCS_A_DESCARGAR = [
    # ── LangChain ──────────────────────────────────────────────────────
    {
        "url": "https://python.langchain.com/docs/how_to/vectorstore_retriever/",
        "filename": "langchain-retriever.md",
        "titulo": "# LangChain — Vector Store Retriever\n\n",
    },
    {
        "url": "https://python.langchain.com/docs/concepts/rag/",
        "filename": "langchain-rag-concepto.md",
        "titulo": "# LangChain — RAG Conceptos\n\n",
    },
    {
        "url": "https://python.langchain.com/docs/concepts/text_splitters/",
        "filename": "langchain-text-splitters.md",
        "titulo": "# LangChain — Text Splitters\n\n",
    },
    {
        "url": "https://python.langchain.com/docs/concepts/embedding_models/",
        "filename": "langchain-embeddings.md",
        "titulo": "# LangChain — Embedding Models\n\n",
    },
    # ── Chroma ─────────────────────────────────────────────────────────
    {
        "url": "https://docs.trychroma.com/docs/overview/introduction",
        "filename": "chroma-introduccion.md",
        "titulo": "# Chroma — Introducción\n\n",
    },
    {
        "url": "https://docs.trychroma.com/docs/querying-collections/query-and-get",
        "filename": "chroma-queries.md",
        "titulo": "# Chroma — Queries y filtros\n\n",
    },
    # ── Ollama ─────────────────────────────────────────────────────────
    {
        "url": "https://github.com/ollama/ollama/blob/main/docs/api.md",
        "filename": "ollama-api.md",
        "titulo": "# Ollama — API Reference\n\n",
    },
]

print(f"Destino: {REFERENCIA_DIR.resolve()}\n")

exitos = 0
errores = 0

for doc in DOCS_A_DESCARGAR:
    dest = REFERENCIA_DIR / doc["filename"]
    print(f"Descargando: {doc['url']}")
    try:
        loader = WebBaseLoader(doc["url"])
        loaded = loader.load()
        contenido = doc["titulo"] + "\n\n".join(d.page_content for d in loaded)
        dest.write_text(contenido, encoding="utf-8")
        kb = len(contenido) / 1024
        print(f"  ✓ Guardado: {doc['filename']} ({kb:.1f} KB)\n")
        exitos += 1
    except Exception as e:
        print(f"  ✗ Error: {e}\n")
        errores += 1

print(f"Resultado: {exitos} exitosos, {errores} errores")
print("Siguiente paso: python indexacion.py")