"""reemplazar_langchain_docs.py — Descarga/actualiza docs de referencia LangChain.

Qué hace:
  Descarga cuatro archivos .mdx desde el repositorio oficial de LangChain
  (GitHub raw) y los guarda como .md en data/docs/referencia/.
  Sobreescribe cualquier versión previa — es un reemplazo completo, no incremental.

Cuándo ejecutarlo:
  - La primera vez que clonas el proyecto (los archivos NO están en git).
  - Cuando quieras actualizar las referencias a la última versión de LangChain.
  - Después de borrar data/docs/referencia/ manualmente.

Prerequisitos:
  1. Conexión a internet activa (descarga desde github.com).
  2. Dependencia instalada: pip install langchain-community
  3. Activar el virtualenv antes de ejecutar:
       .venv\\Scripts\\activate   # Windows PowerShell
       source .venv/bin/activate   # Linux / macOS

Uso:
  python reemplazar_langchain_docs.py

Salida esperada:
  Descargando: https://raw.githubusercontent.com/...
    OK: langchain-rag-concepto.md (12.3 KB)
    OK: langchain-text-splitters.md (8.7 KB)
    ...
  Listo.

Advertencia:
  Este script hace peticiones HTTP a github.com. Si estás detrás de un proxy
  corporativo o sin red, fallará con ERROR: <mensaje>. En ese caso los archivos
  de referencia anteriores NO se borran — el script es seguro ante fallos parciales.

Después de ejecutar:
  Vuelve a indexar para que los nuevos docs entren en ChromaDB:
    python indexacion.py
"""
from pathlib import Path
from langchain_community.document_loaders import WebBaseLoader

REFERENCIA_DIR = Path("data/docs/referencia")
REFERENCIA_DIR.mkdir(parents=True, exist_ok=True)

# Documentos oficiales de LangChain a descargar.
# Cada entrada tiene la URL raw de GitHub y el nombre local del archivo.
# Para agregar más docs: añade un dict con 'url' y 'filename'.
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
