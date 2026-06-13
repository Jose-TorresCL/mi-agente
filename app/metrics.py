"""Registro de métricas de uso por turno de conversación.

Guarda una línea JSONL por turno en storage/logs/metrics.jsonl.
No usa base de datos ni dependencias externas — solo I/O de archivo.

Funciones públicas:
  record_turn(...)          → registra un turno en el log
  get_metrics_summary()     → dict con resumen acumulado de la sesión
  reset_metrics()           → limpia el resumen en memoria (no toca el log)

Campos registrados por turno:
  timestamp, route, intent_type, channel,
  retrieval_ms, llm_ms, tokens_est, cached, num_docs
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.logger import get_logger

log = get_logger(__name__)

_METRICS_DIR  = Path("storage") / "logs"
_METRICS_FILE = _METRICS_DIR / "metrics.jsonl"

# Acumulador en memoria para get_metrics_summary() dentro de la sesión
_SESSION_METRICS: dict[str, int | float] = {
    "turns":        0,
    "total_llm_ms": 0,
    "total_ret_ms": 0,
    "cache_hits":   0,
    "tokens_est":   0,
}


def record_turn(
    route: str,
    intent_type: str = "",
    channel: str = "cli",
    retrieval_ms: int = 0,
    llm_ms: int = 0,
    tokens_est: int = 0,
    cached: bool = False,
    num_docs: int = 0,
) -> None:
    """Registra las métricas de un turno completado en metrics.jsonl.

    Cada llamada añade una línea al archivo JSONL de métricas y actualiza
    el acumulador de sesión en memoria (_SESSION_METRICS).

    Args:
        route:        Carril de decisión (ej. 'rag', 'memory:tasks', 'exit').
        intent_type:  Tipo de intención detectada (puede coincidir con route
                      o ser más específico, ej. 'multi:tasks+work_state').
        channel:      Canal de entrada ('cli', 'telegram'). Por defecto 'cli'.
        retrieval_ms: Tiempo de recuperación Chroma en ms.
        llm_ms:       Tiempo de generación LLM en ms.
        tokens_est:   Estimación de tokens en la respuesta (len(words)*1.3).
        cached:       True si la respuesta vino del caché semántico.
        num_docs:     Número de chunks recuperados del retriever.

    Nunca lanza excepciones — los errores de escritura se loguean como WARNING.
    """
    entry = {
        "timestamp":    datetime.now().isoformat(timespec="seconds"),
        "route":        route,
        "intent_type":  intent_type,
        "channel":      channel,
        "retrieval_ms": retrieval_ms,
        "llm_ms":       llm_ms,
        "tokens_est":   tokens_est,
        "cached":       cached,
        "num_docs":     num_docs,
    }
    try:
        _METRICS_DIR.mkdir(parents=True, exist_ok=True)
        with _METRICS_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.warning("record_turn: no se pudo escribir en metrics.jsonl: %s", exc)

    # Actualizar acumulador de sesión
    _SESSION_METRICS["turns"]        += 1
    _SESSION_METRICS["total_llm_ms"] += llm_ms
    _SESSION_METRICS["total_ret_ms"] += retrieval_ms
    _SESSION_METRICS["tokens_est"]   += tokens_est
    if cached:
        _SESSION_METRICS["cache_hits"] += 1


def get_metrics_summary() -> dict:
    """Devuelve un resumen de las métricas acumuladas en la sesión actual.

    Lee el acumulador en memoria (_SESSION_METRICS), no el archivo JSONL.
    Se reinicia al llamar reset_metrics() o al reiniciar el proceso.

    Returns:
        dict con:
          turns:           Número de turnos en la sesión.
          avg_llm_ms:      Tiempo promedio de generación LLM (ms).
          avg_ret_ms:      Tiempo promedio de recuperación (ms).
          cache_hits:      Número de respuestas servidas desde caché.
          cache_rate:      Tasa de acierto de caché (0.0–1.0).
          total_tokens_est: Estimación total de tokens generados.

    Ejemplo de uso desde !estado:
        from app.metrics import get_metrics_summary
        s = get_metrics_summary()
        print(f"Turnos: {s['turns']}, Cache: {s['cache_rate']:.0%}")
    """
    turns = _SESSION_METRICS["turns"]
    return {
        "turns":             turns,
        "avg_llm_ms":        int(_SESSION_METRICS["total_llm_ms"] / turns) if turns else 0,
        "avg_ret_ms":        int(_SESSION_METRICS["total_ret_ms"] / turns) if turns else 0,
        "cache_hits":        _SESSION_METRICS["cache_hits"],
        "cache_rate":        round(_SESSION_METRICS["cache_hits"] / turns, 4) if turns else 0.0,
        "total_tokens_est":  _SESSION_METRICS["tokens_est"],
    }


def reset_metrics() -> None:
    """Reinicia el acumulador de métricas en memoria.

    No elimina ni modifica el archivo metrics.jsonl — solo limpia el
    resumen de la sesión actual. Útil para tests que necesitan partir
    de un estado limpio sin tocar el log de producción.

    Ejemplo:
        from app.metrics import reset_metrics, get_metrics_summary
        reset_metrics()
        assert get_metrics_summary()["turns"] == 0
    """
    for key in _SESSION_METRICS:
        _SESSION_METRICS[key] = 0
