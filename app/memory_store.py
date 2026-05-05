import json
from pathlib import Path
from datetime import datetime


STORAGE_DIR = Path("storage")

MEMORY_FILE = STORAGE_DIR / "memory.json"
PROFILE_FILE = STORAGE_DIR / "profile.json"
PROJECT_FACTS_FILE = STORAGE_DIR / "project_facts.json"
TASKS_FILE = STORAGE_DIR / "tasks.json"
WORK_STATE_FILE = STORAGE_DIR / "work_state.json"


def _read_json(path: Path, default):
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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


def load_profile():
    return _read_json(PROFILE_FILE, {})


def save_profile(data):
    _write_json(PROFILE_FILE, data)


def load_project_facts():
    return _read_json(PROJECT_FACTS_FILE, {})


def save_project_facts(data):
    _write_json(PROJECT_FACTS_FILE, data)


def update_project_fact(key: str, value):
    data = load_project_facts()
    data[key] = value
    _write_json(PROJECT_FACTS_FILE, data)


def load_tasks():
    return _read_json(TASKS_FILE, {"tasks": []})


def save_tasks(data):
    _write_json(TASKS_FILE, data)


def add_task(title: str, priority: str = "medium", notes: str = ""):
    data = load_tasks()
    tasks = data.get("tasks", [])

    new_id = f"T-{len(tasks) + 1:03d}"
    tasks.append(
        {
            "id": new_id,
            "title": title,
            "status": "pending",
            "priority": priority,
            "notes": notes
        }
    )

    data["tasks"] = tasks
    _write_json(TASKS_FILE, data)
    return new_id


def update_task_status(task_id: str, status: str):
    data = load_tasks()
    for task in data.get("tasks", []):
        if task["id"] == task_id:
            task["status"] = status
            break
    _write_json(TASKS_FILE, data)


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


def update_work_state(current_focus=None, last_completed_step=None, next_step=None):
    data = load_work_state()

    if current_focus is not None:
        data["current_focus"] = current_focus
    if last_completed_step is not None:
        data["last_completed_step"] = last_completed_step
    if next_step is not None:
        data["next_step"] = next_step

    _write_json(WORK_STATE_FILE, data)