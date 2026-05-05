from __future__ import annotations

from app.tools import extract_file_path

TOOL_LIST_KEYWORDS = [
    "listar archivos",
    "lista de archivos",
    "qué archivos",
    "que archivos",
    "archivos del proyecto",
    "ver archivos",
    "mostrar archivos",
    "muéstrame los archivos",
    "muestrame los archivos",
]

TOOL_READ_KEYWORDS = [
    "leer archivo",
    "muéstrame el archivo",
    "muestrame el archivo",
    "abre el archivo",
    "ver archivo",
    "mostrar archivo",
    "lee el archivo",
    "leer docs",
    "leer documentación",
    "leer documento",
    "mostrar documento",
]

MEMORY_KEYWORDS = [
    "mi estilo",
    "preferencia",
    "preferido",
    "cómo prefiero",
    "como prefiero",
    "flujo",
    "cómo trabajo",
    "como trabajo",
    "estado actual",
    "foco actual",
    "siguiente paso",
    "fase actual",
    "en qué vamos",
    "en que vamos",
    "qué sigue",
    "que sigue",
    "tareas",
    "pendientes",
    "memoria",
]

RAG_HINTS = [
    "según los documentos",
    "segun los documentos",
    "qué dice",
    "que dice",
    "explica",
    "explicame",
    "arquitectura",
    "objetivo",
    "relación entre",
    "relacion entre",
]

def route_query(question: str) -> str:
    q = question.lower().strip()

    has_file_path = extract_file_path(question) is not None
    if has_file_path:
        return "tool_read_file"

    if any(keyword in q for keyword in TOOL_LIST_KEYWORDS):
        return "tool_list_files"

    if any(keyword in q for keyword in TOOL_READ_KEYWORDS):
        return "tool_read_file"

    if any(keyword in q for keyword in MEMORY_KEYWORDS):
        return "memory"

    if any(keyword in q for keyword in RAG_HINTS):
        return "rag"

    return "rag"