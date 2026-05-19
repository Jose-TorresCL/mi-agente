"""Caché semántica para el carril RAG — con TTL de expiración

Cómo funciona:
  1. Antes de llamar al LLM, se calcula el embedding de la pregunta nueva.
  2. Se compara contra los embeddings de preguntas ya cacheadas.
  3. Si la similitud coseno supera SIMILARITY_THRESHOLD, se devuelve
     la respuesta guardada sin tocar Chroma ni el LLM.
  4. Si no hay hit, el flujo RAG normal sigue y al final guarda el par
     (embedding, respuesta) para futuras consultas.
  5. Entradas con más de CACHE_TTL_HOURS horas se descartan automáticamente
     al leer la caché — evita envenenar respuestas con información obsoleta.

Configuración:
  SIMILARITY_THRESHOLD — qué tan parecidas deben ser dos preguntas para
    considerarlas iguales.
    0.82: equilibrio entre precisión y hit-rate para español con/sin tilde.
    0.86: más conservador (antiguo valor).

  MAX_CACHE_SIZE — número máximo de entradas. Al superar el límite se
    descartan las más antiguas (FIFO).

  CACHE_TTL_HOURS — horas de vida de cada entrada. Por defecto 24h.
    Pasado ese tiempo la entrada se descarta aunque sea semánticamente
    similar — garantiza que cambios en los docs se reflejen al día siguiente.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from datetime import datetime, timedelta

from app.logger import get_logger

log = get_logger(__name__)


CACHE_FILE           = Path("storage/semantic_cache.json")
SIMILARITY_THRESHOLD = 0.82
MAX_CACHE_SIZE       = 200
CACHE_TTL_HOURS      = 24
EMBED_MODEL          = "nomic-embed-text"
OLLAMA_URL           = "http://localhost:11434"

_embed_client = None


# ─────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────

def _get_embed_client():
    global _embed_client
    if _embed_client is None:
        from langchain_ollama import OllamaEmbeddings
        _embed_client = OllamaEmbeddings(
            model=EMBED_MODEL,
            base_url=OLLAMA_URL,
        )
    return _embed_client


def _is_expired(entry: dict) -> bool:
    """Devuelve True si la entrada supera CACHE_TTL_HOURS."""
    saved_at = entry.get("saved_at")
    if not saved_at:
        return True
    try:
        age = datetime.now() - datetime.fromisoformat(saved_at)
        return age > timedelta(hours=CACHE_TTL_HOURS)
    except (ValueError, TypeError):
        return True


def _entry_age_hours(entry: dict) -> float | None:
    """Devuelve la edad de una entrada en horas, o None si no hay saved_at."""
    saved_at = entry.get("saved_at")
    if not saved_at:
        return None
    try:
        age = datetime.now() - datetime.fromisoformat(saved_at)
        return age.total_seconds() / 3600
    except (ValueError, TypeError):
        return None


def _load_cache() -> list[dict]:
    """Lee la caché desde disco, descartando entradas expiradas."""
    if not CACHE_FILE.exists():
        return []
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        all_entries = data.get("entries", [])
    except (json.JSONDecodeError, OSError):
        return []

    valid = [e for e in all_entries if not _is_expired(e)]

    expired_count = len(all_entries) - len(valid)
    if expired_count:
        log.info("[cache] %d entrada(s) expiradas descartadas (TTL=%dh)", expired_count, CACHE_TTL_HOURS)
        _save_cache(valid)

    return valid


def _save_cache(entries: list[dict]) -> None:
    """Escribe la caché en disco."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({"entries": entries}, f, ensure_ascii=False, indent=2)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def get_embedding(text: str) -> list[float] | None:
    try:
        client = _get_embed_client()
        return client.embed_query(text)
    except Exception as e:
        log.warning("[cache] error al obtener embedding: %s", e)
        return None


# ─────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────

def cache_lookup(question: str) -> str | None:
    """Busca una respuesta cacheada para la pregunta."""
    entries = _load_cache()
    if not entries:
        return None

    q_embedding = get_embedding(question)
    if q_embedding is None:
        return None

    best_sim    = 0.0
    best_answer = None

    for entry in entries:
        cached_emb = entry.get("embedding")
        if not cached_emb:
            continue
        sim = _cosine_similarity(q_embedding, cached_emb)
        if sim > best_sim:
            best_sim    = sim
            best_answer = entry.get("answer")

    if best_sim >= SIMILARITY_THRESHOLD and best_answer:
        log.info("[cache:hit]  similitud=%.3f", best_sim)
        return best_answer

    log.debug("[cache:miss] mejor similitud=%.3f (umbral=%.2f)", best_sim, SIMILARITY_THRESHOLD)
    return None


def cache_save(question: str, answer: str) -> None:
    """Guarda un par (pregunta, respuesta) en la caché."""
    q_embedding = get_embedding(question)
    if q_embedding is None:
        return

    entries = _load_cache()

    for entry in entries:
        cached_emb = entry.get("embedding")
        if cached_emb and _cosine_similarity(q_embedding, cached_emb) >= 0.99:
            return

    entries.append({
        "question":  question,
        "answer":    answer,
        "embedding": q_embedding,
        "saved_at":  datetime.now().isoformat(timespec="seconds"),
    })

    if len(entries) > MAX_CACHE_SIZE:
        entries = entries[-MAX_CACHE_SIZE:]

    _save_cache(entries)
    log.debug("[cache] entrada guardada para: %s", question[:60])


def cache_invalidate() -> None:
    """Borra toda la caché semántica."""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
    log.info("[cache] caché semántica limpiada.")


def cache_stats() -> dict:
    """Devuelve estadísticas de la caché incluyendo edad de entradas.

    Campos devueltos:
        entries          — número de entradas válidas (no expiradas)
        max_size         — límite máximo configurado
        threshold        — umbral de similitud coseno
        ttl_hours        — tiempo de vida configurado en horas
        avg_age_hours    — edad promedio de entradas en horas
        oldest_hours     — entrada más vieja en horas
        newest_hours     — entrada más reciente en horas
        near_expiry_count — entradas con más de (TTL - 4)h (próximas a expirar)
    """
    entries = _load_cache()

    ages: list[float] = []
    for e in entries:
        age = _entry_age_hours(e)
        if age is not None:
            ages.append(age)

    near_expiry_threshold = max(0.0, CACHE_TTL_HOURS - 4)
    near_expiry_count = sum(1 for a in ages if a >= near_expiry_threshold)

    return {
        "entries":           len(entries),
        "max_size":          MAX_CACHE_SIZE,
        "threshold":         SIMILARITY_THRESHOLD,
        "ttl_hours":         CACHE_TTL_HOURS,
        "avg_age_hours":     round(sum(ages) / len(ages), 1) if ages else 0.0,
        "oldest_hours":      round(max(ages), 1) if ages else 0.0,
        "newest_hours":      round(min(ages), 1) if ages else 0.0,
        "near_expiry_count": near_expiry_count,
    }
