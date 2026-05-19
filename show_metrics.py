"""
show_metrics.py — Visor CLI de métricas de sesión (Fase 7B).

Lee storage/metrics.jsonl y muestra un resumen en tabla ASCII.

Uso:
    python show_metrics.py                 # últimas 50 entradas
    python show_metrics.py --last 20       # últimas 20
    python show_metrics.py --route rag     # filtrar por carril
    python show_metrics.py --json          # salida JSON raw
    python show_metrics.py --last 100 --route memory

No requiere dependencias externas — solo stdlib.
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


def _load_entries(last: int | None = None, route_filter: str | None = None) -> list[dict[str, Any]]:
    """Carga entradas del JSONL, aplica filtros y devuelve lista."""
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
    """Formatea milisegundos a cadena legible."""
    if ms >= 60_000:
        return f"{ms/60000:.1f} min"
    if ms >= 1_000:
        return f"{ms/1000:.1f} s"
    return f"{int(ms)} ms"


def _show_table(entries: list[dict[str, Any]]) -> None:
    """Imprime resumen en tabla ASCII."""
    if not entries:
        print("Sin entradas para mostrar.")
        return

    total = len(entries)
    cached_count = sum(1 for e in entries if e.get("cached"))
    llm_ms_list = [e.get("llm_ms", 0) for e in entries if e.get("llm_ms", 0) > 0]
    ret_ms_list = [e.get("retrieval_ms", 0) for e in entries if e.get("retrieval_ms", 0) > 0]
    total_ms_list = [e.get("total_ms", 0) for e in entries]

    avg_llm = sum(llm_ms_list) / len(llm_ms_list) if llm_ms_list else 0
    avg_ret = sum(ret_ms_list) / len(ret_ms_list) if ret_ms_list else 0
    avg_total = sum(total_ms_list) / len(total_ms_list) if total_ms_list else 0
    pct_cached = (cached_count / total * 100) if total else 0

    # Distribución por carril
    by_route: dict[str, int] = defaultdict(int)
    for e in entries:
        by_route[e.get("route", "unknown")] += 1

    # Top 3 más lentos (por total_ms)
    slowest = sorted(entries, key=lambda e: e.get("total_ms", 0), reverse=True)[:3]

    # Tokens estimados totales
    total_tokens = sum(e.get("tokens_est", 0) for e in entries)

    # ── Cabecera ─────────────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print(f"║  MÉTRICAS DE SESIÓN — {total} turnos analizados{' ' * (23 - len(str(total)))}║")
    print("╠══════════════════════════════════════════════════════════════╣")

    # ── Tiempos globales ─────────────────────────────────────────────────────
    print("║  TIEMPOS PROMEDIO                                            ║")
    print(f"║    Total   : {_fmt_ms(avg_total):<49}║")
    print(f"║    LLM     : {_fmt_ms(avg_llm):<49}║")
    print(f"║    Retrieval: {_fmt_ms(avg_ret):<48}║")
    print(f"║    Tokens estimados (total): {total_tokens:<33}║")
    print(f"║    Respuestas desde caché  : {cached_count}/{total} ({pct_cached:.0f}%){' ' * (27 - len(str(cached_count)) - len(str(total)))  }║")
    print("╠══════════════════════════════════════════════════════════════╣")

    # ── Distribución por carril ──────────────────────────────────────────────
    print("║  DISTRIBUCIÓN POR CARRIL                                     ║")
    for ruta, cnt in sorted(by_route.items(), key=lambda x: -x[1]):
        pct = cnt / total * 100
        bar = "█" * int(pct / 5)  # 1 bloque = 5%
        line = f"    {ruta:<25} {cnt:>3}  ({pct:4.0f}%)  {bar}"
        print(f"║  {line:<60}║")
    print("╠══════════════════════════════════════════════════════════════╣")

    # ── Top 3 más lentos ─────────────────────────────────────────────────────
    print("║  TOP 3 TURNOS MÁS LENTOS                                     ║")
    for i, e in enumerate(slowest, 1):
        ts = e.get("timestamp", "")[:19].replace("T", " ")
        line = f"    {i}. {e.get('route','?'):<20} {_fmt_ms(e.get('total_ms',0)):<10} {ts}"
        print(f"║  {line:<60}║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()


def _show_json(entries: list[dict[str, Any]]) -> None:
    """Imprime entradas como JSON array."""
    print(json.dumps(entries, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visor de métricas de sesión — storage/metrics.jsonl"
    )
    parser.add_argument(
        "--last", type=int, default=_DEFAULT_LAST,
        metavar="N", help=f"Mostrar últimas N entradas (default: {_DEFAULT_LAST})"
    )
    parser.add_argument(
        "--route", type=str, default=None,
        metavar="CARRIL", help="Filtrar por carril (ej: rag, memory, tool_list_files)"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Salida en JSON raw en vez de tabla ASCII"
    )
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
        _show_table(entries)


if __name__ == "__main__":
    main()
