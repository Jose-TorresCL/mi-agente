"""
show_metrics.py — Visor CLI de métricas de sesión (Fase 7B/7D / R2).

Lee storage/metrics.jsonl y muestra un resumen en tabla ASCII.
Incluye sección de estado de caché semántica (7D) y tabla de
contexto por tipo de intención (R2).

Uso:
    python show_metrics.py                 # últimas 50 entradas
    python show_metrics.py --last 20       # últimas 20
    python show_metrics.py --route rag     # filtrar por carril
    python show_metrics.py --json          # salida JSON raw
    python show_metrics.py --last 100 --route memory
    python show_metrics.py --no-cache      # omitir sección de caché
    python show_metrics.py --no-intent     # omitir sección de intención

No requiere dependencias externas para la tabla — solo stdlib.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_METRICS_FILE = Path("storage/metrics.jsonl")
_DEFAULT_LAST = 50


def _load_entries(
    last: int | None = None,
    route_filter: str | None = None,
) -> list[dict[str, Any]]:
    if not _METRICS_FILE.exists():
        return []
    entries: list[dict[str, Any]] = []
    with _METRICS_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if route_filter and entry.get("route") != route_filter:
                    continue
                entries.append(entry)
            except json.JSONDecodeError:
                continue
    if last is not None:
        entries = entries[-last:]
    return entries


def _fmt_ms(ms: int | float) -> str:
    if ms >= 60_000:
        return f"{ms/60000:.1f} min"
    if ms >= 1_000:
        return f"{ms/1000:.1f} s"
    return f"{int(ms)} ms"


def _fmt_hours(h: float) -> str:
    if h < 1:
        return f"{int(h*60)} min"
    return f"{h:.1f} h"


def _get_cache_stats() -> dict | None:
    """Obtiene stats de caché sin romper si hay error de import o I/O."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        from app.semantic_cache import cache_stats
        return cache_stats()
    except Exception:
        return None


def _section_intent(entries: list[dict[str, Any]], W: int, row, sep) -> None:
    """Sección CONTEXTO POR INTENT: avg_docs, avg_llm_ms y conteo."""
    # agrupar por intent_type (entradas viejas sin campo → 'unknown')
    groups: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        intent = e.get("intent_type") or "unknown"
        groups[intent].append(e)

    sep()
    row("CONTEXTO POR TIPO DE INTENCIÓN (R2)")
    # cabecera
    row(f"  {'INTENT':<28} {'TURNOS':>6}  {'AVG DOCS':>8}  {'AVG LLM':>9}")
    row("  " + "-" * 56)
    for intent, items in sorted(groups.items(), key=lambda x: -len(x[1])):
        count = len(items)
        docs_vals  = [e.get("num_docs", 0) for e in items if e.get("num_docs", 0) > 0]
        llm_vals   = [e.get("llm_ms",  0) for e in items if e.get("llm_ms",  0) > 0]
        avg_docs   = sum(docs_vals) / len(docs_vals) if docs_vals else 0
        avg_llm    = sum(llm_vals)  / len(llm_vals)  if llm_vals  else 0
        docs_str   = f"{avg_docs:.1f}" if avg_docs else "  -"
        llm_str    = _fmt_ms(avg_llm) if avg_llm else "  -"
        row(f"  {intent:<28} {count:>6}  {docs_str:>8}  {llm_str:>9}")


def _show_table(
    entries: list[dict[str, Any]],
    show_cache: bool = True,
    show_intent: bool = True,
) -> None:
    if not entries:
        print("Sin entradas para mostrar.")
        return

    total         = len(entries)
    cached_count  = sum(1 for e in entries if e.get("cached"))
    llm_ms_list   = [e.get("llm_ms", 0)       for e in entries if e.get("llm_ms", 0) > 0]
    ret_ms_list   = [e.get("retrieval_ms", 0)  for e in entries if e.get("retrieval_ms", 0) > 0]
    total_ms_list = [e.get("total_ms", 0)      for e in entries]

    avg_llm   = sum(llm_ms_list)   / len(llm_ms_list)   if llm_ms_list   else 0
    avg_ret   = sum(ret_ms_list)   / len(ret_ms_list)   if ret_ms_list   else 0
    avg_total = sum(total_ms_list) / len(total_ms_list) if total_ms_list else 0
    pct_cached   = (cached_count / total * 100) if total else 0
    total_tokens = sum(e.get("tokens_est", 0) for e in entries)

    by_route: dict[str, int] = defaultdict(int)
    for e in entries:
        by_route[e.get("route", "unknown")] += 1

    slowest = sorted(entries, key=lambda e: e.get("total_ms", 0), reverse=True)[:3]

    W = 62  # ancho interior de la caja

    def row(text: str) -> None:
        print(f"║  {text:<{W}}║")

    def sep() -> None:
        print("╠" + "═" * (W + 2) + "╣")

    print()
    print("╔" + "═" * (W + 2) + "╗")
    row(f"MÉTRICAS DE SESIÓN — {total} turnos analizados")
    sep()

    row("TIEMPOS PROMEDIO")
    row(f"  Total    : {_fmt_ms(avg_total)}")
    row(f"  LLM      : {_fmt_ms(avg_llm)}")
    row(f"  Retrieval: {_fmt_ms(avg_ret)}")
    row(f"  Tokens estimados (total): {total_tokens}")
    row(f"  Desde caché: {cached_count}/{total} ({pct_cached:.0f}%)")
    sep()

    row("DISTRIBUCIÓN POR CARRIL")
    for ruta, cnt in sorted(by_route.items(), key=lambda x: -x[1]):
        pct = cnt / total * 100
        bar = "█" * int(pct / 5)
        row(f"  {ruta:<26} {cnt:>3}  ({pct:4.0f}%)  {bar}")
    sep()

    row("TOP 3 TURNOS MÁS LENTOS")
    for i, e in enumerate(slowest, 1):
        ts = e.get("timestamp", "")[:19].replace("T", " ")
        row(f"  {i}. {e.get('route','?'):<22} {_fmt_ms(e.get('total_ms',0)):<10} {ts}")

    # ── Sección intent (R2) ──────────────────────────────────────────────────
    if show_intent:
        _section_intent(entries, W, row, sep)

    # ── Sección caché (7D) ───────────────────────────────────────────────────
    if show_cache:
        stats = _get_cache_stats()
        if stats is not None:
            sep()
            row("ESTADO DE CACHÉ SEMÁNTICA")
            row(f"  Entradas : {stats['entries']}/{stats['max_size']}  "
                f"(TTL: {stats['ttl_hours']}h | umbral: {stats['threshold']})")
            if stats["entries"] > 0:
                row(f"  Edad prom: {_fmt_hours(stats['avg_age_hours'])}  "
                    f"| más vieja: {_fmt_hours(stats['oldest_hours'])}  "
                    f"| más nueva: {_fmt_hours(stats['newest_hours'])}")
                if stats["near_expiry_count"] > 0:
                    row(f"  ⚠  {stats['near_expiry_count']} entrada(s) expirarán en < 4h")
            else:
                row("  Caché vacía — se llenará en los próximos turnos RAG")

    print("╚" + "═" * (W + 2) + "╝")
    print()


def _show_json(entries: list[dict[str, Any]]) -> None:
    print(json.dumps(entries, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visor de métricas de sesión — storage/metrics.jsonl"
    )
    parser.add_argument("--last",  type=int, default=_DEFAULT_LAST,
                        metavar="N", help=f"Últimas N entradas (default: {_DEFAULT_LAST})")
    parser.add_argument("--route", type=str, default=None,
                        metavar="CARRIL", help="Filtrar por carril")
    parser.add_argument("--json",     action="store_true", help="Salida JSON raw")
    parser.add_argument("--no-cache",  action="store_true", help="Omitir sección de caché")
    parser.add_argument("--no-intent", action="store_true",
                        help="Omitir sección de contexto por intención")
    args = parser.parse_args()

    if not _METRICS_FILE.exists():
        print(f"[show_metrics] No existe {_METRICS_FILE}")
        print("Ejecuta el agente al menos un turno para generar métricas.")
        sys.exit(0)

    entries = _load_entries(last=args.last, route_filter=args.route)

    if not entries:
        filtro = f" con route='{args.route}'" if args.route else ""
        print(f"[show_metrics] Sin entradas{filtro} en los últimos {args.last} registros.")
        sys.exit(0)

    if args.json:
        _show_json(entries)
    else:
        _show_table(
            entries,
            show_cache=not args.no_cache,
            show_intent=not args.no_intent,
        )


if __name__ == "__main__":
    main()
