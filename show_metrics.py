"""
show_metrics.py — Visor CLI de métricas de sesión (Fase 7B/7D / R2 / R2-B).

Lee storage/metrics.jsonl y muestra un resumen en tabla ASCII.
Incluye sección de estado de caché semántica (7D), tabla de
contexto por tipo de intención (R2) y análisis de drift entre
ventanas de tiempo (R2-B).

Uso:
    python show_metrics.py                 # últimas 50 entradas
    python show_metrics.py --last 20       # últimas 20
    python show_metrics.py --route rag     # filtrar por carril
    python show_metrics.py --json          # salida JSON raw
    python show_metrics.py --last 100 --route memory
    python show_metrics.py --no-cache      # omitir sección de caché
    python show_metrics.py --no-intent     # omitir sección de intención
    python show_metrics.py --drift         # comparar esta semana vs anterior
    python show_metrics.py --drift --window 3  # ventana de 3 días

No requiere dependencias externas para la tabla — solo stdlib.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
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


def _load_all_entries() -> list[dict[str, Any]]:
    """Carga TODAS las entradas sin límite — para análisis de drift."""
    return _load_entries(last=None, route_filter=None)


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
    groups: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        intent = e.get("intent_type") or "unknown"
        groups[intent].append(e)

    sep()
    row("CONTEXTO POR TIPO DE INTENCIÓN (R2)")
    row(f"  {'INTENT':<28} {'TURNOS':>6}  {'AVG DOCS':>8}  {'AVG LLM':>9}")
    row("  " + "-" * 56)
    for intent, items in sorted(groups.items(), key=lambda x: -len(x[1])):
        count = len(items)
        docs_vals = [e.get("num_docs", 0) for e in items if e.get("num_docs", 0) > 0]
        llm_vals  = [e.get("llm_ms",  0) for e in items if e.get("llm_ms",  0) > 0]
        avg_docs  = sum(docs_vals) / len(docs_vals) if docs_vals else 0
        avg_llm   = sum(llm_vals)  / len(llm_vals)  if llm_vals  else 0
        docs_str  = f"{avg_docs:.1f}" if avg_docs else "  -"
        llm_str   = _fmt_ms(avg_llm) if avg_llm else "  -"
        row(f"  {intent:<28} {count:>6}  {docs_str:>8}  {llm_str:>9}")


# ─────────────────────────────────────────────
# R2-B: Análisis de drift entre ventanas
# ─────────────────────────────────────────────

def _parse_ts(entry: dict) -> datetime | None:
    """Parsea el campo timestamp de una entrada. Retorna None si falla."""
    ts_str = entry.get("timestamp", "")
    if not ts_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(ts_str[:19], fmt[:len(fmt)])
        except ValueError:
            continue
    return None


def _window_stats(entries: list[dict]) -> dict:
    """Calcula estadísticas clave de un grupo de entradas."""
    if not entries:
        return {}
    total = len(entries)
    cached = sum(1 for e in entries if e.get("cached"))
    llm_vals   = [e.get("llm_ms", 0)   for e in entries if e.get("llm_ms", 0) > 0]
    total_vals = [e.get("total_ms", 0) for e in entries if e.get("total_ms", 0) > 0]
    fid_vals   = [e["fidelity_score"] for e in entries if e.get("fidelity_score") is not None]

    by_route: dict[str, int] = defaultdict(int)
    for e in entries:
        by_route[e.get("route", "unknown")] += 1
    top_route = max(by_route, key=by_route.__getitem__) if by_route else "—"

    return {
        "turnos":       total,
        "cache_pct":    (cached / total * 100) if total else 0,
        "avg_llm_ms":   sum(llm_vals)   / len(llm_vals)   if llm_vals   else 0,
        "avg_total_ms": sum(total_vals) / len(total_vals) if total_vals else 0,
        "avg_fidelity": sum(fid_vals)   / len(fid_vals)   if fid_vals   else None,
        "top_route":    top_route,
        "route_dist":   dict(by_route),
    }


def _delta_str(val_now: float, val_prev: float, higher_is_better: bool = True) -> str:
    """Formatea la diferencia entre dos períodos con flecha de tendencia."""
    if val_prev == 0:
        return "  —"
    delta = val_now - val_prev
    pct   = (delta / val_prev) * 100
    arrow = "▲" if delta > 0 else "▼"
    good  = (delta > 0) == higher_is_better
    sign  = "+" if delta >= 0 else ""
    emoji = "✓" if good else "⚠"
    return f"{sign}{pct:.1f}% {arrow} {emoji}"


def _section_drift(window_days: int, W: int, row, sep) -> None:
    """
    R2-B: Compara distribución de métricas entre ventana actual y anterior.

    ventana_actual   = últimos window_days días
    ventana_anterior = window_days días previos a eso

    Detecta si el agente responde distinto a lo largo del tiempo:
    latencia, hit rate caché, distribución de carriles, fidelity score.
    """
    all_entries = _load_all_entries()
    if not all_entries:
        sep()
        row("ANÁLISIS DE DRIFT (R2-B) — sin datos suficientes")
        return

    now         = datetime.now()
    cutoff_now  = now - timedelta(days=window_days)
    cutoff_prev = now - timedelta(days=window_days * 2)

    window_now:  list[dict] = []
    window_prev: list[dict] = []

    for e in all_entries:
        ts = _parse_ts(e)
        if ts is None:
            continue
        if ts >= cutoff_now:
            window_now.append(e)
        elif ts >= cutoff_prev:
            window_prev.append(e)

    sep()
    row(f"ANÁLISIS DE DRIFT — {window_days}d actual vs {window_days}d anterior (R2-B)")

    if not window_now and not window_prev:
        row(f"  Sin entradas con timestamp en los últimos {window_days * 2} días.")
        row("  Asegúrate de que metrics.jsonl tenga campo 'timestamp'.")
        return

    stats_now  = _window_stats(window_now)
    stats_prev = _window_stats(window_prev)

    row(f"  {'MÉTRICA':<28} {'ACTUAL':>12}  {'ANTERIOR':>12}  {'CAMBIO':>14}")
    row("  " + "-" * 68)

    # Turnos
    row(f"  {'Turnos':<28} {stats_now.get('turnos', 0):>12}  "
        f"{stats_prev.get('turnos', 0):>12}  {'—':>14}")

    # Latencia total promedio (menor es mejor)
    t_now  = stats_now.get("avg_total_ms", 0)
    t_prev = stats_prev.get("avg_total_ms", 0)
    row(f"  {'Latencia promedio':<28} {_fmt_ms(t_now):>12}  "
        f"{_fmt_ms(t_prev):>12}  "
        f"{_delta_str(t_now, t_prev, higher_is_better=False):>14}")

    # LLM ms (menor es mejor)
    l_now  = stats_now.get("avg_llm_ms", 0)
    l_prev = stats_prev.get("avg_llm_ms", 0)
    row(f"  {'LLM promedio':<28} {_fmt_ms(l_now):>12}  "
        f"{_fmt_ms(l_prev):>12}  "
        f"{_delta_str(l_now, l_prev, higher_is_better=False):>14}")

    # Cache hit rate (mayor es mejor)
    c_now  = stats_now.get("cache_pct", 0)
    c_prev = stats_prev.get("cache_pct", 0)
    row(f"  {'Cache hit rate':<28} {c_now:>11.1f}%  "
        f"{c_prev:>11.1f}%  "
        f"{_delta_str(c_now, c_prev, higher_is_better=True):>14}")

    # Fidelity score promedio (mayor es mejor)
    f_now  = stats_now.get("avg_fidelity")
    f_prev = stats_prev.get("avg_fidelity")
    f_now_str  = f"{f_now:.3f}"  if f_now  is not None else "  —"
    f_prev_str = f"{f_prev:.3f}" if f_prev is not None else "  —"
    drift_fid  = (_delta_str(f_now, f_prev, higher_is_better=True)
                  if f_now is not None and f_prev is not None
                  else "  sin datos")
    row(f"  {'Fidelity score':<28} {f_now_str:>12}  {f_prev_str:>12}  {drift_fid:>14}")

    # Carril dominante
    tr_now  = stats_now.get("top_route", "—")
    tr_prev = stats_prev.get("top_route", "—")
    changed = "⚠ cambió" if tr_now != tr_prev else "✓ igual"
    row(f"  {'Carril dominante':<28} {tr_now:>12}  {tr_prev:>12}  {changed:>14}")

    # Cambios notables en distribución de carriles (≥5%)
    routes_now  = stats_now.get("route_dist", {})
    routes_prev = stats_prev.get("route_dist", {})
    all_routes  = set(routes_now) | set(routes_prev)
    total_now   = stats_now.get("turnos", 1) or 1
    total_prev  = stats_prev.get("turnos", 1) or 1

    notable = []
    for r in sorted(all_routes):
        pct_n = (routes_now.get(r, 0)  / total_now)  * 100
        pct_p = (routes_prev.get(r, 0) / total_prev) * 100
        diff  = pct_n - pct_p
        if abs(diff) >= 5:
            sign = "+" if diff >= 0 else ""
            notable.append((r, pct_n, pct_p, diff, sign))

    if notable:
        row("  ")
        row("  Cambios notables en distribución de carriles (≥5%):")
        for r, pct_n, pct_p, diff, sign in notable:
            row(f"    {r:<26} {pct_n:5.1f}%  →  ant: {pct_p:5.1f}%  ({sign}{diff:.1f}%)")

    # Alertas automáticas de drift
    alerts: list[str] = []
    if t_prev > 0 and t_now > t_prev * 1.15:
        alerts.append("Latencia subió >15% — revisar Ollama o tamaño de contexto")
    if f_prev is not None and f_now is not None and f_now < f_prev * 0.85:
        alerts.append("Fidelity bajó >15% — revisar calidad de chunks o umbral RAG")
    if c_prev > 10 and c_now < c_prev * 0.7:
        alerts.append("Cache hit rate cayó >30% — preguntas más variadas o caché muy pequeña")

    if alerts:
        row("  ")
        row("  ⚠  ALERTAS DE DRIFT:")
        for a in alerts:
            row(f"    • {a}")
    else:
        row("  ")
        row("  ✓  Sin drift significativo detectado en esta ventana.")


# ─────────────────────────────────────────────
# Render principal
# ─────────────────────────────────────────────

def _show_table(
    entries: list[dict[str, Any]],
    show_cache:   bool = True,
    show_intent:  bool = True,
    show_drift:   bool = False,
    drift_window: int  = 7,
) -> None:
    if not entries:
        print("Sin entradas para mostrar.")
        return

    total         = len(entries)
    cached_count  = sum(1 for e in entries if e.get("cached"))
    llm_ms_list   = [e.get("llm_ms", 0)      for e in entries if e.get("llm_ms", 0) > 0]
    ret_ms_list   = [e.get("retrieval_ms", 0) for e in entries if e.get("retrieval_ms", 0) > 0]
    total_ms_list = [e.get("total_ms", 0)     for e in entries]

    avg_llm   = sum(llm_ms_list)   / len(llm_ms_list)   if llm_ms_list   else 0
    avg_ret   = sum(ret_ms_list)   / len(ret_ms_list)   if ret_ms_list   else 0
    avg_total = sum(total_ms_list) / len(total_ms_list) if total_ms_list else 0
    pct_cached   = (cached_count / total * 100) if total else 0
    total_tokens = sum(e.get("tokens_est", 0) for e in entries)

    by_route: dict[str, int] = defaultdict(int)
    for e in entries:
        by_route[e.get("route", "unknown")] += 1

    slowest = sorted(entries, key=lambda e: e.get("total_ms", 0), reverse=True)[:3]

    W = 62

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

    if show_intent:
        _section_intent(entries, W, row, sep)

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

    if show_drift:
        _section_drift(drift_window, W, row, sep)

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
    parser.add_argument("--json",      action="store_true", help="Salida JSON raw")
    parser.add_argument("--no-cache",  action="store_true", help="Omitir sección de caché")
    parser.add_argument("--no-intent", action="store_true",
                        help="Omitir sección de contexto por intención")
    parser.add_argument("--drift",     action="store_true",
                        help="(R2-B) Comparar ventana actual vs ventana anterior")
    parser.add_argument("--window",    type=int, default=7,
                        metavar="DÍAS",
                        help="Tamaño de ventana en días para --drift (default: 7)")
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
            show_drift=args.drift,
            drift_window=args.window,
        )


if __name__ == "__main__":
    main()
