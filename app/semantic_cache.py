"""Caché semántica de respuestas RAG.

Evita llamadas repetidas al LLM para preguntas funcionalmente equivalentes.
Usa embeddings coseno para detectar preguntas similares (no idénticas).

Arquitectura:
  - Almacenamiento: lista en memoria (CACHE) + archivo JSON en storage/
  - Similitud: embeddings de Ollama via /api/embeddings + coseno
  - Lookup: busca la entrada más similar; devuelve la respuesta si sim >= CACHE_THRESHOLD
  - Persistencia: se carga al importar el módulo y se guarda en cada cache_save()

Constantes de configuración:
  CACHE_THRESHOLD = 0.85   Similitud mínima para considerar un hit
  CACHE_MAX_SIZE  = 200    Máximo de entradas en el caché (FIFO)

Funciones públicas:
  get_embedding(text)          → list[float] | None
  cache_lookup(query)          → str | None
  cache_save(query, answer)    → None
  cache_stats()                → dict
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import requests

from app.config import MODEL_NAME, OLLAMA_URL
from app.logger import get_logger

log = get_logger(__name__)

CACHE_THRESHOLD   = 0.85
CACHE_MAX_SIZE    = 200
_EMBED_TIMEOUT    = 90   # subido de 10s: bajo carga CPU el embed puede tardar más
_EMBED_RETRIES    = 2    # reintentos si falla (total: 3 intentos)
_EMBED_RETRY_WAIT = 10   # segundos de espera entre reintentos

_CACHE_FILE = Path("storage") / "semantic_cache.json"

# Estructura interna: lista de dicts {"query": str, "answer": str, "embedding": list[float]}
CACHE: list[dict] = []


def _load_cache() -> None:
    """Carga el caché desde disco al inicializar el módulo."""
    global CACHE
    if not _CACHE_FILE.exists():
        return
    try:
        data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            CACHE = data
            log.debug("Caché semántica cargada: %d entradas", len(CACHE))
    except Exception as exc:
        log.warning("No se pudo cargar semantic_cache.json: %s", exc)


def _save_cache() -> None:
    """Persiste el caché en disco después de cada escritura."""
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(
            json.dumps(CACHE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        log.warning("No se pudo guardar semantic_cache.json: %s", exc)


def _cosine(a: list[float], b: list[float]) -> float:
    """Similitud coseno entre dos vectores de igual longitud."""
    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def get_embedding(text: str) -> list[float] | None:
    """Obtiene el embedding de un texto desde Ollama, con reintentos.

    Bajo carga CPU (el LLM genera en paralelo), Ollama puede tardar más de
    los 10s originales. Por eso el timeout sube a 90s y se hacen hasta
    _EMBED_RETRIES reintentos con _EMBED_RETRY_WAIT segundos de espera.

    Peor caso: 3 × 90s + 2 × 10s = 290s antes de devolver None.

    Args:
        text: Texto a embeber. No se trunca — el llamador es responsable de
              limitar la longitud si es necesario (ver _MAX_CONTEXT_CHARS en fidelity_check).

    Returns:
        Lista de floats con el vector de embedding, o None si todos los
        intentos fallaron. Nunca lanza excepciones.
    """
    last_exc: Exception | None = None
    for attempt in range(1 + _EMBED_RETRIES):
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": MODEL_NAME, "prompt": text},
                timeout=_EMBED_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json().get("embedding")
        except Exception as exc:
            last_exc = exc
            if attempt < _EMBED_RETRIES:
                log.debug(
                    "get_embedding intento %d falló, reintentando en %ds: %s",
                    attempt + 1, _EMBED_RETRY_WAIT, exc,
                )
                time.sleep(_EMBED_RETRY_WAIT)
    log.debug("get_embedding falló tras %d intentos: %s", 1 + _EMBED_RETRIES, last_exc)
    return None


def cache_lookup(query: str) -> str | None:
    """Busca en el caché semántico una respuesta para la consulta dada."""
    if not CACHE:
        return None
    q_emb = get_embedding(query)
    if q_emb is None:
        return None

    best_score = 0.0
    best_answer: str | None = None
    for entry in CACHE:
        stored_emb = entry.get("embedding")
        if not stored_emb:
            continue
        score = _cosine(q_emb, stored_emb)
        if score > best_score:
            best_score = score
            best_answer = entry["answer"]

    if best_score >= CACHE_THRESHOLD:
        log.debug("[cache:hit] sim=%.3f query='%s'", best_score, query[:60])
        return best_answer

    log.debug("[cache:miss] best_sim=%.3f query='%s'", best_score, query[:60])
    return None


def cache_save(query: str, answer: str) -> None:
    """Guarda una nueva entrada en el caché semántico."""
    q_emb = get_embedding(query)
    if q_emb is None:
        log.debug("[cache:skip] no se pudo obtener embedding para guardar")
        return

    CACHE.append({"query": query, "answer": answer, "embedding": q_emb})

    if len(CACHE) > CACHE_MAX_SIZE:
        CACHE.pop(0)

    _save_cache()
    log.debug("[cache:saved] total_entries=%d", len(CACHE))


def cache_stats() -> dict:
    """Devuelve estadísticas del estado actual del caché."""
    return {
        "total_entries": len(CACHE),
        "cache_file":    str(_CACHE_FILE),
        "file_exists":   _CACHE_FILE.exists(),
    }


# Cargar caché al importar el módulo
_load_cache()
