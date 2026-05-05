"""
Asistente local:
- Usa Ollama (por defecto llama3.2:latest) como LLM.
- Recupera contexto de tus docs con Chroma (RAG).
- Guarda memoria de conversación en storage/memory.json.

Ejecutar:
    python chat.py

Salir:
    escribir 'salir', 'exit' o 'quit'.

Comando especial:
    !reset -> borra la memoria de conversación (storage/memory.json)
"""

from pathlib import Path

from rich.markdown import Markdown

from app.router import route_query
from app.tools import list_project_files, read_project_file, extract_file_path

from app.chat_core import (
    CHROMA_DIR,
    MEMORY_FILE,
    ensure_storage,
    load_vector_store,
    build_memory,
    build_retriever,
    build_chain,
    build_structured_memory_context,
)
from app.chat_ui import console, print_debug_retrieval, print_sources


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

        route = route_query(user_input)

        if route == "tool_list_files":
            files = list_project_files()
            console.print("\n".join(files[:50]))
            continue

        if route == "tool_read_file":
            file_path = extract_file_path(user_input)
            if not file_path:
                console.print("Escribe la ruta del archivo")
                file_path = console.input("> ").strip()

            content = read_project_file(file_path)
            console.print(content)
            continue

        console.print("[magenta]Pensando...[/magenta]")

        retriever = build_retriever(vectordb, user_input)
        debug_docs = retriever.invoke(user_input)
        print_debug_retrieval(user_input, debug_docs)

        memory_context = build_structured_memory_context()
        chain = build_chain(retriever, memory, memory_context)
        result = chain.invoke({"question": user_input})

        answer = result["answer"]
        docs = result.get("source_documents", [])

        console.print(Markdown(f"**Lautaro:** {answer}"))
        print_sources(docs)


if __name__ == "__main__":
    main()