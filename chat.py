"""
Asistente local Lautaro:
- Usa Ollama (por defecto llama3.2:latest) como LLM.
- Recupera contexto de tus docs con Chroma (RAG).
- Responde desde memoria estructurada cuando corresponde.
- Guarda memoria de conversación en storage/memory.json.

Ejecutar:
    python chat.py

Salir:
    escribir 'salir', 'exit' o 'quit'.

Comandos especiales:
    !reset  -> borra la memoria de conversación (storage/memory.json)
    !estado -> muestra foco actual, siguiente paso, tareas pendientes
               y estadísticas del router en la sesión actual
"""

from pathlib import Path

from rich.markdown import Markdown

from app.chat_core import (
    CHROMA_DIR,
    MEMORY_FILE,
    ensure_storage,
    load_vector_store,
    build_memory,
    handle_query,
)
from app.chat_ui import console, print_sources


def mostrar_contexto_inicial():
    """Muestra automáticamente el estado del proyecto al arrancar."""
    from app.memory_store import load_work_state, load_tasks

    ws = load_work_state()
    tasks_data = load_tasks()
    pending = [
        t for t in tasks_data.get("tasks", [])
        if t.get("status") not in ("completed", "done")
    ]

    foco   = ws.get("current_focus", "sin foco definido")
    next_s = ws.get("next_step", "sin siguiente paso")
    last_s = ws.get("last_completed_step", "—")

    console.print("\n[bold yellow]📌 Retomando donde lo dejaste:[/bold yellow]")
    console.print(f"   [cyan]Foco:[/cyan]      {foco}")
    console.print(f"   [cyan]Siguiente:[/cyan] {next_s}")
    console.print(f"   [dim]Último:    {last_s}[/dim]")

    if pending:
        console.print(
            f"   [yellow]Tareas pendientes ({len(pending)}):[/yellow] "
            + ", ".join(t.get("title", t.get("id", "?")) for t in pending)
        )
    else:
        console.print("   [dim]Sin tareas pendientes.[/dim]")

    console.print("")


def cmd_estado():
    """Imprime un resumen completo del estado actual del proyecto."""
    from app.memory_store import load_work_state, load_tasks
    from app.router import SESSION_STATS

    ws = load_work_state()
    tasks_data = load_tasks()
    pending = [
        t for t in tasks_data.get("tasks", [])
        if t.get("status") not in ("completed", "done")
    ]

    console.print("\n[bold]── Estado actual ────────────────────────────[/bold]")
    console.print(f"  [cyan]Foco:[/cyan]           {ws.get('current_focus', '—')}")
    console.print(f"  [cyan]Siguiente paso:[/cyan] {ws.get('next_step', '—')}")
    console.print(f"  [cyan]Último paso:[/cyan]    {ws.get('last_completed_step', '—')}")
    blockers = ws.get("current_blockers", [])
    if blockers:
        console.print(f"  [red]Bloqueos:[/red]       {', '.join(blockers)}")

    console.print(f"\n  [yellow]Tareas pendientes ({len(pending)}):[/yellow]")
    if pending:
        for t in pending:
            console.print(
                f"    [[bold]{t['id']}[/bold]] {t['title']} "
                f"([dim]{t.get('priority', 'media')}[/dim])"
            )
    else:
        console.print("    Sin tareas pendientes.")

    # ── Estadísticas del router ──────────────────────────────────
    total = SESSION_STATS["total"]
    if total > 0:
        kw_pct  = SESSION_STATS["kw"]  * 100 // total
        emb_pct = SESSION_STATS["emb"] * 100 // total
        llm_pct = SESSION_STATS["llm"] * 100 // total
        console.print(f"\n  [bold]Router esta sesión ({total} consultas):[/bold]")
        console.print(f"    [green]Capa 1 keywords :[/green]   {SESSION_STATS['kw']:>3} consultas  ({kw_pct}%)  0ms")
        console.print(f"    [blue]Capa 2 embeddings:[/blue]  {SESSION_STATS['emb']:>3} consultas  ({emb_pct}%)  ~50ms")
        console.print(f"    [red]Capa 3 LLM       :[/red]   {SESSION_STATS['llm']:>3} consultas  ({llm_pct}%)  ~3-8s")

        if llm_pct >= 30:
            console.print(
                "\n  [bold red]⚠ El LLM se usa mucho (≥30%).[/bold red] "
                "Considera añadir más ejemplos a data/intent_examples.json "
                "y reejecutar build_intent_index.py"
            )
    else:
        console.print("\n  [dim]Router: sin consultas en esta sesión aún.[/dim]")

    console.print("[bold]──────────────────────────────────────[/bold]\n")


def main():
    ensure_storage()

    if not Path(CHROMA_DIR).exists():
        raise FileNotFoundError(
            f"No encuentro el vector store en {CHROMA_DIR}. "
            "Primero ejecuta 'python indexacion.py'."
        )

    vectordb = load_vector_store()
    # chat_history es ahora una lista simple de HumanMessage / AIMessage
    chat_history = build_memory()

    console.print("[bold green]Lautaro está iniciado[/bold green]")
    console.print("Escribe tu pregunta. 'salir', 'exit' o 'quit' para terminar.")
    console.print(
        "Comandos: [yellow]!reset[/yellow] (borra memoria) "
        "[yellow]!estado[/yellow] (resumen del proyecto + stats del router)\n"
    )

    mostrar_contexto_inicial()

    while True:
        user_input = console.input("[bold cyan]Tú:[/bold cyan] ").strip()

        if user_input.lower() in {"salir", "exit", "quit"}:
            console.print("[yellow]Hasta luego 👋[/yellow]")
            break

        if user_input.lower() == "!reset":
            if MEMORY_FILE.exists():
                MEMORY_FILE.unlink()
            chat_history.clear()
            console.print("[red]Memoria de conversación borrada.[/red]")
            continue

        if user_input.lower() == "!estado":
            cmd_estado()
            continue

        if not user_input:
            continue

        console.print("[magenta]Pensando...[/magenta]")

        answer, sources = handle_query(user_input, vectordb, chat_history)

        console.print(Markdown(f"**Lautaro:** {answer}"))
        print_sources(sources)


if __name__ == "__main__":
    main()
