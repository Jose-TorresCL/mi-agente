from __future__ import annotations

import json
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

# Contrato canónico:
# app.metrics escribe una línea JSON por turno en este archivo.
METRICS_FILE = Path("storage") / "logs" / "metrics.jsonl"
BASELINES_FILE = Path("data") / "metrics_baselines.json"

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


def _load_metrics(path: Path | None = None) -> list[dict]:
    """Carga métricas desde un archivo jsonl, ignorando líneas inválidas."""
    metrics_path = path or METRICS_FILE
    if not metrics_path.exists():
        return []

    rows: list[dict] = []
    for line in metrics_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # Línea corrupta: se ignora para no romper el reporte
            continue
    return rows
def _load_baselines(path: Path | None = None) -> dict:
    """Carga baselines; devuelve {} si falta o es inválido."""
    baselines_path = path or BASELINES_FILE
    if not baselines_path.exists():
        return {}

    try:
        return json.loads(baselines_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def _resolve_baseline(value: str) -> tuple[str | None, dict | None]:
    """Resuelve 'active' o un ID explícito."""
    data = _load_baselines()
    baseline_id = data.get("active_baseline") if value == "active" else value

    if not baseline_id:
        return None, None

    for baseline in data.get("baselines", []):
        if baseline.get("id") == baseline_id:
            return baseline_id, baseline

    return baseline_id, None


def _filter_by_baseline(rows: list[dict], baseline_id: str) -> tuple[list[dict], int]:
    """Filtra filas del baseline y devuelve también cuántas fueron excluidas."""
    filtered = [row for row in rows if row.get("baseline_id") == baseline_id]
    return filtered, len(rows) - len(filtered)

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
    """Duración total del turno en segundos, con varios formatos soportados."""
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
    """Devuelve el tiempo de fidelity en segundos."""
    if row.get("fidelity_ms") is not None:
        return _safe_float(row.get("fidelity_ms")) / 1000

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
    """
    Devuelve el tipo de intención normalizado.

    Fallbacks:
    - intent_type
    - intent
    - memory_intent
    - lane
    - "unknown"
    """
    return (
        row.get("intent_type")
        or row.get("intent")
        or row.get("memory_intent")
        or row.get("lane")
        or "unknown"
    )


def _lane_from_row(row: dict) -> str:
    """
    Devuelve el carril de ejecución (lane/route) normalizado.

    Fallbacks:
    - route
    - lane
    - "unknown"
    """
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
    """
    Devuelve stats del caché semántico, o un dict con error si algo falla.
    """
    try:
        from app.semantic_cache import cache_stats
        raw = cache_stats() or {}
    except Exception as exc:  # pragma: no cover - defensa última
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


def _positive_values(fn, rows: list[dict]) -> list[float]:
    """
    Aplica un helper a cada row y devuelve solo valores > 0.
    """
    values: list[float] = []
    for row in rows:
        value = fn(row)
        if value > 0:
            values.append(value)
    return values


def _print_header(
    rows: list[dict],
    width: int,
    baseline_id: str | None = None,
    excluded: int = 0,
) -> None:
    print(_separator(width))
    print(_box_line(f"METRICAS - {len(rows)} turnos analizados", width))

    if baseline_id:
        print(_box_line(f" BASELINE: {baseline_id}", width))
        print(_box_line(f" Legacy excluidos: {excluded}", width))

    print(_separator(width))


def _print_global_times(rows: list[dict], width: int) -> None:
    total_times = [_duration_from_row(row) for row in rows]
    llm_times = _positive_values(_llm_time_from_row, rows)
    retrieval_times = _positive_values(_retrieval_time_from_row, rows)
    fidelity_times = _positive_values(_fidelity_time_from_row, rows)
    tokens_total = sum(_estimated_tokens_from_row(row) for row in rows)
    cache_hits = sum(_cache_hit_from_row(row) for row in rows)
    total_rows = len(rows)

    print(_box_line("TIEMPOS PROMEDIO", width))
    print(_box_line(f"  Total    : {_format_seconds(mean(total_times) if total_times else 0)}", width))
    print(_box_line(f"  LLM      : {_format_seconds(mean(llm_times) if llm_times else 0)}", width))
    print(_box_line(f"  Retrieval: {_format_seconds(mean(retrieval_times) if retrieval_times else 0)}", width))
    print(_box_line(f"  Fidelity : {_format_seconds(mean(fidelity_times) if fidelity_times else 0)}", width))
    print(_box_line(f"  Tokens estimados (total): {tokens_total}", width))

    cache_pct = round(cache_hits * 100 / total_rows) if total_rows else 0
    print(_box_line(f"  Desde cache: {cache_hits}/{total_rows} ({cache_pct}%)", width))
    print(_separator(width))


def _print_lane_distribution(rows: list[dict], width: int) -> None:
    lane_counts = Counter(_lane_from_row(row) for row in rows)
    total_rows = len(rows)

    print(_box_line("DISTRIBUCION POR CARRIL", width))
    for lane, count in lane_counts.most_common():
        pct = round(count * 100 / total_rows) if total_rows else 0
        bar = _ascii_bar(count, total_rows)
        print(
            _box_line(
                f"  {lane:<24} {count:>3} ({pct:>3}%) {bar}",
                width,
            )
        )
    print(_separator(width))


def _print_top_slowest(rows: list[dict], width: int) -> None:
    print(_box_line("TOP 3 TURNOS MAS LENTOS", width))
    for index, row in enumerate(sorted(rows, key=_duration_from_row, reverse=True)[:3], start=1):
        lane = _lane_from_row(row)
        duration = _format_seconds(_duration_from_row(row))
        ts = _timestamp_from_row(row)
        print(_box_line(f"  {index}. {lane:<20} {duration:<10} {ts}", width))
    print(_separator(width))


def _print_intent_context(rows: list[dict], width: int) -> None:
    intent_groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        intent_groups[_intent_from_row(row)].append(row)

    print(_box_line("CONTEXTO POR TIPO DE INTENCION", width))
    print(_box_line("  INTENT                   TURNOS  AVG DOCS    AVG LLM   AVG RETR", width))

    for intent, group in sorted(intent_groups.items(), key=lambda item: len(item[1]), reverse=True):
        docs: list[int] = []
        llm_times: list[float] = []
        retrieval_times: list[float] = []

        for row in group:
            doc_count = _docs_count_from_row(row)
            if doc_count is not None:
                docs.append(doc_count)

            llm_time = _llm_time_from_row(row)
            if llm_time > 0:
                llm_times.append(llm_time)

            retrieval_time = _retrieval_time_from_row(row)
            if retrieval_time > 0:
                retrieval_times.append(retrieval_time)

        avg_docs = f"{mean(docs):.1f}" if docs else "-"
        avg_llm = _format_seconds(mean(llm_times)) if llm_times else "-"
        avg_retrieval = _format_seconds(mean(retrieval_times)) if retrieval_times else "-"

        print(
            _box_line(
                f"  {intent:<24} {len(group):>5}  {avg_docs:>8}  {avg_llm:>9}  {avg_retrieval:>9}",
                width,
            )
        )
    print(_separator(width))

def _print_cache_status(width: int) -> None:
    stats = _get_cache_stats()

    print(_box_line("ESTADO DE CACHE SEMANTICA", width))
    print(_box_line(f"  Entradas : {stats['entries']}/{stats['max_size']}", width))
    print(_box_line(f"  Hits     : {stats['hits']}", width))
    print(_box_line(f"  Misses   : {stats['misses']}", width))
    print(_box_line(f"  Archivo  : {stats['cache_file']}", width))
    print(_box_line(f"  Existe   : {'si' if stats['file_exists'] else 'no'}", width))
    print(_separator(width))

def _show_table(rows: list[dict],baseline_id: str | None = None,
      excluded: int = 0,  ) -> None:
    width = 66

    _print_header(rows, width, baseline_id, excluded)

    if not rows:
        print(_box_line("No se encontraron metricas en storage/logs/metrics.jsonl", width))
        print(_separator(width))
        return

    _print_global_times(rows, width)
    _print_lane_distribution(rows, width)
    _print_top_slowest(rows, width)
    _print_intent_context(rows, width)
    _print_cache_status(width)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Muestra métricas de Lautaro desde metrics.jsonl."
    )
    parser.add_argument(
        "--baseline",
        help="Filtra por baseline ID o usa 'active' para el baseline activo.",
    )
    parser.add_argument(
        "--all-history",
        action="store_true",
        help="Ignora el filtro y muestra todo el historial.",
    )
    args = parser.parse_args()

    rows = _load_metrics()
    baseline_id = None
    excluded = 0

    if args.baseline and not args.all_history:
        baseline_id, baseline = _resolve_baseline(args.baseline)

        if baseline is None:
            print(f"Baseline no encontrado: {baseline_id or args.baseline}")
            return

        rows, excluded = _filter_by_baseline(rows, baseline_id)

    _show_table(rows, baseline_id, excluded)


if __name__ == "__main__":
    main()