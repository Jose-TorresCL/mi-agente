from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

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
