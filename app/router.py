# app/router.py
from __future__ import annotations

def route_query(question: str) -> str:
    q = question.lower()

    if any(word in q for word in [
        "listar archivos", "lista de archivos", "qué archivos", "que archivos",
        "archivos del proyecto", "ver archivos"
    ]):
        return "tool_list_files"

    if any(word in q for word in [
        "leer archivo", "muéstrame el archivo", "muestrame el archivo",
        "abre el archivo", "ver archivo", "leer docs", "leer documentación"
    ]):
        return "tool_read_file"

    if any(word in q for word in [
        "estado", "foco actual", "siguiente paso", "fase", "preferencia",
        "estilo", "flujo", "memoria", "tareas"
    ]):
        return "memory"

    return "rag"