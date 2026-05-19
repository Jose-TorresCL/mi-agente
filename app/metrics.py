"""Módulo de métricas de sesión — Fase 7A.

Escribe una entrada JSON por turno en storage/metrics.jsonl (append-only).
Nunca lanza excepciones — errores de I/O se loguean como WARNING.

Esquema de cada línea:
  {
    "timestamp": "2026-05-19T10:00:00.123456",  # ISO 8601
    "route":        "rag",                        # carril elegido
    "retrieval_ms": 320,                          # tiempo de retrieval (0 si no aplica)
    "llm_ms":       1840,                         # tiempo de llamada LLM (0 si no aplica)
    "total_ms":     2160,                         # retrieval_ms + llm_ms
    "tokens_est":   210,                          # estimación simple por palabras
    "cached":        false                         # True si vino del caché semántico
  }

Uso:
    from app.metrics import record_turn
    record_turn(route="rag", retrieval_ms=320, llm_ms=1840, tokens_est=210)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.logger import get_logger

log = get_logger(__name__)

_METRICS_DIR = Path("storage")
_METRICS_FILE = _METRICS_DIR / "metrics.jsonl"


def record_turn(
    route: str,
    retrieval_ms: int = 0,
    llm_ms: int = 0,
    tokens_est: int = 0,
    cached: bool = False,
) -> None:
    """Escribe una entrada de métricas en storage/metrics.jsonl.

    Args:
        route:        Carril del router (ej: 'rag', 'memory', 'tool_list_files').
        retrieval_ms: Tiempo de retrieval vectorial en milisegundos.
        llm_ms:       Tiempo de llamada al LLM en milisegundos.
        tokens_est:   Estimación de tokens en la respuesta (palabras * 1.3).
        cached:       True si la respuesta vino del caché semántico.

    Never raises.
    """
    try:
        _METRICS_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "route": route,
            "retrieval_ms": retrieval_ms,
            "llm_ms": llm_ms,
            "total_ms": retrieval_ms + llm_ms,
            "tokens_est": tokens_est,
            "cached": cached,
        }
        with _METRICS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        log.debug(
            "[metrics] route=%s total_ms=%d cached=%s",
            route, entry["total_ms"], cached,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("[metrics] No se pudo escribir entrada: %s", exc)
