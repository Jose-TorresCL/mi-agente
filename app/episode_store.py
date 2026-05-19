"""Capa de indexación episódica en Chroma — experience_index.

Responsabilidades:
  - Indexar episodios en la colección 'experience_index' de Chroma
    (namespace SEPARADO de la colección de documentos RAG).
  - Proveer búsqueda semántica sobre episodios pasados.
  - Permitir re-indexación completa desde episodic_memory.json.

Flujo de uso normal:
  1. memory_store.save_episode()  llama  index_episode()  al guardar.
  2. intelligence.py carril 'episode' llama search_episodes() para responder
     preguntas directas sobre sesiones pasadas.
  3. intelligence.py _decide_rag() llama experience_lookup() para inyectar
     contexto episódico relevante (score > 0.80) en todos los carriles RAG.
  4. (8C) al cerrar sesión, close_session_episode() pregunta al usuario y
     llama mark_episode() para marcar exitoso=True/False.

Convenciones:
  - Colección Chroma: EPISODE_COLLECTION = 'experience_index'
  - ID de cada documento: ISO timestamp del episodio (ej: '2026-05-19T10:30')
  - Metadatos almacenados: date, time, turns, source, carril_dominante,
    tareas_completadas, exitoso
  - Namespace físico: storage/chroma  (misma instancia que documentos,
    colección diferente — Chroma las aísla automáticamente)

Never raises: todos los métodos públicos capturan excepciones y loggean.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from app.logger import get_logger

if TYPE_CHECKING:
    from app.schemas import EpisodeItem

log = get_logger("episode_store")

# ─────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────

EPISODE_COLLECTION   = "experience_index"          # renombrado de 'episodios' (8A-v2)
EPISODIC_MEMORY_FILE = Path("storage") / "episodic_memory.json"
CHROMA_DIR           = Path("storage") / "chroma"

# Score mínimo para que search_episodes() lo considere relevante en búsqueda directa.
_MIN_RELEVANCE_SCORE = 0.20

# Score para inyección automática en contexto RAG (experience_lookup).
EXPERIENCE_INJECT_THRESHOLD = 0.80

# ─────────────────────────────────────────────
# Inicialización lazy del cliente Chroma
# ─────────────────────────────────────────────

_collection = None  # instancia lazy: se crea al primer uso


def _get_collection():
    """Devuelve (creando si no existe) la colección 'experience_index' en Chroma.

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

    Metadatos enriquecidos (8A-v2):
      - carril_dominante:   carril más usado en la sesión (str, default 'unknown')
      - tareas_completadas: número de tareas marcadas done en la sesión (int)
      - exitoso:            True/False/None (None = sin marcar aún)

    Args:
        episode: dict con keys date, time, turns, summary y opcionales
                 carril_dominante, tareas_completadas, exitoso.

    Returns:
        Tupla (doc_id, metadata, text_content).
    """
    date    = episode.get("date", "unknown")
    time_   = episode.get("time", "00:00")
    turns   = episode.get("turns", 0)
    summary = episode.get("summary", "").strip()

    # Metadatos enriquecidos — valores por defecto si no están en el episodio
    carril_dominante   = episode.get("carril_dominante", "unknown")
    tareas_completadas = episode.get("tareas_completadas", 0)
    # Chroma no almacena None como metadato — se convierte a string sentinel
    exitoso_raw = episode.get("exitoso", None)
    if exitoso_raw is True:
        exitoso_str = "true"
    elif exitoso_raw is False:
        exitoso_str = "false"
    else:
        exitoso_str = "unmarked"   # valor sentinel — sin marcar aún

    doc_id   = f"{date}T{time_}"
    metadata = {
        "date":               date,
        "time":               time_,
        "turns":              turns,
        "source":             "episode",
        "carril_dominante":   carril_dominante,
        "tareas_completadas": tareas_completadas,
        "exitoso":            exitoso_str,
    }
    # El texto indexado combina fecha + resumen para que
    # preguntas como '¿qué pasó el 18 de mayo?' también funcionen.
    content = f"[{date} {time_}] ({turns} turnos)\n{summary}"
    return doc_id, metadata, content


# ─────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────

def index_episode(episode: dict) -> bool:
    """Indexa un único episodio en Chroma (experience_index).

    Idempotente: si el episodio ya existe (mismo ID), Chroma lo actualiza
    sin duplicar.

    Args:
        episode: dict con keys date, time, turns, summary y opcionales
                 carril_dominante, tareas_completadas, exitoso.

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

    Devuelve también los metadatos enriquecidos (exitoso, carril_dominante)
    para que intelligence.py pueda filtrar por calidad.

    Args:
        query: Texto de búsqueda.
        k:     Número de resultados a devolver. Default 3.

    Returns:
        Lista de dicts con keys: summary, date, time, turns, score,
        exitoso, carril_dominante.
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
            meta = doc.metadata
            exitoso_str = meta.get("exitoso", "unmarked")
            if exitoso_str == "true":
                exitoso = True
            elif exitoso_str == "false":
                exitoso = False
            else:
                exitoso = None  # sin marcar
            episodes_found.append({
                "summary":          doc.page_content,
                "date":             meta.get("date", "?"),
                "time":             meta.get("time", "?"),
                "turns":            meta.get("turns", 0),
                "score":            round(score, 3),
                "exitoso":          exitoso,
                "carril_dominante": meta.get("carril_dominante", "unknown"),
            })
        log.info(f"[episode_store] search '{query[:40]}' → {len(episodes_found)} resultados")
        return episodes_found
    except Exception as exc:
        log.warning(f"[episode_store] error en búsqueda episódica: {exc}")
        return []


def experience_lookup(query: str) -> str | None:
    """Busca experiencias previas relevantes para inyectar en contexto RAG.

    Diseñada para ser llamada desde _decide_rag() en intelligence.py.
    Solo devuelve resultado si score >= EXPERIENCE_INJECT_THRESHOLD (0.80).

    Prioriza episodios marcados como exitosos sobre los no marcados.
    Ignora episodios marcados como fallidos (exitoso=False) si hay
    alternativos con score >= 0.65.

    Args:
        query: pregunta actual del usuario.

    Returns:
        Texto de contexto listo para concatenar al prompt RAG, o None
        si no hay experiencias suficientemente relevantes.

    Never raises.
    """
    col = _get_collection()
    if col is None:
        return None
    try:
        results = col.similarity_search_with_relevance_scores(query, k=5)
        # Filtrar por umbral de inyección
        candidates = [
            (doc, score) for doc, score in results
            if score >= EXPERIENCE_INJECT_THRESHOLD
        ]
        if not candidates:
            return None

        # Separar exitosos de fallidos
        successful = [
            (doc, score) for doc, score in candidates
            if doc.metadata.get("exitoso") == "true"
        ]
        failed = [
            (doc, score) for doc, score in candidates
            if doc.metadata.get("exitoso") == "false"
        ]
        unmarked = [
            (doc, score) for doc, score in candidates
            if doc.metadata.get("exitoso", "unmarked") == "unmarked"
        ]

        # Preferencia: exitosos > sin marcar > fallidos (solo si no hay alternativas)
        if successful:
            selected = successful
        elif unmarked:
            selected = unmarked
        else:
            # Solo fallidos disponibles — incluir con advertencia
            selected = failed

        if not selected:
            return None

        # Tomar el mejor resultado
        best_doc, best_score = max(selected, key=lambda x: x[1])
        date = best_doc.metadata.get("date", "?")
        time_ = best_doc.metadata.get("time", "?")
        summary_text = best_doc.page_content
        # Limpiar encabezado [fecha hora] si está incluido en el content
        if summary_text.startswith("["):
            nl = summary_text.find("\n")
            summary_text = summary_text[nl + 1:].strip() if nl != -1 else summary_text

        log.debug(
            "[episode_store] experience_lookup: hit en %sT%s (score=%.3f)",
            date, time_, best_score,
        )
        return (
            f"[Experiencia previa relevante — {date} {time_}, score={best_score:.2f}]\n"
            f"{summary_text}"
        )
    except Exception as exc:
        log.warning(f"[episode_store] experience_lookup error: {exc}")
        return None


def mark_episode(doc_id: str, exitoso: bool) -> bool:
    """Actualiza el metadato 'exitoso' de un episodio ya indexado.

    Usado por 8C al final de la sesión cuando el usuario responde s/n.
    Como Chroma no soporta update in-place de metadatos, re-indexamos
    el documento con los metadatos actualizados.

    Args:
        doc_id:  ID del episodio (ej: '2026-05-19T10:30').
        exitoso: True si la sesión fue productiva, False si no.

    Returns:
        True si se actualizó, False si fallo.

    Never raises.
    """
    col = _get_collection()
    if col is None:
        return False
    try:
        # Recuperar el documento existente
        result = col.get(ids=[doc_id], include=["documents", "metadatas"])
        if not result["ids"]:
            log.warning("[episode_store] mark_episode: ID '%s' no encontrado", doc_id)
            return False

        content  = result["documents"][0]
        metadata = result["metadatas"][0]
        metadata["exitoso"] = "true" if exitoso else "false"

        # Reemplazar el documento con metadatos actualizados
        col.delete(ids=[doc_id])
        col.add_texts(texts=[content], metadatas=[metadata], ids=[doc_id])
        log.info("[episode_store] mark_episode: %s marcado como exitoso=%s", doc_id, exitoso)
        return True
    except Exception as exc:
        log.warning("[episode_store] mark_episode error: %s", exc)
        return False


def close_session_episode() -> None:
    """Cierre de sesión: actualiza metadatos del episodio activo y pregunta al usuario.

    Flujo (8C):
      1. Obtiene el doc_id del episodio activo desde session_state.
      2. Actualiza carril_dominante y tareas_completadas en Chroma.
      3. Pregunta '¿Fue productiva esta sesión? (s/n)' con timeout 15s.
      4. Llama mark_episode() con el resultado.

    Si el usuario no responde en 15 segundos → cierre silencioso (unmarked).
    Si el episodio no existe en Chroma todavía → solo loggea y continúa.

    Never raises.
    """
    try:
        from app.session_state import (
            get_session_doc_id,
            get_carril_dominante,
            get_tareas_completadas,
        )

        doc_id             = get_session_doc_id()
        carril_dominante   = get_carril_dominante()
        tareas_completadas = get_tareas_completadas()

        col = _get_collection()
        if col is None:
            return

        # Intentar actualizar carril_dominante y tareas_completadas
        result = col.get(ids=[doc_id], include=["documents", "metadatas"])
        if result["ids"]:
            content  = result["documents"][0]
            metadata = result["metadatas"][0]
            metadata["carril_dominante"]   = carril_dominante
            metadata["tareas_completadas"] = tareas_completadas
            col.delete(ids=[doc_id])
            col.add_texts(texts=[content], metadatas=[metadata], ids=[doc_id])
            log.info(
                "[episode_store] close_session: %s actualizado (carril=%s, tareas=%d)",
                doc_id, carril_dominante, tareas_completadas,
            )
        else:
            log.info(
                "[episode_store] close_session: episodio %s no encontrado en índice — "
                "probablemente sesión sin turnos completados.",
                doc_id,
            )
            return

        # Preguntar al usuario con timeout
        import signal

        def _timeout_handler(signum, frame):
            raise TimeoutError

        try:
            # En Windows signal.SIGALRM no existe — usar threading como fallback
            import threading
            answered = threading.Event()
            respuesta = [None]

            def _ask():
                try:
                    r = input("\n❓ ¿Fue productiva esta sesión? (s/n): ").strip().lower()
                    respuesta[0] = r
                finally:
                    answered.set()

            t = threading.Thread(target=_ask, daemon=True)
            t.start()
            t.join(timeout=15)

            if not answered.is_set() or respuesta[0] is None:
                log.info("[episode_store] close_session: sin respuesta en 15s — episodio sin marcar")
                return

            if respuesta[0] in ("s", "si", "sí", "y", "yes"):
                mark_episode(doc_id, exitoso=True)
                print("✅ Sesión marcada como productiva.")
            elif respuesta[0] in ("n", "no"):
                mark_episode(doc_id, exitoso=False)
                print("📝 Sesión marcada para revisión.")
            else:
                log.info("[episode_store] close_session: respuesta '%s' no reconocida — sin marcar", respuesta[0])

        except Exception as exc:
            log.warning("[episode_store] close_session: error al preguntar — %s", exc)

    except Exception as exc:
        log.warning("[episode_store] close_session_episode error: %s", exc)


def reindex_all() -> int:
    """Re-indexa TODOS los episodios de episodic_memory.json desde cero.

    Útil cuando:
    - Se cambia el formato del episodio.
    - Se quiere reconstruir el índice tras una corrupción.
    - Se migra desde la versión sin índice (o con colección 'episodios' antigua).

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
                log.info(
                    "[episode_store] reindex_all: eliminados %d docs previos",
                    len(existing_ids),
                )
        except Exception:
            pass  # colección vacía: no hay nada que borrar

        # Indexar todos los episodios
        count = 0
        for ep in episodes:
            if index_episode(ep):
                count += 1

        log.info("[episode_store] reindex_all: %d/%d episodios indexados", count, len(episodes))
        return count
    except Exception as exc:
        log.warning("[episode_store] reindex_all error: %s", exc)
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
        log.warning("[episode_store] stats error: %s", exc)
        return {
            "indexed_count": 0,
            "collection":    EPISODE_COLLECTION,
            "chroma_dir":    str(CHROMA_DIR),
            "available":     False,
        }
