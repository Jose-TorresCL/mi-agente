from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

# Contrato canonico: app.metrics escribe una linea JSON por turno aqui.
METRICS_FILE = Path("storage") / "logs" / "metrics.jsonl"


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return default if value is None else float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        return default if value is None else int(value)
    except (TypeError, ValueError):
        return default


def _load_metrics() -> list[dict]:
    if not METRICS_FILE.exists():
        return []

    rows: list[dict] = []
    for line in METRICS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _format_seconds(seconds: float) -> str:
    seconds = _safe_float(seconds)
    if seconds >= 60:
        return f"{seconds / 60:.1f} min"
    if seconds >= 1:
        return f"{seconds:.1f} s"
    return f"{seconds * 1000:.0f} ms"


def _box_line(text: str, width: int = 66) -> str:
    return f"| {text:<{width - 4}} |"


def _separator(width: int = 66) -> str:
    return "+" + "-" * (width - 2) + "+"


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _duration_from_row(row: dict) -> float:
    if row.get("total_ms") is not None:
        return _safe_float(row.get("total_ms")) / 1000

    for key in ("total_time_s", "duration_s", "elapsed_s", "total_seconds"):
        if row.get(key) is not None:
            return _safe_float(row.get(key))

    start = _parse_ts(row.get("started_at") or row.get("start_time"))
    end = _parse_ts(row.get("finished_at") or row.get("end_time") or row.get("timestamp"))
    return max((end - start).total_seconds(), 0.0) if start and end else 0.0


def _llm_time_from_row(row: dict) -> float:
    if row.get("llm_ms") is not None:
        return _safe_float(row.get("llm_ms")) / 1000
    for key in ("llm_time_s", "generation_time_s", "llm_seconds", "model_time_s"):
        if row.get(key) is not None:
            return _safe_float(row.get(key))
    return 0.0


def _retrieval_time_from_row(row: dict) -> float:
    if row.get("retrieval_ms") is not None:
        return _safe_float(row.get("retrieval_ms")) / 1000
    for key in ("retrieval_time_s", "retrieval_s", "search_time_s", "rag_retrieval_time_s"):
        if row.get(key) is not None:
            return _safe_float(row.get(key))
    return 0.0


def _fidelity_time_from_row(row: dict) -> float:
    for key in ("fidelity_time_s", "fidelity_s"):
        if row.get(key) is not None:
            return _safe_float(row.get(key))
    return 0.0


def _estimated_tokens_from_row(row: dict) -> int:
    for key in ("tokens_est", "tokens_total", "estimated_tokens", "tokens_estimated", "total_tokens"):
        if row.get(key) is not None:
            return _safe_int(row.get(key))
    return 0


def _docs_count_from_row(row: dict) -> int | None:
    for key in ("num_docs", "docs_count", "retrieved_docs", "chunks_count", "context_docs"):
        if row.get(key) is not None:
            return _safe_int(row.get(key))
    return None


def _intent_from_row(row: dict) -> str:
    return row.get("intent_type") or row.get("intent") or row.get("memory_intent") or row.get("lane") or "unknown"


def _lane_from_row(row: dict) -> str:
    return row.get("route") or row.get("lane") or "unknown"


def _cache_hit_from_row(row: dict) -> bool:
    for key in ("cached", "cache_hit", "from_cache", "semantic_cache_hit"):
        value = row.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "si", "sí"}
        if isinstance(value, (int, float)):
            return bool(value)
    return False


def _timestamp_from_row(row: dict) -> str:
    return row.get("timestamp") or row.get("finished_at") or row.get("end_time") or "-"


def _ascii_bar(value: int, total: int, width: int = 12) -> str:
    return "#" * round(value * width / total) if total else ""


def _get_cache_stats() -> dict:
    try:
        from app.semantic_cache import cache_stats
        raw = cache_stats() or {}
    except Exception as exc:
        raw = {"error": str(exc)}

    entries = raw.get("entries", raw.get("total_entries", 0))
    return {
        "entries": _safe_int(entries),
        "max_size": raw.get("max_size", "?"),
        "hits": _safe_int(raw.get("hits", 0)),
        "misses": _safe_int(raw.get("misses", 0)),
        "cache_file": raw.get("cache_file", "-"),
        "file_exists": bool(raw.get("file_exists", False)),
        "raw": raw,
    }


def _show_table(rows: list[dict]) -> None:
    width = 66
    print(_separator(width))
    print(_box_line(f"METRICAS - {len(rows)} turnos analizados", width))
    print(_separator(width))

    if not rows:
        print(_box_line("No se encontraron metricas en storage/logs/metrics.jsonl", width))
        print(_separator(width))
        return

    total_times = [_duration_from_row(row) for row in rows]
    llm_times = [_llm_time_from_row(row) for row in rows if _llm_time_from_row(row) > 0]
    retrieval_times = [_retrieval_time_from_row(row) for row in rows if _retrieval_time_from_row(row) > 0]
    fidelity_times = [_fidelity_time_from_row(row) for row in rows if _fidelity_time_from_row(row) > 0]
    tokens_total = sum(_estimated_tokens_from_row(row) for row in rows)
    cache_hits = sum(_cache_hit_from_row(row) for row in rows)

    print(_box_line("TIEMPOS PROMEDIO", width))
    print(_box_line(f"  Total    : {_format_seconds(mean(total_times) if total_times else 0)}", width))
    print(_box_line(f"  LLM      : {_format_seconds(mean(llm_times) if llm_times else 0)}", width))
    print(_box_line(f"  Retrieval: {_format_seconds(mean(retrieval_times) if retrieval_times else 0)}", width))
    print(_box_line(f"  Fidelity : {_format_seconds(mean(fidelity_times) if fidelity_times else 0)}", width))
    print(_box_line(f"  Tokens estimados (total): {tokens_total}", width))
    print(_box_line(f"  Desde cache: {cache_hits}/{len(rows)} ({round(cache_hits * 100 / len(rows))}%)", width))
    print(_separator(width))

    lane_counts = Counter(_lane_from_row(row) for row in rows)
    print(_box_line("DISTRIBUCION POR CARRIL", width))
    for lane, count in lane_counts.most_common():
        print(_box_line(f"  {lane:<24} {count:>3} ({round(count * 100 / len(rows)):>3}%) {_ascii_bar(count, len(rows))}", width))
    print(_separator(width))

    print(_box_line("TOP 3 TURNOS MAS LENTOS", width))
    for index, row in enumerate(sorted(rows, key=_duration_from_row, reverse=True)[:3], start=1):
        print(_box_line(f"  {index}. {_lane_from_row(row):<20} {_format_seconds(_duration_from_row(row)):<10} {_timestamp_from_row(row)}", width))
    print(_separator(width))

    intent_groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        intent_groups[_intent_from_row(row)].append(row)
    print(_box_line("CONTEXTO POR TIPO DE INTENCION", width))
    print(_box_line("  INTENT                   TURNOS  AVG DOCS    AVG LLM", width))
    for intent, group in sorted(intent_groups.items(), key=lambda item: len(item[1]), reverse=True):
        docs = [_docs_count_from_row(row) for row in group if _docs_count_from_row(row) is not None]
        llm = [_llm_time_from_row(row) for row in group if _llm_time_from_row(row) > 0]
        avg_docs = f"{mean(docs):.1f}" if docs else "-"
        avg_llm = _format_seconds(mean(llm)) if llm else "-"
        print(_box_line(f"  {intent:<24} {len(group):>5}  {avg_docs:>8}  {avg_llm:>9}", width))
    print(_separator(width))

    stats = _get_cache_stats()
    print(_box_line("ESTADO DE CACHE SEMANTICA", width))
    print(_box_line(f"  Entradas : {stats['entries']}/{stats['max_size']}", width))
    print(_box_line(f"  Hits     : {stats['hits']}", width))
    print(_box_line(f"  Misses   : {stats['misses']}", width))
    print(_box_line(f"  Archivo  : {stats['cache_file']}", width))
    print(_box_line(f"  Existe   : {'si' if stats['file_exists'] else 'no'}", width))
    print(_separator(width))


def main() -> None:
    _show_table(_load_metrics())


if __name__ == "__main__":
    main()
