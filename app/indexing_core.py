"""Motor de indexación — carga, chunking y construcción del vectorstore.

Responsabilidad única: procesar data/docs/ y persistir Chroma en storage/chroma/.
Ningún otro módulo debería importar langchain_chroma directamente para indexar.
"""
from __future__ import annotations

from pathlib import Path
import shutil

from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    MarkdownHeaderTextSplitter,
)
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

# ── Importar constantes desde config — una sola fuente de verdad ──────────────
from app.config import CHROMA_DIR as _CHROMA_DIR_STR, OLLAMA_URL

DOCS_DIR   = Path("data/docs")
STORAGE_DIR = Path("storage")
CHROMA_DIR  = Path(_CHROMA_DIR_STR)   # e.g. storage/chroma


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de directorio
# ─────────────────────────────────────────────────────────────────────────────

def ensure_directories():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def reset_vectorstore():
    if CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
        print(f"INFO: Vector store anterior eliminado: {CHROMA_DIR}")


# ─────────────────────────────────────────────────────────────────────────────
# Inferencia de tipo de documento
# Cubre los 18 docs actuales en data/docs/ y es fácil de extender.
# ─────────────────────────────────────────────────────────────────────────────

def infer_doctype(path: Path) -> str:
    """Asigna doc_type a partir de la ruta/nombre del archivo.

    Jerarquía de detección (de más específico a más general):
      adr       → carpeta adr/ o nombre "adr-"
      paper     → nombre empieza con "paper-"
      estado    → nombre contiene "estado"
      roadmap   → nombre contiene "roadmap"
      arquitectura → nombre contiene "arquitectura" o "decisiones"
      memoria   → nombre contiene "memoria"
      langchain → nombre contiene "langchain"
      chroma    → nombre contiene "chroma"
      ollama    → nombre contiene "ollama"
      proyecto  → carpeta proyecto/
      referencia → carpeta referencia/ (fallback para refs técnicas)
      general   → todo lo demás
    """
    name = path.name.lower()
    parts = [p.lower() for p in path.parts]

    if "adr" in parts or name.startswith("adr-"):
        return "adr"
    if name.startswith("paper-"):
        return "paper"
    if "estado" in name:
        return "estado"
    if "roadmap" in name:
        return "roadmap"
    if "arquitectura" in name or "decisiones" in name:
        return "arquitectura"
    if "memoria" in name:
        return "memoria"
    if "langchain" in name:
        return "langchain"
    if "chroma" in name:
        return "chroma"
    if "ollama" in name:
        return "ollama"
    if "proyecto" in parts:
        return "proyecto"
    if "referencia" in parts:
        return "referencia"

    return "general"


def _build_title(path: Path) -> str:
    """Genera un título legible para el metadato 'title'.

    Convierte el nombre de archivo en algo presentable:
      paper-memgpt-resumen.md  →  Paper: MemGPT Resumen
      ADR-001-router-hibrido.md → ADR-001: Router Híbrido
      langchain-retriever.md   → LangChain: Retriever
    """
    stem = path.stem  # sin extensión
    doc_type = infer_doctype(path)

    if doc_type == "paper":
        parts = stem.split("-")[1:]  # quita "paper"
        label = " ".join(p.capitalize() for p in parts)
        return f"Paper: {label}"
    if doc_type == "adr":
        parts = stem.split("-", 2)   # ADR-001-titulo
        number = "-".join(parts[:2]).upper()
        label = parts[2].replace("-", " ").title() if len(parts) > 2 else ""
        return f"{number}: {label}".strip(": ")
    if doc_type == "langchain":
        label = stem.replace("langchain-", "").replace("-", " ").title()
        return f"LangChain — {label}"
    if doc_type == "chroma":
        label = stem.replace("chroma-", "").replace("-", " ").title()
        return f"Chroma — {label}"
    if doc_type == "ollama":
        label = stem.replace("ollama-", "").replace("-", " ").title()
        return f"Ollama — {label}"

    # fallback: nombre limpio
    return stem.replace("-", " ").replace("_", " ").title()


def build_base_metadata(path: Path) -> dict:
    return {
        "source":    path.name,          # nombre corto para el bloque "Basado en:"
        "filepath":  str(path),          # ruta completa para diagnóstico
        "filename":  path.name,
        "filetype":  path.suffix.lower(),
        "doc_type":  infer_doctype(path),
        "title":     _build_title(path),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Carga de documentos
# ─────────────────────────────────────────────────────────────────────────────

def load_documents() -> list[Document]:
    docs = []

    if not DOCS_DIR.exists():
        raise FileNotFoundError(f"No existe la carpeta {DOCS_DIR.resolve()}")

    for path in DOCS_DIR.rglob("*"):
        if path.is_dir():
            continue

        suffix = path.suffix.lower()

        if suffix == ".pdf":
            loader = PyPDFLoader(str(path))
            loaded_docs = loader.load()
            for i, doc in enumerate(loaded_docs):
                doc.metadata.update(build_base_metadata(path))
                doc.metadata["section"] = f"page {i + 1}"
                docs.append(doc)
            print(f"INFO: Cargado PDF: {path}")
            continue

        if suffix == ".txt":
            loader = TextLoader(str(path), encoding="utf-8")
            loaded_docs = loader.load()
            for doc in loaded_docs:
                doc.metadata.update(build_base_metadata(path))
                doc.metadata["section"] = "texto completo"
                docs.append(doc)
            print(f"INFO: Cargado TXT: {path}")
            continue

        if suffix == ".md":
            text = path.read_text(encoding="utf-8")
            base_metadata = build_base_metadata(path)

            headers_to_split_on = [
                ("#",   "h1"),
                ("##",  "h2"),
                ("###", "h3"),
            ]
            md_splitter = MarkdownHeaderTextSplitter(
                headers_to_split_on=headers_to_split_on,
                strip_headers=False,
            )
            md_docs = md_splitter.split_text(text)

            if not md_docs:
                md_docs = [Document(page_content=text, metadata=base_metadata)]

            for doc in md_docs:
                h1 = doc.metadata.get("h1", "")
                h2 = doc.metadata.get("h2", "")
                h3 = doc.metadata.get("h3", "")
                section_parts = [p for p in [h1, h2, h3] if p]
                section = " > ".join(section_parts) if section_parts else "sin sección"

                doc.metadata.update(base_metadata)
                doc.metadata["section"] = section
                docs.append(doc)

            print(f"INFO: Cargado MD ({base_metadata['doc_type']:12s}): {path.name}")
            continue

        print(f"WARN: Ignorando {path.name} (extensión no soportada)")

    if not docs:
        raise ValueError("No se cargó ningún documento. Revisa data/docs.")

    return docs


# ─────────────────────────────────────────────────────────────────────────────
# Chunking
# ─────────────────────────────────────────────────────────────────────────────

def split_documents(docs: list[Document]) -> list[Document]:
    recursive_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1100,
        chunk_overlap=150,
        separators=["\n\n", "\n", " ", ""],
    )

    final_chunks: list[Document] = []

    for doc in docs:
        if len(doc.page_content) <= 1200:
            final_chunks.append(doc)
        else:
            final_chunks.extend(recursive_splitter.split_documents([doc]))

    for i, chunk in enumerate(final_chunks):
        doc_type = chunk.metadata.get("doc_type", "general")
        section  = chunk.metadata.get("section",  "sin-seccion")
        safe     = section.replace(" ", ".").replace(",", "-")
        chunk.metadata["chunk_id"] = f"{doc_type}-{safe}-{i}"

    return final_chunks


# ─────────────────────────────────────────────────────────────────────────────
# Construcción del vectorstore
# ─────────────────────────────────────────────────────────────────────────────

def build_vectorstore(chunks: list[Document]) -> Chroma:
    embeddings = OllamaEmbeddings(
        model="nomic-embed-text",
        base_url=OLLAMA_URL,        # ← desde config, no hardcodeado
    )

    vectordb = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(CHROMA_DIR),
    )

    print(f"INFO: Vector store guardado en {CHROMA_DIR}  ({len(chunks)} chunks)")
    return vectordb
