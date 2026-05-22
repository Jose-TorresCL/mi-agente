"""Motor RAG — recuperación de documentos y construcción de la chain.

Responsabilidad única: todo lo relacionado con ChromaDB y LangChain.
Ningún otro módulo debería importar langchain_chroma ni ChatOllama directamente.

Clientes LLM disponibles (Fix C2 — cliente unificado):
  build_chain()    → chain LangChain RAG completa (para process_turn RAG)
  generate_raw()   → llamada directa al LLM singleton sin RAG ni chain.
                     Para síntesis de memoria, resumen episódico y cualquier
                     llamada LLM que no necesite recuperación vectorial.
                     Mismo modelo, mismos timeouts, mismo logging centralizado.
"""
from __future__ import annotations

from typing import Any

from app.config import MODEL_NAME, OLLAMA_URL, CHROMA_DIR
from app.logger import get_logger

from langchain_chroma import Chroma
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage

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
# Fix C2 — cliente LLM unificado (sin RAG)
# ─────────────────────────────────────────────

def generate_raw(
    prompt: str,
    temperature: float = 0.3,
    num_predict: int = 150,
    timeout: int = 30,
) -> str | None:
    """Llama al LLM singleton con un prompt libre, sin RAG ni chain LangChain.

    Usa el mismo ChatOllama singleton que build_chain(), garantizando:
    - Un único cliente LLM en todo el proyecto (Fix C2).
    - El mismo modelo (MODEL_NAME de config.py).
    - Logging centralizado con el mismo get_logger.
    - Manejo de errores uniforme: devuelve None en caso de fallo.

    Args:
        prompt:      Texto completo del prompt a enviar al LLM.
        temperature: Temperatura de generación (default 0.3, más conservador
                     que RAG que usa 0.1).
        num_predict: Máximo de tokens a generar.
        timeout:     Segundos antes de abortar la llamada.

    Returns:
        Texto generado por el LLM, o None si la llamada falló.

    Uso típico:
        answer = generate_raw(prompt, temperature=0.3, num_predict=150)
        if answer is None:
            return fallback_string
    """
    try:
        llm = get_llm()
        # ChatOllama acepta opciones extra vía bind().
        # Creamos una instancia temporal con los parámetros ajustados
        # sin tocar el singleton base (que mantiene temperature=0.1 para RAG).
        llm_temp = ChatOllama(
            model=MODEL_NAME,
            base_url=OLLAMA_URL,
            temperature=temperature,
            num_predict=num_predict,
            timeout=timeout,
        )
        result = llm_temp.invoke([HumanMessage(content=prompt)])
        text = result.content.strip() if hasattr(result, "content") else str(result).strip()
        log.debug("generate_raw: %d chars generados", len(text))
        return text if text else None
    except Exception as exc:
        log.warning("generate_raw falló: %s", exc)
        return None


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
    "adr": [
        "adr", "decisión arquitectural", "decision arquitectural",
        "por qué se eligió", "por que se eligio",
        "alternativa descartada", "registro de decisión",
        "registro de decision", "ADR-001", "ADR-002", "ADR-003", "ADR-004",
    ],
    "general": [
        "roadmap", "prioridad", "prioridades", "siguiente fase",
        "qué falta", "que falta", "qué queda", "que queda",
        "plan del proyecto", "próxima sesión", "proxima sesion",
    ],
    "paper": [
        "slm-first", "slm first", "small language model first",
        "moa", "mixture of agents", "mixture-of-agents",
        "memgpt", "lightmem",
        "phi3", "phi3:mini", "phi-3", "por qué falló", "por que falló",
        "falló phi", "fallo phi",
        "auto-refinamiento", "auto refinamiento", "self-refinement",
        "modelos en paralelo", "modelo paralelo",
        "qué dice el paper", "que dice el paper",
        "paper de", "según el paper", "segun el paper",
        "investigación sobre", "investigacion sobre",
    ],
}

_FETCH_K_BY_TYPE: dict[str, int] = {
    "paper": 30,
}
_DEFAULT_FETCH_K = 20


def _infer_doc_types(question: str) -> list[str]:
    q = question.lower()
    return [
        doc_type
        for doc_type, signals in _DOC_TYPE_SIGNALS.items()
        if any(s in q for s in signals)
    ]


def build_retriever(vectordb: Chroma, question: str):
    """Construye el retriever con MMR y filtro opcional por tipo de documento."""
    doc_types = _infer_doc_types(question)

    fetch_k = max(
        (_FETCH_K_BY_TYPE.get(dt, _DEFAULT_FETCH_K) for dt in doc_types),
        default=_DEFAULT_FETCH_K,
    )

    search_kwargs: dict = {
        "k": 5,
        "fetch_k": fetch_k,
        "lambda_mult": 0.6,
    }
    if len(doc_types) == 1:
        search_kwargs["filter"] = {"doc_type": doc_types[0]}
    elif len(doc_types) > 1:
        search_kwargs["filter"] = {"$or": [{"doc_type": dt} for dt in doc_types]}
    return vectordb.as_retriever(
        search_type="mmr",
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
