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
    !reset -> borra la memoria de conversación (storage/memory.json)
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
    console.print("Comando especial: [yellow]!reset[/yellow] para borrar la memoria.\n")

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

        if not user_input:
            continue

        console.print("[magenta]Pensando...[/magenta]")

        answer, sources = handle_query(user_input, vectordb, memory)

        console.print(Markdown(f"**Lautaro:** {answer}"))
        print_sources(sources)


if __name__ == "__main__":
    main()
