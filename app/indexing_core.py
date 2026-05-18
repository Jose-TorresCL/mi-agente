"""Motor de indexación — carga, chunking y construcción del vectorstore.

Responsabilidad única: procesar data/docs/ y persistir Chroma en storage/chroma/.
Ningún otro módulo debería importar langchain_chroma directamente para indexar.

API pública
───────────
    needs_reindex()   → (bool, str)  — ¿hay docs más nuevos que el índice?
    run_full_index()  → Chroma       — reset + load + split + build en un paso
    load_documents()  → list[Document]
    split_documents() → list[Document]
    build_vectorstore() → Chroma
"""
from __future__ import annotations

from pathlib import Path
import shutil
import time

from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    MarkdownHeaderTextSplitter,
)
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

from app.config import CHROMA_DIR as _CHROMA_DIR_STR, OLLAMA_URL
from app.logger import get_logger

log = get_logger(__name__)

DOCS_DIR    = Path("data/docs")
STORAGE_DIR = Path("storage")
CHROMA_DIR  = Path(_CHROMA_DIR_STR)

# ─────────────────────────────────────────────────────────────────────────────
# Archivos excluidos del índice RAG
# Razones de exclusión:
#   ollama-api.md      → 55 KB, genera ~110 chunks de código sin contexto;
#                        el agente nunca recibe preguntas sobre la API interna
#   hardware-modelos.md → muy pequeño y genérico; el LLM ya conoce este info
#   chroma-introduccion.md → genérico; chroma-queries.md lo cubre mejor
# ─────────────────────────────────────────────────────────────────────────────
EXCLUDED_FILENAMES: set[str] = {
    "ollama-api.md",
    "hardware-modelos.md",
    "chroma-introduccion.md",
}


# ─────────────────────────────────────────────────────────────────────────────
# Auto-reindex — detección de docs nuevos
# ─────────────────────────────────────────────────────────────────────────────

def needs_reindex() -> tuple[bool, str]:
    """Compara el mtime del doc más reciente contra el mtime del vectorstore.

    Returns:
        (True,  motivo)  si hay que re-indexar
        (False, motivo)  si el índice está al día

    Casos que disparan re-indexado:
      - El vectorstore no existe todavía
      - Hay al menos un doc en data/docs/ más nuevo que el índice
    """
    # Caso 1: el vectorstore no existe
    chroma_sqlite = CHROMA_DIR / "chroma.sqlite3"
    if not chroma_sqlite.exists():
        return True, "vectorstore no existe — primer indexado"

    # Timestamp del vectorstore (cuándo se creó/actualizó por última vez)
    index_mtime = chroma_sqlite.stat().st_mtime

    # Timestamp del doc más reciente en data/docs/ (excluidos los omitidos)
    doc_files = [
        p for p in DOCS_DIR.rglob("*")
        if p.is_file()
        and p.suffix.lower() in {".md", ".txt", ".pdf"}
        and p.name not in EXCLUDED_FILENAMES
    ]
    if not doc_files:
        return False, "no hay docs en data/docs/"

    newest_doc = max(doc_files, key=lambda p: p.stat().st_mtime)
    newest_mtime = newest_doc.stat().st_mtime

    if newest_mtime > index_mtime:
        # Calcular cuántos docs son más nuevos que el índice
        newer = [p for p in doc_files if p.stat().st_mtime > index_mtime]
        return True, f"{len(newer)} doc(s) más nuevo(s) que el índice — más reciente: {newest_doc.name}"

    return False, f"índice al día (último doc: {newest_doc.name})"


def run_full_index() -> Chroma:
    """Ciclo completo: reset → load → split → build.

    Punto de entrada único para re-indexar desde cualquier lugar
    sin conocer los pasos internos.
    """
    t0 = time.time()
    reset_vectorstore()
    docs   = load_documents()
    chunks = split_documents(docs)
    db     = build_vectorstore(chunks)
    elapsed = time.time() - t0
    log.info("[indexing] re-indexado completo en %.1fs (%d chunks)", elapsed, len(chunks))
    return db


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de directorio
# ─────────────────────────────────────────────────────────────────────────────

def ensure_directories():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def reset_vectorstore():
    if CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
        log.info("[indexing] vectorstore anterior eliminado: %s", CHROMA_DIR)


# ─────────────────────────────────────────────────────────────────────────────
# Inferencia de tipo de documento
# ─────────────────────────────────────────────────────────────────────────────

def infer_doctype(path: Path) -> str:
    """Asigna doc_type a partir de la ruta/nombre del archivo.

    Jerarquía de detección (de más específico a más general):
      adr          → carpeta adr/ o nombre "adr-"
      paper        → nombre empieza con "paper-"
      estado       → nombre contiene "estado"
      roadmap      → nombre contiene "roadmap"
      vision       → nombre contiene "vision"
      hardware     → nombre contiene "hardware"
      arquitectura → nombre contiene "arquitectura" o "decisiones"
      memoria      → nombre contiene "memoria"
      langchain    → nombre contiene "langchain"
      chroma       → nombre contiene "chroma"
      ollama       → nombre contiene "ollama"
      proyecto     → carpeta proyecto/
      referencia   → carpeta referencia/ (fallback para refs técnicas)
      general      → todo lo demás
    """
    name  = path.name.lower()
    parts = [p.lower() for p in path.parts]

    if "adr" in parts or name.startswith("adr-"):         return "adr"
    if name.startswith("paper-"):                          return "paper"
    if "estado" in name:                                   return "estado"
    if "roadmap" in name:                                  return "roadmap"
    if "vision" in name:                                   return "vision"
    if "hardware" in name:                                 return "hardware"
    if "arquitectura" in name or "decisiones" in name:    return "arquitectura"
    if "memoria" in name:                                  return "memoria"
    if "langchain" in name:                                return "langchain"
    if "chroma" in name:                                   return "chroma"
    if "ollama" in name:                                   return "ollama"
    if "proyecto" in parts:                                return "proyecto"
    if "referencia" in parts:                              return "referencia"
    return "general"


def _build_title(path: Path) -> str:
    """Genera un título legible para el metadato 'title'."""
    stem     = path.stem
    doc_type = infer_doctype(path)

    if doc_type == "paper":
        parts = stem.split("-")[1:]
        label = " ".join(p.capitalize() for p in parts)
        return f"Paper: {label}"
    if doc_type == "adr":
        parts  = stem.split("-", 2)
        number = "-".join(parts[:2]).upper()
        label  = parts[2].replace("-", " ").title() if len(parts) > 2 else ""
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
    if doc_type == "vision":
        label = stem.replace("vision-", "").replace("-", " ").title()
        return f"Visión — {label}"
    if doc_type == "hardware":
        label = stem.replace("hardware-", "").replace("-", " ").title()
        return f"Hardware — {label}"
    return stem.replace("-", " ").replace("_", " ").title()


def build_base_metadata(path: Path) -> dict:
    return {
        "source":   path.name,
        "filepath": str(path),
        "filename": path.name,
        "filetype": path.suffix.lower(),
        "doc_type": infer_doctype(path),
        "title":    _build_title(path),
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

        # ── Exclusiones explícitas ──────────────────────────────────────────
        if path.name in EXCLUDED_FILENAMES:
            log.info("[indexing] EXCLUIDO: %s (en lista de exclusión)", path.name)
            continue

        suffix = path.suffix.lower()

        if suffix == ".pdf":
            loader = PyPDFLoader(str(path))
            loaded_docs = loader.load()
            for i, doc in enumerate(loaded_docs):
                doc.metadata.update(build_base_metadata(path))
                doc.metadata["section"] = f"page {i + 1}"
                docs.append(doc)
            log.info("[indexing] PDF: %s", path.name)
            continue

        if suffix == ".txt":
            loader = TextLoader(str(path), encoding="utf-8")
            loaded_docs = loader.load()
            for doc in loaded_docs:
                doc.metadata.update(build_base_metadata(path))
                doc.metadata["section"] = "texto completo"
                docs.append(doc)
            log.info("[indexing] TXT: %s", path.name)
            continue

        if suffix == ".md":
            text          = path.read_text(encoding="utf-8")
            base_metadata = build_base_metadata(path)

            headers_to_split_on = [("#", "h1"), ("##", "h2"), ("###", "h3")]
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

            log.info("[indexing] MD  (%s): %s", base_metadata['doc_type'], path.name)
            continue

        log.warning("[indexing] ignorando %s (extensión no soportada)", path.name)

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
        base_url=OLLAMA_URL,
    )

    vectordb = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(CHROMA_DIR),
    )

    log.info("[indexing] vectorstore guardado en %s (%d chunks)", CHROMA_DIR, len(chunks))
    return vectordb
