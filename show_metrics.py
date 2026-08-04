from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

METRICS_FILE = Path("storage") / "metrics.jsonl"


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
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
    seconds = _safe_float(seconds, 0.0)
    if seconds >= 60:
        minutes = seconds / 60
        return f"{minutes:.1f} min"
    if seconds >= 1:
        return f"{seconds:.1f} s"
    return f"{seconds * 1000:.0f} ms"


def _box_line(text: str, width: int = 62) -> str:
    return f"║ {text:<{width - 4}} ║"


def _separator(width: int = 62) -> str:
    return "╠" + "═" * (width - 2) + "╣"


def _top_border(width: int = 62) -> str:
    return "╔" + "═" * (width - 2) + "╗"


def _bottom_border(width: int = 62) -> str:
    return "╚" + "═" * (width - 2) + "╝"


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _duration_from_row(row: dict) -> float:
    candidates = [
        row.get("total_time_s"),
        row.get("duration_s"),
        row.get("elapsed_s"),
        row.get("total_seconds"),
    ]
    for value in candidates:
        if value is not None:
            return _safe_float(value, 0.0)

    start = _parse_ts(row.get("started_at") or row.get("start_time"))
    end = _parse_ts(row.get("finished_at") or row.get("end_time") or row.get("timestamp"))
    if start and end:
        return max((end - start).total_seconds(), 0.0)

    return 0.0


def _llm_time_from_row(row: dict) -> float:
    candidates = [
        row.get("llm_time_s"),
        row.get("generation_time_s"),
        row.get("llm_seconds"),
        row.get("model_time_s"),
    ]
    for value in candidates:
        if value is not None:
            return _safe_float(value, 0.0)
    return 0.0


def _retrieval_time_from_row(row: dict) -> float:
    candidates = [
        row.get("retrieval_time_s"),
        row.get("retrieval_s"),
        row.get("search_time_s"),
        row.get("rag_retrieval_time_s"),
    ]
    for value in candidates:
        if value is not None:
            return _safe_float(value, 0.0)
    return 0.0


def _fidelity_time_from_row(row: dict) -> float:
    candidates = [
        row.get("fidelity_time_s"),
        row.get("fidelity_s"),
    ]
    for value in candidates:
        if value is not None:
            return _safe_float(value, 0.0)
    return 0.0


def _estimated_tokens_from_row(row: dict) -> int:
    candidates = [
        row.get("tokens_total"),
        row.get("estimated_tokens"),
        row.get("tokens_estimated"),
        row.get("total_tokens"),
    ]
    for value in candidates:
        if value is not None:
            return _safe_int(value, 0)
    return 0


def _docs_count_from_row(row: dict) -> int | None:
    candidates = [
        row.get("docs_count"),
        row.get("retrieved_docs"),
        row.get("chunks_count"),
        row.get("context_docs"),
    ]
    for value in candidates:
        if value is not None:
            return _safe_int(value, 0)
    return None


def _intent_from_row(row: dict) -> str:
    return (
        row.get("intent_type")
        or row.get("intent")
        or row.get("memory_intent")
        or row.get("lane")
        or "unknown"
    )


def _lane_from_row(row: dict) -> str:
    return row.get("lane") or row.get("route") or "unknown"


def _cache_hit_from_row(row: dict) -> bool:
    candidates = [
        row.get("cache_hit"),
        row.get("from_cache"),
        row.get("semantic_cache_hit"),
    ]
    for value in candidates:
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
    if total <= 0:
        return ""
    filled = round((value / total) * width)
    return "█" * filled


def _get_cache_stats() -> dict:
    try:
        from app.semantic_cache import cache_stats
        raw = cache_stats() or {}
    except Exception as e:
        return {
            "entries": 0,
            "max_size": "?",
            "hits": 0,
            "misses": 0,
            "cache_file": "-",
            "file_exists": False,
            "raw": {"error": str(e)},
        }

    entries = raw.get("entries")
    if entries is None:
        entries = raw.get("total_entries", 0)

    return {
        "entries": _safe_int(entries, 0),
        "max_size": raw.get("max_size", "?"),
        "hits": _safe_int(raw.get("hits", 0), 0),
        "misses": _safe_int(raw.get("misses", 0), 0),
        "cache_file": raw.get("cache_file", "-"),
        "file_exists": bool(raw.get("file_exists", False)),
        "raw": raw,
    }


def _show_table(rows: list[dict]) -> None:
    width = 66

    print(_top_border(width))
    print(_box_line(f"MÉTRICAS DE SESIÓN — {len(rows)} turnos analizados", width))
    print(_separator(width))

    if not rows:
        print(_box_line("No se encontraron métricas en storage/metrics.jsonl", width))
        print(_bottom_border(width))
        return

    total_times = [_duration_from_row(r) for r in rows]
    llm_times = [_llm_time_from_row(r) for r in rows if _llm_time_from_row(r) > 0]
    retrieval_times = [_retrieval_time_from_row(r) for r in rows if _retrieval_time_from_row(r) > 0]
    fidelity_times = [_fidelity_time_from_row(r) for r in rows if _fidelity_time_from_row(r) > 0]
    tokens_total = sum(_estimated_tokens_from_row(r) for r in rows)
    cache_hits = sum(1 for r in rows if _cache_hit_from_row(r))

    avg_total = mean(total_times) if total_times else 0.0
    avg_llm = mean(llm_times) if llm_times else 0.0
    avg_retrieval = mean(retrieval_times) if retrieval_times else 0.0
    avg_fidelity = mean(fidelity_times) if fidelity_times else 0.0

    print(_box_line("TIEMPOS PROMEDIO", width))
    print(_box_line(f"  Total    : {_format_seconds(avg_total)}", width))
    print(_box_line(f"  LLM      : {_format_seconds(avg_llm)}", width))
    print(_box_line(f"  Retrieval: {_format_seconds(avg_retrieval)}", width))
    print(_box_line(f"  Fidelity : {_format_seconds(avg_fidelity)}", width))
    print(_box_line(f"  Tokens estimados (total): {tokens_total}", width))
    print(_box_line(f"  Desde caché: {cache_hits}/{len(rows)} ({round(cache_hits * 100 / max(len(rows), 1))}%)", width))
    print(_separator(width))

    lane_counts = Counter(_lane_from_row(r) for r in rows)
    print(_box_line("DISTRIBUCIÓN POR CARRIL", width))
    for lane, count in lane_counts.most_common():
        pct = round(count * 100 / len(rows))
        bar = _ascii_bar(count, len(rows))
        print(_box_line(f"  {lane:<24} {count:>3}  ({pct:>3}%)  {bar}", width))
    print(_separator(width))

    slowest = sorted(
        rows,
        key=lambda r: _duration_from_row(r),
        reverse=True
    )[:3]

    print(_box_line("TOP 3 TURNOS MÁS LENTOS", width))
    for i, row in enumerate(slowest, start=1):
        lane = _lane_from_row(row)
        duration = _format_seconds(_duration_from_row(row))
        ts = _timestamp_from_row(row)
        print(_box_line(f"  {i}. {lane:<20} {duration:<10} {ts}", width))
    print(_separator(width))

    intent_groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        intent_groups[_intent_from_row(row)].append(row)

    print(_box_line("CONTEXTO POR TIPO DE INTENCIÓN (R2)", width))
    print(_box_line("  INTENT                   TURNOS  AVG DOCS    AVG LLM", width))
    print(_box_line("  --------------------------------------------------", width))
    for intent, group in sorted(intent_groups.items(), key=lambda kv: len(kv[1]), reverse=True):
        docs_values = [_docs_count_from_row(r) for r in group if _docs_count_from_row(r) is not None]
        llm_values = [_llm_time_from_row(r) for r in group if _llm_time_from_row(r) > 0]
        avg_docs = f"{mean(docs_values):.1f}" if docs_values else "-"
        avg_llm_intent = _format_seconds(mean(llm_values)) if llm_values else "-"
        print(_box_line(f"  {intent:<24} {len(group):>5}  {avg_docs:>8}  {avg_llm_intent:>9}", width))
    print(_separator(width))

    stats = _get_cache_stats()
    print(_box_line("ESTADO DE CACHÉ SEMÁNTICA", width))
    print(_box_line(f"  Entradas : {stats['entries']}/{stats['max_size']}", width))
    print(_box_line(f"  Hits     : {stats['hits']}", width))
    print(_box_line(f"  Misses   : {stats['misses']}", width))
    print(_box_line(f"  Archivo  : {stats['cache_file']}", width))
    print(_box_line(f"  Existe   : {'sí' if stats['file_exists'] else 'no'}", width))
    print(_separator(width))

    raw_keys = ", ".join(sorted(stats["raw"].keys())) if isinstance(stats["raw"], dict) else "-"
    print(_box_line("DEBUG CONTRATO CACHE", width))
    print(_box_line(f"  Claves detectadas: {raw_keys}", width))
    print(_bottom_border(width))


def main() -> None:
    rows = _load_metrics()
    _show_table(rows)


if __name__ == "__main__":
    main()