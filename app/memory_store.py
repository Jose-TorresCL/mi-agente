"""Capa de persistencia de memoria — todos los JSON de storage/

Este módulo es la única puerta de entrada y salida para los archivos JSON.
Ningún otro módulo debe leer o escribir storage/ directamente.

Archivos gestionados:
  storage/memory.json         → memoria de conversación (corta)
  storage/profile.json        → perfil del usuario
  storage/project_facts.json  → hechos persistentes del proyecto
  storage/tasks.json          → tareas pendientes/completadas
  storage/work_state.json     → estado operativo actual
  storage/episodic_memory.json → resúmenes de sesiones pasadas

Convención de nombres:
  load_*   → lee el archivo, devuelve dict/list (nunca lanza)
  save_*   → escribe el archivo completo
  add_*    → añade un elemento a una colección
  update_* → actualiza un campo específico sin tocar el resto
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from datetime import datetime

from app.schemas import (
    WorkState, TaskItem, TasksFile,
    ProfileData, Message, MemoryFile,
    EpisodeItem, EpisodicMemory,
    validate_work_state,
)


STORAGE_DIR = Path("storage")

MEMORY_FILE          = STORAGE_DIR / "memory.json"
PROFILE_FILE         = STORAGE_DIR / "profile.json"
PROJECT_FACTS_FILE   = STORAGE_DIR / "project_facts.json"
TASKS_FILE           = STORAGE_DIR / "tasks.json"
WORK_STATE_FILE      = STORAGE_DIR / "work_state.json"
EPISODIC_MEMORY_FILE = STORAGE_DIR / "episodic_memory.json"


# ─────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────

def _read_json(path: Path, default: object) -> object:
    """Lee un archivo JSON y devuelve el contenido o el default si falla.

    Never raises: errores de IO o JSON devuelven el default.
    """
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, data: object) -> None:
    """Escribe JSON con backup automático del archivo anterior.

    Args:
        path: Ruta de destino.
        data: Objeto serializable a JSON.

    Never raises: fallos de escritura se propagan (no se silencian aquí).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_suffix(".bak"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# Memoria de conversación (corta)
# ─────────────────────────────────────────────

def load_memory() -> MemoryFile:
    """Carga memory.json. Devuelve estructura vacía si no existe.

    Returns:  MemoryFile con lista 'messages'.
    Never raises.
    """
    return _read_json(MEMORY_FILE, {"messages": []})  # type: ignore[return-value]


def save_memory(data: MemoryFile) -> None:
    """Sobrescribe memory.json con el contenido de data."""
    _write_json(MEMORY_FILE, data)


def append_message(role: str, content: str) -> None:
    """Añade un mensaje al historial de conversación.

    Args:
        role:    'user' o 'assistant'.
        content: Texto del mensaje.

    Never raises.
    """
    data = load_memory()
    data["messages"].append(
        {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(timespec="seconds")
        }
    )
    _write_json(MEMORY_FILE, data)


def clear_memory() -> None:
    """Borra el historial de conversación (equivale a !reset)."""
    _write_json(MEMORY_FILE, {"messages": []})


# ─────────────────────────────────────────────
# Perfil del usuario
# ─────────────────────────────────────────────

def load_profile() -> ProfileData:
    """Carga profile.json. Devuelve dict vacío si no existe.

    Returns:  ProfileData con los campos conocidos del usuario.
    Never raises.
    """
    return _read_json(PROFILE_FILE, {})  # type: ignore[return-value]


def save_profile(data: ProfileData) -> None:
    """Sobrescribe profile.json con el contenido de data."""
    _write_json(PROFILE_FILE, data)


# ─────────────────────────────────────────────
# Hechos persistentes del proyecto
# ─────────────────────────────────────────────

def load_project_facts() -> dict[str, str]:
    """Carga project_facts.json. Devuelve dict vacío si no existe.

    Returns:  dict[str, str] con los hechos guardados.
    Never raises.
    """
    return _read_json(PROJECT_FACTS_FILE, {})  # type: ignore[return-value]


def save_project_facts(data: dict[str, str]) -> None:
    """Sobrescribe project_facts.json con el contenido de data."""
    _write_json(PROJECT_FACTS_FILE, data)


def update_project_fact(key: str, value: str) -> None:
    """Actualiza un campo específico de project_facts.json sin tocar el resto.

    Args:
        key:   Clave del hecho (ej: 'fase_actual').
        value: Valor del hecho (ej: 'fase_4').

    Never raises.
    """
    data = load_project_facts()
    data[key] = value
    _write_json(PROJECT_FACTS_FILE, data)


def save_project_fact(key: str, value: str) -> None:
    """Alias semántico de update_project_fact para uso desde tools.

    Args:
        key:   Clave del hecho. Se hace strip() automáticamente.
        value: Valor del hecho. Se hace strip() automáticamente.

    Never raises: ignora silenciosamente si key o value están vacíos.
    """
    key = key.strip()
    value = value.strip()
    if not key or not value:
        return
    update_project_fact(key, value)


# ─────────────────────────────────────────────
# Tareas
# ─────────────────────────────────────────────

def load_tasks() -> TasksFile:
    """Carga tasks.json. Devuelve estructura vacía si no existe.

    Returns:  TasksFile con lista 'tasks'.
    Never raises.
    """
    return _read_json(TASKS_FILE, {"tasks": []})  # type: ignore[return-value]


def save_tasks(data: TasksFile) -> None:
    """Sobrescribe tasks.json con el contenido de data."""
    _write_json(TASKS_FILE, data)


def add_task(title: str, priority: str = "medium", notes: str = "") -> str:
    """Agrega una nueva tarea y devuelve su ID.

    Args:
        title:    Título de la tarea.
        priority: 'low' | 'medium' | 'high'. Default 'medium'.
        notes:    Notas adicionales. Default ''.

    Returns:
        str con el ID generado (formato T-MMDDHHMISS).

    Never raises.
    """
    data = load_tasks()
    tasks = data.get("tasks", [])
    new_id = f"T-{datetime.now().strftime('%m%d%H%M%S')}"
    tasks.append(
        {
            "id": new_id,
            "title": title.strip(),
            "status": "pending",
            "priority": priority.strip().lower(),
            "notes": notes.strip(),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    data["tasks"] = tasks
    _write_json(TASKS_FILE, data)
    return new_id


def update_task_status(task_id: str, status: str) -> None:
    """Cambia el estado de una tarea por su ID.

    Args:
        task_id: ID de la tarea (ej: 'T-0506132952').
        status:  Nuevo estado ('pending' | 'completed').

    Never raises: si task_id no existe, no hace nada.
    """
    data = load_tasks()
    for task in data.get("tasks", []):
        if task["id"] == task_id:
            task["status"] = status
            break
    _write_json(TASKS_FILE, data)


# ─────────────────────────────────────────────
# Work state (estado operativo actual)
# ─────────────────────────────────────────────

def load_work_state() -> WorkState:
    """Carga work_state.json. Devuelve estructura vacía si no existe.

    Returns:  WorkState con el estado operativo actual.
    Never raises.
    """
    data = _read_json(
        WORK_STATE_FILE,
        {
            "current_focus": "",
            "last_completed": "",
            "next_step": "",
            "current_blockers": [],
            "notes": [],
        }
    )  # type: ignore[assignment]
    # Nivel 2: advertir sobre claves desconocidas (no bloquea)
    for w in validate_work_state(data):  # type: ignore[arg-type]
        print(w)
    return data  # type: ignore[return-value]


def save_work_state(data: WorkState) -> None:
    """Sobrescribe work_state.json con el contenido de data."""
    _write_json(WORK_STATE_FILE, data)


def update_work_state(field: str, value: str) -> None:
    """Actualiza un campo específico de work_state.json de forma dinámica.

    Args:
        field: Nombre del campo (debe estar en WorkState).
        value: Valor a asignar.

    Never raises.
    """
    data = load_work_state()
    if field == "current_blockers":
        blockers: list[str] = data.get("current_blockers", [])  # type: ignore[assignment]
        if value.strip() and value.strip() not in blockers:
            blockers.append(value.strip())
        data["current_blockers"] = blockers  # type: ignore[typeddict-unknown-key]
    else:
        data[field] = value.strip()  # type: ignore[literal-required]
    data["last_updated"] = datetime.now().strftime("%Y-%m-%d")  # type: ignore[typeddict-unknown-key]
    _write_json(WORK_STATE_FILE, data)


# ─────────────────────────────────────────────
# Memoria episódica (SimpleMem)
# ─────────────────────────────────────────────

MAX_EPISODES = 10  # guardamos los últimos 10 episodios; el más viejo se descarta


def save_episode(summary: str, turns: int) -> None:
    """Guarda un resumen de sesión en episodic_memory.json.

    Args:
        summary: Texto del resumen generado por el LLM.
        turns:   Número de turnos de la sesión.

    Estructura de cada episodio: EpisodeItem (ver schemas.py).
    Mantiene solo los últimos MAX_EPISODES episodios.

    Never raises.
    """
    data: EpisodicMemory = _read_json(EPISODIC_MEMORY_FILE, {"episodes": []})  # type: ignore[assignment]
    episodes = data.get("episodes", [])

    now = datetime.now()
    episodes.append({
        "date":    now.strftime("%Y-%m-%d"),
        "time":    now.strftime("%H:%M"),
        "turns":   turns,
        "summary": summary.strip(),
    })

    data["episodes"] = episodes[-MAX_EPISODES:]
    _write_json(EPISODIC_MEMORY_FILE, data)


def load_last_episode() -> EpisodeItem | None:
    """Devuelve el episodio más reciente o None si no hay ninguno.

    Returns:
        EpisodeItem con date, time, turns y summary,
        o None si episodic_memory.json está vacío.

    Never raises.
    """
    data: EpisodicMemory = _read_json(EPISODIC_MEMORY_FILE, {"episodes": []})  # type: ignore[assignment]
    episodes = data.get("episodes", [])
    return episodes[-1] if episodes else None
