from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule

console = Console()
DEBUG_RETRIEVAL = True


# ──────────────────────────────────────────────
# Bienvenida
# ──────────────────────────────────────────────

def print_welcome() -> None:
    """Muestra el banner de bienvenida al arrancar el chat."""
    console.print(Panel(
        Text.assemble(
            ("Lautaro", "bold cyan"),
            (" — Asistente técnico local\n", "white"),
            ("Escribe tu pregunta o ", "dim"),
            ("'chao'", "bold"),
            (" para salir.", "dim"),
        ),
        border_style="cyan",
        padding=(0, 2),
    ))


# ──────────────────────────────────────────────
# Session Intelligence Briefing (Paso D)
# ──────────────────────────────────────────────

_STATE_ICON = {
    "blocked":    "⛔",
    "momentum":   "🚀",
    "recovering": "⚠️ ",
    "overloaded": "📋",
    "stale":      "🕰️ ",
    "focused":    "🎯",
    "drifting":   "🧭",
}

_STATE_LABEL = {
    "blocked":    "Hay bloqueos activos",
    "momentum":   "Buena racha — sesión anterior exitosa",
    "recovering": "Sesión anterior incompleta — revisar antes de avanzar",
    "overloaded": "Muchas tareas abiertas",
    "stale":      "Hay tareas estancadas",
    "focused":    "Foco claro",
    "drifting":   "Sin foco definido",
}


def _mostrar_briefing_compacto(briefing: dict) -> None:
    """Briefing resumido (<5 líneas) para reaperturas del mismo día.

    Muestra solo lo esencial: estado, foco, conteo de tareas y sugerencia.
    Se activa cuando briefing['es_retomada'] es True.
    La lógica completa sigue intacta en mostrar_briefing() para
    la primera apertura del día.
    """
    state      = briefing.get("session_state", "drifting")
    icon       = _STATE_ICON.get(state, "💡")
    foco       = briefing.get("foco", "sin foco")
    n_open     = len(briefing["tasks"]["all_open"])
    n_stale    = len(briefing["tasks"]["stale"])
    suggestion = briefing.get("suggestion", "")

    console.print()
    console.print(Rule(style="dim"))

    tareas_str = f"{n_open} tareas"
    if n_stale:
        tareas_str += f" ([yellow]{n_stale} estancadas[/yellow])"

    console.print(
        f"  {icon} [bold]Retomando[/bold] — Foco: [bold cyan]{foco}[/bold cyan]  "
        f"·  {tareas_str}"
    )
    if suggestion:
        console.print(f"  [cyan]→ {suggestion}[/cyan]")

    console.print(Rule(style="dim"))
    console.print()


def mostrar_briefing(briefing: dict) -> None:
    """Muestra el resumen de arranque de sesión con Session Intelligence.

    Ramifica entre dos modos según briefing['es_retomada']:
      - False (primera apertura del día): briefing completo con todas las secciones.
      - True  (segunda+ apertura del día): modo compacto de <5 líneas.

    El modo compacto delega en _mostrar_briefing_compacto().
    El modo completo ejecuta la lógica original intacta.
    """
    if briefing.get("es_retomada", False):
        _mostrar_briefing_compacto(briefing)
        return

    # ── Modo completo (primera apertura del día) ──────────────────
    state   = briefing.get("session_state", "drifting")
    icon    = _STATE_ICON.get(state, "💡")
    label   = _STATE_LABEL.get(state, state)
    all_open = briefing["tasks"]["all_open"]
    stale    = briefing["tasks"]["stale"]
    ep       = briefing.get("last_episode")

    console.print()
    console.print(Rule(style="dim"))

    # ── Foco y objetivo ──────────────────────────────────────────
    foco = briefing.get("foco", "")
    goal = briefing.get("session_goal", "")
    if foco:
        console.print(f"  [bold]🎯 Foco:[/bold] {foco}")
    if goal:
        console.print(f"  [bold cyan]💡 Objetivo de hoy:[/bold cyan] {goal}")

    # ── Tareas ────────────────────────────────────────────────────
    n_open  = len(all_open)
    n_stale = len(stale)
    if n_open == 0:
        console.print("  [dim]📋 Sin tareas abiertas.[/dim]")
    else:
        stale_suffix = f" ([yellow]{n_stale} estancadas[/yellow])" if n_stale else ""
        console.print(f"  [bold]📋 Tareas abiertas:[/bold] {n_open}{stale_suffix}")
        sorted_tasks = sorted(
            all_open,
            key=lambda t: ("high" not in t.get("priority", ""), t.get("created_at", "")),
        )[:3]
        for t in sorted_tasks:
            pri = t.get("priority", "medium")
            pri_color = "red" if pri == "high" else "yellow" if pri == "medium" else "dim"
            console.print(
                f"    [dim]·[/dim] [{pri_color}]{pri}[/{pri_color}] {t.get('title', '')}"
                + (" [yellow][estancada][/yellow]" if t in stale else "")
            )

    # ── Último completado ─────────────────────────────────────────
    last_done = briefing.get("last_completed", "")
    if last_done:
        console.print(f"  [dim]✅ Último completado:[/dim] [dim]{last_done}[/dim]")

    # ── Episodio anterior ─────────────────────────────────────────
    if ep:
        ep_date    = ep.get("date", "")
        ep_turns   = ep.get("turns", 0)
        ep_exitoso = ep.get("exitoso", "unmarked")
        ep_carril  = ep.get("carril_dominante", "")
        ep_summary = ep.get("summary", "")

        try:
            delta = (datetime.now().date() - datetime.fromisoformat(ep_date).date()).days
            if delta == 0:
                cuando = "hoy"
            elif delta == 1:
                cuando = "ayer"
            else:
                cuando = f"hace {delta} días"
        except (ValueError, TypeError):
            cuando = ep_date

        resultado_icon = (
            "✅" if ep_exitoso in (True, "true")
            else "⚠️ " if ep_exitoso in (False, "false")
            else "📅"
        )

        # Tag (retomada) si es_retomada pero estamos en modo completo
        # (edge case: es_retomada=True pero se fuerza modo completo externamente)
        retomada_tag = " [cyan](retomada)[/cyan]" if briefing.get("es_retomada") else ""
        carril_str = f" · carril dominante: {ep_carril}" if ep_carril else ""
        console.print(
            f"  [dim]{resultado_icon} Última sesión:[/dim] "
            f"[dim]{cuando}{retomada_tag} · {ep_turns} turnos{carril_str}[/dim]"
        )
        if ep_summary:
            resumen_corto = ep_summary[:120] + "…" if len(ep_summary) > 120 else ep_summary
            console.print(f"    [dim italic]{resumen_corto}[/dim italic]")
    else:
        console.print("  [dim]📅 Primera sesión — sin episodios anteriores.[/dim]")

    # ── Diagnóstico + sugerencia ──────────────────────────────────
    console.print()
    console.print(f"  {icon} [bold]{label}[/bold]")
    suggestion = briefing.get("suggestion", "")
    if suggestion:
        console.print(f"  [cyan]→ {suggestion}[/cyan]")

    console.print(Rule(style="dim"))
    console.print()


# ──────────────────────────────────────────────
# Formateo de respuesta
# ──────────────────────────────────────────────

def format_answer(answer: str) -> str:
    """Devuelve la respuesta con prefijo del asistente."""
    return f"\nLautaro: {answer}\n"


# ──────────────────────────────────────────────
# Fuentes
# ──────────────────────────────────────────────

def print_sources(docs) -> None:
    if not docs:
        return

    console.print("[dim]Basado en:[/dim]")
    seen = set()
    idx = 1

    for d in docs:
        src = d.metadata.get("source", "desconocido")
        name = Path(src).name if src != "desconocido" else src
        doc_type = d.metadata.get("doc_type", "sin_tipo")
        section = d.metadata.get("section", "sin_seccion")

        key = (src, doc_type, section)
        if key not in seen:
            console.print(f"  {idx}. {name} | {doc_type} | {section}")
            seen.add(key)
            idx += 1


# ──────────────────────────────────────────────
# Debug retrieval (solo en desarrollo)
# ──────────────────────────────────────────────

def print_debug_retrieval(question: str, docs) -> None:
    if not DEBUG_RETRIEVAL:
        return

    console.print("[blue]DEBUG RETRIEVAL:[/blue]")
    console.print(f"[blue]Pregunta:[/blue] {question}")

    if not docs:
        console.print("[blue]No se recuperaron documentos.[/blue]\n")
        return

    for i, d in enumerate(docs, 1):
        src = d.metadata.get("source", "desconocido")
        name = Path(src).name if src != "desconocido" else src
        doc_type = d.metadata.get("doc_type", "sin_tipo")
        section = d.metadata.get("section", "sin_seccion")
        preview = d.page_content[:220].replace("\n", " ")

        console.print(f"[blue]{i}. {name} | {doc_type} | {section}[/blue]")
        console.print(f"[dim]{preview}...[/dim]")

    console.print()
