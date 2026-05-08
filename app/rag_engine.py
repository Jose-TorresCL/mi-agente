"""Motor RAG — recuperación de documentos y construcción de la chain.

Responsabilidad única: todo lo relacionado con ChromaDB y LangChain.
Ningún otro módulo debería importar langchain_chroma ni ChatOllama directamente.
"""
from __future__ import annotations

from app.config import MODEL_NAME, OLLAMA_URL, CHROMA_DIR
from app.logger import get_logger

from langchain_chroma import Chroma
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

log = get_logger(__name__)


# ─────────────────────────────────────────────
# Singleton LLM
# ─────────────────────────────────────────────

_llm_instance: ChatOllama | None = None


def get_llm() -> ChatOllama:
    """Devuelve el LLM singleton. Se crea solo la primera vez."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = ChatOllama(
            model=MODEL_NAME,
            base_url=OLLAMA_URL,
            temperature=0.1,
        )
        log.debug("LLM singleton inicializado: %s", MODEL_NAME)
    return _llm_instance


# ─────────────────────────────────────────────
# Vector store
# ─────────────────────────────────────────────

def load_vector_store() -> Chroma:
    """Carga ChromaDB con el modelo de embeddings configurado."""
    embeddings = OllamaEmbeddings(
        model="nomic-embed-text",
        base_url=OLLAMA_URL,
    )
    return Chroma(
        embedding_function=embeddings,
        persist_directory=CHROMA_DIR,
    )


# ─────────────────────────────────────────────
# Filtrado de documentos por tipo
# ─────────────────────────────────────────────

_DOC_TYPE_SIGNALS: dict[str, list[str]] = {
    "arquitectura": [
        "arquitectura", "componente", "componentes", "chat.py",
        "indexacion", "índice", "indice", "vector store",
        "base documental", "documentos fuente",
    ],
    "memoria": [
        "memoria", "memoria híbrida", "memoria hibrida",
        "grounded", "correcta", "corto plazo", "largo plazo",
    ],
    "estado": [
        "estado", "próximos pasos", "proximos pasos",
        "objetivo actual", "objetivo de esta etapa",
        "estado del proyecto",
    ],
}


def _infer_doc_types(question: str) -> list[str]:
    q = question.lower()
    return [
        doc_type
        for doc_type, signals in _DOC_TYPE_SIGNALS.items()
        if any(s in q for s in signals)
    ]


def build_retriever(vectordb: Chroma, question: str):
    """Construye el retriever con filtro opcional por tipo de documento."""
    doc_types = _infer_doc_types(question)
    search_kwargs: dict = {"k": 5}
    if len(doc_types) == 1:
        search_kwargs["filter"] = {"doc_type": doc_types[0]}
    elif len(doc_types) > 1:
        search_kwargs["filter"] = {"$or": [{"doc_type": dt} for dt in doc_types]}
    return vectordb.as_retriever(
        search_type="similarity",
        search_kwargs=search_kwargs,
    )


def retrieve_context(question: str, vectordb: Chroma) -> tuple[str, list]:
    """Recupera documentos relevantes y devuelve (texto_contexto, source_docs)."""
    retriever = build_retriever(vectordb, question)
    source_docs = retriever.invoke(question)
    log.debug("RAG: recuperados %d documentos", len(source_docs))
    context_text = "\n\n".join(doc.page_content for doc in source_docs)
    return context_text, source_docs


# ─────────────────────────────────────────────
# Chain LangChain
# ─────────────────────────────────────────────

def build_chain(prompt_template: str, memory_context: str):
    """Construye la chain RAG: prompt | llm | parser."""
    llm = get_llm()
    qa_prompt = ChatPromptTemplate.from_template(prompt_template)
    qa_prompt_with_memory = qa_prompt.partial(memory_context=memory_context)
    return qa_prompt_with_memory | llm | StrOutputParser()
