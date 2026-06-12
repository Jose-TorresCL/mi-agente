"""Formatter RAG para convertir chunks técnicos en resúmenes claros."""
from __future__ import annotations
import re


def extract_key_info(chunk: str) -> str:
    """Extrae la información clave de un chunk técnico y la deja lista para resumen."""
    if not isinstance(chunk, str):
        return ""

    text = chunk.strip()
    if not text:
        return ""

    # Eliminar encabezados Markdown/HTML básicos y separar por líneas.
    text = re.sub(r"(?m)^#{1,6}\s+", "", text)
    text = re.sub(r"<[^>]+>", "", text)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    candidates = []
    for line in lines:
        if len(line) < 10:
            continue
        if any(line.lower().startswith(prefix) for prefix in ("nota:", "importante:", "resumen:", "objetivo:", "acción:")):
            candidates.append(line)
            break
        candidates.append(line)

    if not candidates:
        candidates = lines

    summary = candidates[0]
    if len(summary) > 220:
        summary = summary[:217].rsplit(" ", 1)[0] + "..."

    return summary


def format_chunks_to_summary(chunks: list[str]) -> str:
    """Convierte una lista de chunks técnicos en un resumen claro y legible."""
    summaries: list[str] = []
    for chunk in chunks:
        summary = extract_key_info(chunk)
        if summary:
            summaries.append(summary)
    return "\n".join(summaries)
