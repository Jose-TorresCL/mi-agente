from pathlib import Path
from langchain_community.document_loaders import WebBaseLoader

REFERENCIA_DIR = Path("data/docs/referencia")
REFERENCIA_DIR.mkdir(parents=True, exist_ok=True)

DOCS = [
    {
        "url": "https://raw.githubusercontent.com/langchain-ai/langchain/master/docs/docs/concepts/rag.mdx",
        "filename": "langchain-rag-concepto.md",
    },
    {
        "url": "https://raw.githubusercontent.com/langchain-ai/langchain/master/docs/docs/concepts/text_splitters.mdx",
        "filename": "langchain-text-splitters.md",
    },
    {
        "url": "https://raw.githubusercontent.com/langchain-ai/langchain/master/docs/docs/concepts/embedding_models.mdx",
        "filename": "langchain-embeddings.md",
    },
    {
        "url": "https://raw.githubusercontent.com/langchain-ai/langchain/master/docs/docs/how_to/vectorstore_retriever.mdx",
        "filename": "langchain-retriever.md",
    },
]

for doc in DOCS:
    dest = REFERENCIA_DIR / doc["filename"]
    print(f"Descargando: {doc['url']}")
    try:
        loader = WebBaseLoader(doc["url"])
        loaded = loader.load()
        contenido = "\n\n".join(d.page_content for d in loaded)
        dest.write_text(contenido, encoding="utf-8")
        kb = len(contenido) / 1024
        print(f"  OK: {doc['filename']} ({kb:.1f} KB)")
    except Exception as e:
        print(f"  ERROR: {e}")

print("Listo.")
