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
  3. intelligence.py _retrieve_rag_context() llama experience_lookup_with_score()
     para inyectar contexto episódico relevante en todos los carriles RAG.
     El score se expone explícitamente para que intelligence.py aplique
     su propio umbral (_MIN_EXPERIENCE_SCORE = 0.70) — D3.
  4. (8C) al cerrar sesión, close_session_episode() pregunta al usuario y
     llama mark_episode() para marcar exitoso=True/False.

Convenciones:
  - Colección Chroma: EPISODE_COLLECTION = 'experience_index'
  - ID de cada documento: ISO timestamp del episodio (ej: '2026-05-19T10:30')
  - Metadatos almacenados: date, time, turns, source, carril_dominante,
    tareas_completadas, exitoso
  - Namespace físico: storage/chroma  (misma instancia que documentos,
    colección diferente — Chroma las aísla automáticamente)

Brecha 1 (resuelta):
  mark_episode() ahora sincroniza exitoso también en episodic_memory.json.
  Antes: load_last_episode() siempre devólvia exitoso=None porque Chroma
  y el JSON estaban desincronizados. Ahora ambos tienen el mismo valor.

Never raises: todos los métodos públicos capturan excepciones y loggean.

D6  — decay temporal (Park et al. 2023 — Generative Agents) (CERRADO):
  score_final = DECAY_ALPHA * score_semántico + (1-DECAY_ALPHA) * e^(-DECAY_LAMBDA * días)
  _DECAY_ALPHA  = 0.75  (peso del score semántico vs. recencia)
  _DECAY_LAMBDA = 0.05  (velocidad de decaimiento — suave, no agresivo)
  Efecto: episodio de hoy × 1.0. 30 días × 0.89. 90 días × 0.78.
  Se aplica en search_episodes() y experience_lookup_with_score().
  El boost de exitosos (8C) se aplica sobre score post-decay.
  Fallback: sin fecha válida, el score no se modifica.
"""
from __future__ import annotations

import json
import math
from datetime import date as _date_cls, datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from app.logger import get_logger

if TYPE_CHECKING:
    from app.schemas import EpisodeItem

log = get_logger("episode_store")

# ─────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────

EPISODE_COLLECTION   = "experience_index"
EPISODIC_MEMORY_FILE = Path("storage") / "episodic_memory.json"
CHROMA_DIR           = Path("storage") / "chroma"

_MIN_RELEVANCE_SCORE = 0.20
EXPERIENCE_INJECT_THRESHOLD = 0.80
_EXITOSO_BOOST = 0.15
_FALLIDO_HIDE_THRESHOLD = 0.65

_DECAY_ALPHA  = 0.75
_DECAY_LAMBDA = 0.05

# ─────────────────────────────────────────────
# Inicialización lazy del cliente Chroma
# ─────────────────────────────────────────────

_collection = None


def _get_collection():
    """Devuelve (creando si no existe) la colección 'experience_index' en Chroma."""
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
    """Convierte un EpisodeItem a (id, metadata, page_content) para Chroma."""
    date    = episode.get("date", "unknown")
    time_   = episode.get("time", "00:00")
    turns   = episode.get("turns", 0)
    summary = episode.get("summary", "").strip()

    carril_dominante   = episode.get("carril_dominante", "unknown")
    tareas_completadas = episode.get("tareas_completadas", 0)
    exitoso_raw = episode.get("exitoso", None)
    if exitoso_raw is True:
        exitoso_str = "true"
    elif exitoso_raw is False:
        exitoso_str = "false"
    else:
        exitoso_str = "unmarked"

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
    content = f"[{date} {time_}] ({turns} turnos)\n{summary}"
    return doc_id, metadata, content


def _mark_exitoso_in_json(doc_id: str, exitoso: bool) -> None:
    """Brecha 1: sincroniza el campo exitoso en episodic_memory.json.

    doc_id tiene el formato 'YYYY-MM-DDTHH:MM' (ej: '2026-05-22T15:05').
    Busca el episodio cuya combinación date+time coincide y escribe exitoso.

    Se llama siempre después de mark_episode() para mantener JSON y Chroma
    sincronizados. Si el episodio no se encuentra en el JSON, loggea y sigue.

    Never raises.
    """
    try:
        if not EPISODIC_MEMORY_FILE.exists():
            return

        with open(EPISODIC_MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        episodes = data.get("episodes", [])
        # doc_id = 'YYYY-MM-DDTHH:MM'  →  date='YYYY-MM-DD', time='HH:MM'
        parts = doc_id.split("T", 1)
        if len(parts) != 2:
            log.warning("[episode_store] _mark_exitoso_in_json: doc_id mal formado '%s'", doc_id)
            return

        ep_date, ep_time = parts[0], parts[1]
        updated = False
        for ep in episodes:
            if ep.get("date") == ep_date and ep.get("time") == ep_time:
                ep["exitoso"] = exitoso
                updated = True
                break

        if updated:
            data["episodes"] = episodes
            with open(EPISODIC_MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            log.info(
                "[episode_store] _mark_exitoso_in_json: %s → exitoso=%s",
                doc_id, exitoso,
            )
        else:
            log.warning(
                "[episode_store] _mark_exitoso_in_json: episodio %s no encontrado en JSON",
                doc_id,
            )
    except Exception as exc:
        log.warning("[episode_store] _mark_exitoso_in_json error: %s", exc)


def _apply_recency_decay(semantic_score: float, episode_date_str: str) -> float:
    """D6: aplica decay temporal al score semántico.

    Fórmula (Generative Agents — Park et al. 2023):
        score_final = alpha * score_sem + (1 - alpha) * e^(-lambda * días)

    Fallback: si la fecha no es parseable, devuelve el score original sin modificar.
    Never raises.
    """
    try:
        ep_date  = datetime.strptime(episode_date_str, "%Y-%m-%d").date()
        today    = _date_cls.today()
        days_ago = max((today - ep_date).days, 0)
        recency  = math.exp(-_DECAY_LAMBDA * days_ago)
        final    = _DECAY_ALPHA * semantic_score + (1.0 - _DECAY_ALPHA) * recency
        return round(min(final, 1.0), 4)
    except Exception:
        return semantic_score


def _extract_best_candidate(
    results: list,
    inject_threshold: float,
) -> tuple[str, float] | tuple[None, float]:
    """Helper interno: selecciona el mejor episodio candidato para inyección."""
    candidates = [
        (doc, score) for doc, score in results
        if score >= inject_threshold
    ]
    if not candidates:
        return None, 0.0

    successful = [(d, s) for d, s in candidates if d.metadata.get("exitoso") == "true"]
    unmarked   = [(d, s) for d, s in candidates if d.metadata.get("exitoso", "unmarked") == "unmarked"]
    failed     = [(d, s) for d, s in candidates if d.metadata.get("exitoso") == "false"]

    if successful:
        selected = successful
    elif unmarked:
        selected = unmarked
    else:
        selected = failed

    if not selected:
        return None, 0.0

    best_doc, best_score = max(selected, key=lambda x: x[1])
    date      = best_doc.metadata.get("date", "?")
    time_     = best_doc.metadata.get("time", "?")
    summary_text = best_doc.page_content
    if summary_text.startswith("["):
        nl = summary_text.find("\n")
        summary_text = summary_text[nl + 1:].strip() if nl != -1 else summary_text

    snippet = (
        f"[Experiencia previa relevante — {date} {time_}, score={best_score:.2f}]\n"
        f"{summary_text}"
    )
    return snippet, best_score


# ─────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────

def index_episode(episode: dict) -> bool:
    """Indexa un único episodio en Chroma (experience_index). Idempotente."""
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

    D6: aplica decay temporal (_apply_recency_decay) antes del boost.
    Aplica boost de calidad (8C): exitosos +0.15, fallidos descartados si hay
    alternativos con score >= 0.65.
    Orden final de operaciones: score_sem → decay → boost_exitoso → ranking.
    """
    col = _get_collection()
    if col is None:
        return []
    try:
        results = col.similarity_search_with_relevance_scores(query, k=k)

        candidates = []
        for doc, raw_score in results:
            if raw_score < _MIN_RELEVANCE_SCORE:
                continue

            meta = doc.metadata
            episode_date = meta.get("date", "")
            exitoso_str  = meta.get("exitoso", "unmarked")

            decayed_score = _apply_recency_decay(raw_score, episode_date)

            if exitoso_str == "true":
                exitoso = True
                boosted_score = min(decayed_score + _EXITOSO_BOOST, 1.0)
            elif exitoso_str == "false":
                exitoso = False
                boosted_score = decayed_score
            else:
                exitoso = None
                boosted_score = decayed_score

            candidates.append({
                "summary":          doc.page_content,
                "date":             meta.get("date", "?"),
                "time":             meta.get("time", "?"),
                "turns":            meta.get("turns", 0),
                "score":            round(boosted_score, 3),
                "exitoso":          exitoso,
                "carril_dominante": meta.get("carril_dominante", "unknown"),
            })

        if not candidates:
            return []

        best_non_failed_score = max(
            (ep["score"] for ep in candidates if ep["exitoso"] is not False),
            default=0.0,
        )
        if best_non_failed_score >= _FALLIDO_HIDE_THRESHOLD:
            candidates = [ep for ep in candidates if ep["exitoso"] is not False]

        candidates.sort(key=lambda x: x["score"], reverse=True)
        log.info(f"[episode_store] search '{query[:40]}' → {len(candidates)} resultados")
        return candidates
    except Exception as exc:
        log.warning(f"[episode_store] error en búsqueda episódica: {exc}")
        return []


def experience_lookup_with_score(query: str) -> tuple[str, float] | tuple[None, float]:
    """D3: variante de experience_lookup que expone el score al llamador.

    D6: el score devuelto ya incluye decay temporal.
    Never raises.
    """
    col = _get_collection()
    if col is None:
        return None, 0.0
    try:
        results = col.similarity_search_with_relevance_scores(query, k=5)

        results_with_decay = [
            (doc, _apply_recency_decay(raw_score, doc.metadata.get("date", "")))
            for doc, raw_score in results
        ]

        snippet, score = _extract_best_candidate(results_with_decay, EXPERIENCE_INJECT_THRESHOLD)
        if snippet:
            log.debug(
                "[episode_store] experience_lookup_with_score: score=%.3f (con decay) para '%s'",
                score, query[:40],
            )
        return snippet, score
    except Exception as exc:
        log.warning(f"[episode_store] experience_lookup_with_score error: {exc}")
        return None, 0.0


def experience_lookup(query: str) -> str | None:
    """Busca experiencias previas relevantes para inyectar en contexto RAG.

    DEPRECATED para uso interno en intelligence.py — usar experience_lookup_with_score().
    Se mantiene por compatibilidad con código externo o tests que lo llamen directamente.
    """
    snippet, _ = experience_lookup_with_score(query)
    return snippet


def mark_episode(doc_id: str, exitoso: bool) -> bool:
    """Actualiza el metadato 'exitoso' de un episodio ya indexado en Chroma y en JSON.

    Brecha 1: ahora sincroniza exitoso en AMBOS almacenamientos:
      1. Chroma (experience_index) — como antes.
      2. episodic_memory.json — nuevo, via _mark_exitoso_in_json().

    Esto garantiza que load_last_episode() devuelva exitoso correcto
    en la próxima sesión, habilitándolo en Session Intelligence (get_session_briefing).
    Never raises.
    """
    col = _get_collection()
    if col is None:
        # Sin Chroma igual actualizamos el JSON
        _mark_exitoso_in_json(doc_id, exitoso)
        return False
    try:
        result = col.get(ids=[doc_id], include=["documents", "metadatas"])
        if not result["ids"]:
            log.warning("[episode_store] mark_episode: ID '%s' no encontrado en Chroma", doc_id)
            # Intentamos el JSON de todas formas
            _mark_exitoso_in_json(doc_id, exitoso)
            return False

        content  = result["documents"][0]
        metadata = result["metadatas"][0]
        metadata["exitoso"] = "true" if exitoso else "false"

        col.delete(ids=[doc_id])
        col.add_texts(texts=[content], metadatas=[metadata], ids=[doc_id])
        log.info("[episode_store] mark_episode: %s marcado como exitoso=%s en Chroma", doc_id, exitoso)

        # Brecha 1: sincronizar también en episodic_memory.json
        _mark_exitoso_in_json(doc_id, exitoso)

        return True
    except Exception as exc:
        log.warning("[episode_store] mark_episode error: %s", exc)
        return False


def close_session_episode() -> None:
    """Cierre de sesión: actualiza metadatos del episodio activo y pregunta al usuario (8C)."""
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
                "[episode_store] close_session: episodio %s no encontrado — "
                "sesión sin turnos completados.",
                doc_id,
            )
            return

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
        t.join(timeout=90)

        if not answered.is_set() or respuesta[0] is None:
            log.info("[episode_store] close_session: sin respuesta en 90s — sin marcar")
            return

        if respuesta[0] in ("s", "si", "sí", "y", "yes"):
            mark_episode(doc_id, exitoso=True)
            print("✅ Sesión marcada como productiva.")
        elif respuesta[0] in ("n", "no"):
            mark_episode(doc_id, exitoso=False)
            print("📝 Sesión marcada para revisión.")
        else:
            log.info("[episode_store] close_session: respuesta '%s' no reconocida", respuesta[0])

    except Exception as exc:
        log.warning("[episode_store] close_session_episode error: %s", exc)


def reindex_all() -> int:
    """Re-indexa TODOS los episodios de episodic_memory.json desde cero."""
    global _collection
    try:
        if not EPISODIC_MEMORY_FILE.exists():
            return 0

        with open(EPISODIC_MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        episodes = data.get("episodes", [])
        if not episodes:
            return 0

        _collection = None
        col = _get_collection()
        if col is None:
            return 0

        try:
            existing_ids = col.get()["ids"]
            if existing_ids:
                col.delete(ids=existing_ids)
        except Exception:
            pass

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
    """Devuelve estadísticas del índice episódico."""
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
