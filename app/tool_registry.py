from __future__ import annotations

from app.tools import (
    list_project_files,
    read_project_file,
    tool_save_fact,
    tool_create_task,
    tool_complete_task,
    tool_update_work_state,
)

TOOLS: dict[str, dict] = {
    "tool_list_files": {
        "fn":          list_project_files,
        "carril":      "tool_list_files",
        "descripcion": "Lista archivos del proyecto",
    },
    "tool_read_file": {
        "fn":          read_project_file,
        "carril":      "tool_read_file",
        "descripcion": "Lee el contenido de un archivo",
    },
    "tool_save_fact": {
        "fn":          tool_save_fact,
        "carril":      "tool_save_fact",
        "descripcion": "Guarda un hecho en project_facts.json",
    },
    "tool_create_task": {
        "fn":          tool_create_task,
        "carril":      "tool_create_task",
        "descripcion": "Crea una tarea en tasks.json",
    },
    "tool_complete_task": {
        "fn":          tool_complete_task,
        "carril":      "tool_complete_task",
        "descripcion": "Marca una tarea como completada",
    },
    "tool_update_work_state": {
        "fn":          tool_update_work_state,
        "carril":      "tool_update_work_state",
        "descripcion": "Actualiza work_state.json",
    },
}
