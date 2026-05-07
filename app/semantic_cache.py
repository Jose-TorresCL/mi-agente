"""Caché semántica para el carril RAG — 10c

Cómo funciona:
  1. Antes de llamar al LLM, se calcula el embedding de la pregunta nueva.
  2. Se compara contra los embeddings de preguntas ya cacheadas.
  3. Si la similitud coseno supera SIMILARITY_THRESHOLD, se devuelve
     la respuesta guardada sin tocar Chroma ni el LLM.
  4. Si no hay hit, el flujo RAG normal sigue y al final guarda el par
     (embedding, respuesta) para futuras consultas.

Configuración:
  SIMILARITY_THRESHOLD — qué tan parecidas deben ser dos preguntas para
    considerarlas iguales.
    0.82: equilibrio entre precisión y hit-rate para español con/sin tilde.
    0.86: más conservador (antiguo valor).
    0.88: muy conservador — 'cómo funciona el router' y 'explica el router'
          tienen ~0.91 → se cachean juntas solo si bajan a 0.88.

  MAX_CACHE_SIZE — número máximo de entradas. Al superar el límite se
    descartan las más antiguas (FIFO).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from datetime import datetime

from app.logger import get_logger

log = get_logger(__name__)


CACHE_FILE          = Path("storage/semantic_cache.json")
SIMILARITY_THRESHOLD = 0.82
MAX_CACHE_SIZE      = 200
EMBED_MODEL         = "nomic-embed-text"
OLLAMA_URL          = "http://localhost:11434"

# Singleton de embeddings en memoria — no recrea el cliente en cada consulta
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


def _load_cache() -> list[dict]:
    """Lee la caché desde disco. Devuelve lista vacía si no existe o está dañada."""
    if not CACHE_FILE.exists():
        return []
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("entries", [])
    except (json.JSONDecodeError, OSError):
        return []


def _save_cache(entries: list[dict]) -> None:
    """Escribe la caché en disco."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({"entries": entries}, f, ensure_ascii=False, indent=2)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similitud coseno entre dos vectores. Puro Python, sin numpy."""
    dot   = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def get_embedding(text: str) -> list[float] | None:
    """Obtiene el embedding de un texto usando Ollama. Devuelve None si falla."""
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
    """Busca una respuesta cacheada para la pregunta.

    Devuelve la respuesta guardada si hay un hit semántico,
    o None si no hay ninguna entrada suficientemente similar.
    """
    entries = _load_cache()
    if not entries:
        return None

    q_embedding = get_embedding(question)
    if q_embedding is None:
        return None  # Ollama no disponible → flujo normal

    best_sim   = 0.0
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
    """Guarda un par (pregunta, respuesta) en la caché.

    Si ya existe una entrada con similitud >= 0.99 (prácticamente idéntica),
    no guarda duplicado.
    Descarta entradas antiguas si se supera MAX_CACHE_SIZE.
    """
    q_embedding = get_embedding(question)
    if q_embedding is None:
        return  # no guardar si no hay embedding

    entries = _load_cache()

    # Evitar duplicados casi exactos
    for entry in entries:
        cached_emb = entry.get("embedding")
        if cached_emb and _cosine_similarity(q_embedding, cached_emb) >= 0.99:
            return  # ya existe, no duplicar

    entries.append({
        "question":  question,
        "answer":    answer,
        "embedding": q_embedding,
        "saved_at":  datetime.now().isoformat(timespec="seconds"),
    })

    # FIFO: si supera el límite, descartar los más viejos
    if len(entries) > MAX_CACHE_SIZE:
        entries = entries[-MAX_CACHE_SIZE:]

    _save_cache(entries)
    log.debug("[cache] entrada guardada para: %s", question[:60])


def cache_invalidate() -> None:
    """Borra toda la caché semántica (se llama desde !reset)."""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
    log.info("[cache] caché semántica limpiada.")


def cache_stats() -> dict:
    """Devuelve estadísticas básicas de la caché para !estado."""
    entries = _load_cache()
    return {
        "entries":   len(entries),
        "max_size":  MAX_CACHE_SIZE,
        "threshold": SIMILARITY_THRESHOLD,
    }
