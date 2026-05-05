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


DOCS_DIR = Path("data/docs")
STORAGE_DIR = Path("storage")
CHROMA_DIR = STORAGE_DIR / "chroma"


def ensure_directories():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def reset_vector_store():
    if CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
        print(f"[INFO] Vector store anterior eliminado: {CHROMA_DIR}")


def infer_doc_type(path: Path) -> str:
    name = path.name.lower()

    if "estado" in name:
        return "estado"
    if "arquitectura" in name:
        return "arquitectura"
    if "memoria" in name:
        return "memoria"
    if "referencia" in str(path).lower():
        return "referencia"
    return "general"


def build_base_metadata(path: Path) -> dict:
    return {
        "source": str(path),
        "file_name": path.name,
        "file_type": path.suffix.lower(),
        "doc_type": infer_doc_type(path),
    }


def load_documents():
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
                doc.metadata["section"] = f"page_{i + 1}"
                docs.append(doc)

            print(f"[INFO] Cargado PDF: {path}")
            continue

        if suffix == ".txt":
            loader = TextLoader(str(path), encoding="utf-8")
            loaded_docs = loader.load()

            for doc in loaded_docs:
                doc.metadata.update(build_base_metadata(path))
                doc.metadata["section"] = "texto_completo"
                docs.append(doc)

            print(f"[INFO] Cargado TXT: {path}")
            continue

        if suffix == ".md":
            text = path.read_text(encoding="utf-8")
            base_metadata = build_base_metadata(path)

            headers_to_split_on = [
                ("#", "h1"),
                ("##", "h2"),
                ("###", "h3"),
            ]

            md_splitter = MarkdownHeaderTextSplitter(
                headers_to_split_on=headers_to_split_on,
                strip_headers=False,
            )

            md_docs = md_splitter.split_text(text)

            if not md_docs:
                md_docs = [Document(page_content=text, metadata={})]

            for doc in md_docs:
                h1 = doc.metadata.get("h1", "")
                h2 = doc.metadata.get("h2", "")
                h3 = doc.metadata.get("h3", "")

                section_parts = [part for part in [h1, h2, h3] if part]
                section = " > ".join(section_parts) if section_parts else "sin_seccion"

                doc.metadata.update(base_metadata)
                doc.metadata["section"] = section
                docs.append(doc)

            print(f"[INFO] Cargado MD: {path}")
            continue

        print(f"[WARN] Ignorando {path.name} (extensión no soportada)")

    if not docs:
        raise ValueError("No se cargó ningún documento. Revisa data/docs.")

    return docs


def split_documents(docs):
    recursive_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=120,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    final_chunks = []

    for doc in docs:
        if len(doc.page_content) <= 900:
            final_chunks.append(doc)
            continue

        sub_chunks = recursive_splitter.split_documents([doc])
        final_chunks.extend(sub_chunks)

    for i, chunk in enumerate(final_chunks):
        chunk.metadata["chunk_id"] = i

    return final_chunks


def build_vector_store(chunks):
    embeddings = OllamaEmbeddings(
        model="nomic-embed-text",
        base_url="http://localhost:11434",
    )

    vectordb = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(CHROMA_DIR),
    )

    print(f"[INFO] Vector store guardado en {CHROMA_DIR}")
    return vectordb


def main():
    ensure_directories()

    print("[INFO] Cargando documentos...")
    docs = load_documents()

    print(f"[INFO] Documentos cargados: {len(docs)}")

    print("[INFO] Dividiendo en chunks...")
    chunks = split_documents(docs)

    print(f"[INFO] Total de chunks: {len(chunks)}")

    print("[INFO] Reiniciando índice anterior...")
    reset_vector_store()

    print("[INFO] Construyendo vector store...")
    build_vector_store(chunks)

    print("[OK] Indexación completada.")


if __name__ == "__main__":
    main()