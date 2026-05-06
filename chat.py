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
    !estado -> muestra foco actual, siguiente paso y tareas pendientes
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


def cmd_estado():
    """Imprime un resumen completo del estado actual del proyecto."""
    from app.memory_store import load_work_state, load_tasks
    ws = load_work_state()
    tasks_data = load_tasks()
    pending = [
        t for t in tasks_data.get("tasks", [])
        if t.get("status") not in ("completed", "done")
    ]
    console.print("\n[bold]── Estado actual ────────────────────────────[/bold]")
    console.print(f"  [cyan]Foco:[/cyan]           {ws.get('current_focus', '—')}")
    console.print(f"  [cyan]Siguiente paso:[/cyan] {ws.get('next_step', '—')}")
    console.print(f"  [cyan]Último paso:[/cyan]   {ws.get('last_completed_step', '—')}")
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
    console.print("[bold]──────────────────────────────────────[/bold]\n")


def main():
    ensure_storage()

    if not Path(CHROMA_DIR).exists():
        raise FileNotFoundError(
            f"No encuentro el vector store en {CHROMA_DIR}. "
            "Primero ejecuta 'python indexacion.py'."
        )

    vectordb = load_vector_store()
    memory = build_memory()

    console.print("[bold green]Lautaro está iniciado[/bold green]")
    console.print("Escribe tu pregunta. 'salir', 'exit' o 'quit' para terminar.")
    console.print(
        "Comandos: [yellow]!reset[/yellow] (borra memoria) "
        "[yellow]!estado[/yellow] (resumen del proyecto)\n"
    )

    while True:
        user_input = console.input("[bold cyan]Tú:[/bold cyan] ").strip()

        if user_input.lower() in {"salir", "exit", "quit"}:
            console.print("[yellow]Hasta luego 👋[/yellow]")
            break

        if user_input.lower() == "!reset":
            if MEMORY_FILE.exists():
                MEMORY_FILE.unlink()
            console.print("[red]Memoria de conversación borrada.[/red]")
            memory = build_memory()
            continue

        # ── Item 3: Comando !estado ──────────────────────────────
        if user_input.lower() == "!estado":
            cmd_estado()
            continue

        if not user_input:
            continue

        console.print("[magenta]Pensando...[/magenta]")

        answer, sources = handle_query(user_input, vectordb, memory)

        console.print(Markdown(f"**Lautaro:** {answer}"))
        print_sources(sources)


if __name__ == "__main__":
    main()
