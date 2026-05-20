"""Singleton del índice de intenciones — Capa 2 del router.

Encapsula el acceso a Chroma para el intent_index.
El router delega aquí sin importar langchain_chroma directamente,
cumpliendo el contrato R1-E: Chroma pertenece a rag_engine/episode_store
y a este módulo, no al router.

Requisito previo:
    Ejecutar python build_intent_index.py una vez para crear
    storage/intent_index. Si el índice no existe, get_intent_db()
    devuelve None y la Capa 2 se salta silenciosamente.
"""
from __future__ import annotations

from pathlib import Path

from app.config import OLLAMA_URL
from app.logger import get_logger

log = get_logger(__name__)

INTENT_DIR      = Path("storage/intent_index")
EMBED_MODEL     = "nomic-embed-text"
EMBED_THRESHOLD = 0.70
EMBED_TOP_K     = 1

_intent_db         = None
_intent_embeddings = None


def get_intent_db():
    """Devuelve el singleton de Chroma para intent_index.

    Crea la instancia la primera vez (lazy init).
    Devuelve None si el índice no existe en disco — la Capa 2
    del router lo interpreta como 'saltar al fallback'.
    """
    global _intent_db, _intent_embeddings

    if not INTENT_DIR.exists():
        return None

    if _intent_db is None:
        try:
            from langchain_ollama import OllamaEmbeddings
            from langchain_chroma import Chroma

            _intent_embeddings = OllamaEmbeddings(
                model=EMBED_MODEL,
                base_url=OLLAMA_URL,
            )
            _intent_db = Chroma(
                persist_directory=str(INTENT_DIR),
                embedding_function=_intent_embeddings,
                collection_name="intent_index",
            )
            log.debug("[intent_index] singleton inicializado desde %s", INTENT_DIR)
        except Exception as e:
            log.warning("[intent_index] error al inicializar: %s", e)
            return None

    return _intent_db
