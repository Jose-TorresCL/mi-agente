import json
import shutil
from pathlib import Path
from datetime import datetime


STORAGE_DIR = Path("storage")

MEMORY_FILE = STORAGE_DIR / "memory.json"
PROFILE_FILE = STORAGE_DIR / "profile.json"
PROJECT_FACTS_FILE = STORAGE_DIR / "project_facts.json"
TASKS_FILE = STORAGE_DIR / "tasks.json"
WORK_STATE_FILE = STORAGE_DIR / "work_state.json"


# ─────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────

def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, data):
    """Escribe JSON con backup automático del archivo anterior (item 2)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # ── Item 2: Backup automático ─────────────────────────────
    if path.exists():
        shutil.copy2(path, path.with_suffix(".bak"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# Memoria de conversación (corta)
# ─────────────────────────────────────────────

def load_memory():
    return _read_json(MEMORY_FILE, {"messages": []})


def save_memory(data):
    _write_json(MEMORY_FILE, data)


def append_message(role: str, content: str):
    data = load_memory()
    data["messages"].append(
        {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(timespec="seconds")
        }
    )
    _write_json(MEMORY_FILE, data)


def clear_memory():
    _write_json(MEMORY_FILE, {"messages": []})


# ─────────────────────────────────────────────
# Perfil del usuario
# ─────────────────────────────────────────────

def load_profile():
    return _read_json(PROFILE_FILE, {})


def save_profile(data):
    _write_json(PROFILE_FILE, data)


# ─────────────────────────────────────────────
# Hechos persistentes del proyecto
# ─────────────────────────────────────────────

def load_project_facts():
    return _read_json(PROJECT_FACTS_FILE, {})


def save_project_facts(data):
    _write_json(PROJECT_FACTS_FILE, data)


def update_project_fact(key: str, value):
    """Actualiza un campo específico de project_facts.json sin tocar el resto."""
    data = load_project_facts()
    data[key] = value
    _write_json(PROJECT_FACTS_FILE, data)


def save_project_fact(key: str, value: str) -> None:
    """Alias semántico de update_project_fact para uso desde tools."""
    key = key.strip()
    value = value.strip()
    if not key or not value:
        return
    update_project_fact(key, value)


# ─────────────────────────────────────────────
# Tareas
# ─────────────────────────────────────────────

def load_tasks():
    return _read_json(TASKS_FILE, {"tasks": []})


def save_tasks(data):
    _write_json(TASKS_FILE, data)


def add_task(title: str, priority: str = "medium", notes: str = "") -> str:
    """Agrega una nueva tarea y devuelve su ID.

    Item 4: ID único basado en timestamp para evitar duplicados
    al borrar tareas.
    """
    data = load_tasks()
    tasks = data.get("tasks", [])

    # ── Item 4: ID único por timestamp ───────────────────────────
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


def update_task_status(task_id: str, status: str):
    """Cambia el estado de una tarea por su ID."""
    data = load_tasks()
    for task in data.get("tasks", []):
        if task["id"] == task_id:
            task["status"] = status
            break
    _write_json(TASKS_FILE, data)


# ─────────────────────────────────────────────
# Work state (estado operativo actual)
# ─────────────────────────────────────────────

def load_work_state():
    return _read_json(
        WORK_STATE_FILE,
        {
            "current_focus": "",
            "last_completed_step": "",
            "next_step": "",
            "current_blockers": [],
            "notes": []
        }
    )


def save_work_state(data):
    _write_json(WORK_STATE_FILE, data)


def update_work_state(field: str, value: str) -> None:
    """Actualiza un campo específico de work_state.json de forma dinámica.

    Uso: update_work_state("current_focus", "fase 3 — router semántico")

    Para current_blockers acepta un string que se añade a la lista
    si no está ya presente.
    """
    data = load_work_state()

    if field == "current_blockers":
        blockers = data.get("current_blockers", [])
        if value.strip() and value.strip() not in blockers:
            blockers.append(value.strip())
        data["current_blockers"] = blockers
    else:
        data[field] = value.strip()

    data["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    _write_json(WORK_STATE_FILE, data)
