"""Capa de indexación episódica en Chroma.

Responsabilidades:
  - Indexar episodios individuales en la colección 'episodios' de Chroma
    (namespace SEPARADO de la colección de documentos RAG).
  - Proveer búsqueda semántica sobre episodios pasados.
  - Permitir re-indexación completa desde episodic_memory.json.

Flujo de uso normal:
  1. memory_store.save_episode()  llama  index_episode()  al guardar.
  2. intelligence.py              llama  search_episodes() en el carril 'episode'.
  3. (8C) memory_manager.py       llama  consolidate_old_episodes() periódicamente.

Convenciones:
  - Colección Chroma: EPISODE_COLLECTION = 'episodios'
  - ID de cada documento: ISO timestamp del episodio (ej: '2026-05-19T10:30')
  - Metadatos almacenados: date, time, turns, source='episode'
  - Namespace físico: storage/chroma  (misma instancia que documentos,
    colección diferente — Chroma las aísla automáticamente)

Never raises: todos los métodos públicos capturan excepciones y loggean.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from app.logger import get_logger

if TYPE_CHECKING:
    from app.schemas import EpisodeItem

log = get_logger("episode_store")

# ─────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────

EPISODE_COLLECTION   = "episodios"
EPISODIC_MEMORY_FILE = Path("storage") / "episodic_memory.json"
CHROMA_DIR           = Path("storage") / "chroma"

# ─────────────────────────────────────────────
# Inicialización lazy del cliente Chroma
# ─────────────────────────────────────────────

_collection = None  # instancia lazy: se crea al primer uso


def _get_collection():
    """Devuelve (creando si no existe) la colección 'episodios' en Chroma.

    Usa OllamaEmbeddings con el mismo modelo que el RAG de documentos
    para que los vectores sean comparables semánticamente.

    Returns:
        langchain_chroma.Chroma | None  — None si Chroma/Ollama no están disponibles.
    """
    global _collection
    if _collection is not None:
        return _collection
    try:
        from langchain_ollama import OllamaEmbeddings
        from langchain_chroma import Chroma

        embeddings = OllamaEmbeddings(model="nomic-embed-text")
        _collection = Chroma(
            collection_name=EPISODE_COLLECTION,
            persist_directory=str(CHROMA_DIR),
            embedding_function=embeddings,
        )
        log.info(f"[episode_store] colección '{EPISODE_COLLECTION}' lista en {CHROMA_DIR}")
        return _collection
    except Exception as exc:
        log.warning(f"[episode_store] Chroma no disponible: {exc}")
        return None


# ─────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────

def _episode_to_doc(episode: dict) -> tuple[str, dict, str]:
    """Convierte un EpisodeItem a (id, metadata, page_content) para Chroma.

    El `page_content` es el resumen del episodio — es lo que se embeddea
    y se usa para la búsqueda semántica.

    El `id` es 'YYYY-MM-DDTHH:MM' para garantizar unicidad y orden.

    Args:
        episode: dict con keys date, time, turns, summary.

    Returns:
        Tupla (doc_id, metadata, text_content).
    """
    date    = episode.get("date", "unknown")
    time    = episode.get("time", "00:00")
    turns   = episode.get("turns", 0)
    summary = episode.get("summary", "").strip()

    doc_id   = f"{date}T{time}"
    metadata = {
        "date":   date,
        "time":   time,
        "turns":  turns,
        "source": "episode",
    }
    # El texto indexado combina fecha + resumen para que
    # preguntas como '¿qué pasó el 18 de mayo?' también funcionen.
    content = f"[{date} {time}] ({turns} turnos)\n{summary}"
    return doc_id, metadata, content


# ─────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────

def index_episode(episode: dict) -> bool:
    """Indexa un único episodio en Chroma.

    Idempotente: si el episodio ya existe (mismo ID), Chroma lo actualiza
    sin duplicar.

    Args:
        episode: dict con keys date, time, turns, summary
                 (formato EpisodeItem de schemas.py).

    Returns:
        True si se indexó correctamente, False si Chroma no está disponible.

    Never raises.
    """
    col = _get_collection()
    if col is None:
        return False
    try:
        doc_id, metadata, content = _episode_to_doc(episode)
        col.add_texts(
            texts=[content],
            metadatas=[metadata],
            ids=[doc_id],
        )
        log.info(f"[episode_store] episodio indexado: {doc_id}")
        return True
    except Exception as exc:
        log.warning(f"[episode_store] error indexando episodio: {exc}")
        return False


def search_episodes(query: str, k: int = 3) -> list[dict]:
    """Busca los k episodios más relevantes para la consulta.

    Args:
        query: Texto de búsqueda (ej: 'bug con Chroma', 'embeddings', 'semana pasada').
        k:     Número de resultados a devolver. Default 3.

    Returns:
        Lista de dicts con keys: summary, date, time, turns, score.
        Lista vacía si Chroma no está disponible o no hay resultados.

    Never raises.
    """
    col = _get_collection()
    if col is None:
        return []
    try:
        results = col.similarity_search_with_relevance_scores(query, k=k)
        episodes_found = []
        for doc, score in results:
            episodes_found.append({
                "summary": doc.page_content,
                "date":    doc.metadata.get("date", "?"),
                "time":    doc.metadata.get("time", "?"),
                "turns":   doc.metadata.get("turns", 0),
                "score":   round(score, 3),
            })
        log.info(f"[episode_store] search '{query[:40]}' → {len(episodes_found)} resultados")
        return episodes_found
    except Exception as exc:
        log.warning(f"[episode_store] error en búsqueda episódica: {exc}")
        return []


def reindex_all() -> int:
    """Re-indexa TODOS los episodios de episodic_memory.json desde cero.

    Útil cuando:
    - Se cambia el formato del episodio.
    - Se quiere reconstruir el índice tras una corrupción.
    - Se migra desde la versión sin índice.

    Elimina la colección existente y la reconstruye.

    Returns:
        Número de episodios indexados (0 si falla o no hay episodios).

    Never raises.
    """
    global _collection
    try:
        if not EPISODIC_MEMORY_FILE.exists():
            log.info("[episode_store] reindex_all: no existe episodic_memory.json")
            return 0

        with open(EPISODIC_MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        episodes = data.get("episodes", [])
        if not episodes:
            log.info("[episode_store] reindex_all: sin episodios para indexar")
            return 0

        # Forzar recreación de la colección
        _collection = None
        col = _get_collection()
        if col is None:
            return 0

        # Eliminar todos los documentos existentes en la colección
        try:
            existing_ids = col.get()["ids"]
            if existing_ids:
                col.delete(ids=existing_ids)
                log.info(f"[episode_store] reindex_all: eliminados {len(existing_ids)} docs previos")
        except Exception:
            pass  # colección vacía: no hay nada que borrar

        # Indexar todos los episodios
        count = 0
        for ep in episodes:
            if index_episode(ep):
                count += 1

        log.info(f"[episode_store] reindex_all: {count}/{len(episodes)} episodios indexados")
        return count
    except Exception as exc:
        log.warning(f"[episode_store] reindex_all error: {exc}")
        return 0


def episode_index_stats() -> dict:
    """Devuelve estadísticas del índice episódico.

    Returns:
        dict con:
          - indexed_count: int  — documentos en Chroma
          - collection:    str  — nombre de la colección
          - chroma_dir:    str  — ruta del directorio
          - available:     bool — True si Chroma está operativo

    Never raises.
    """
    col = _get_collection()
    if col is None:
        return {
            "indexed_count": 0,
            "collection":    EPISODE_COLLECTION,
            "chroma_dir":    str(CHROMA_DIR),
            "available":     False,
        }
    try:
        count = len(col.get()["ids"])
        return {
            "indexed_count": count,
            "collection":    EPISODE_COLLECTION,
            "chroma_dir":    str(CHROMA_DIR),
            "available":     True,
        }
    except Exception as exc:
        log.warning(f"[episode_store] stats error: {exc}")
        return {
            "indexed_count": 0,
            "collection":    EPISODE_COLLECTION,
            "chroma_dir":    str(CHROMA_DIR),
            "available":     False,
        }
