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
# D2: Validación de memory.json al arrancar
# ─────────────────────────────────────────────

def validate_memory_file() -> str:
    """Verifica que memory.json tiene el formato correcto {messages: [...]}.

    Llamar al inicio del programa (en chat.py o __main__).
    Si el archivo está en formato LangChain antiguo o corrupto,
    lo migra silenciosamente al formato propio o lo resetea.

    Returns:
        str con el resultado: 'ok' | 'migrated' | 'reset' | 'created'

    Never raises.
    """
    if not MEMORY_FILE.exists():
        _write_json(MEMORY_FILE, {"messages": []})
        return "created"
    try:
        raw = MEMORY_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        _write_json(MEMORY_FILE, {"messages": []})
        return "reset"

    # Formato correcto
    if isinstance(data.get("messages"), list):
        messages = data["messages"]
        valid = all(
            isinstance(m, dict) and "role" in m and "content" in m
            for m in messages
        )
        if valid or not messages:
            return "ok"
        _write_json(MEMORY_FILE, {"messages": []})
        return "reset"

    if isinstance(data, list):
        migrated: list[dict] = []
        for m in data:
            if isinstance(m, dict):
                role_map = {"human": "human", "ai": "ai", "HumanMessage": "human", "AIMessage": "ai"}
                role = role_map.get(m.get("type", ""), None)
                content = ""
                if isinstance(m.get("data"), dict):
                    content = m["data"].get("content", "")
                elif isinstance(m.get("content"), str):
                    content = m["content"]
                if role and content:
                    migrated.append({"role": role, "content": content})
        _write_json(MEMORY_FILE, {"messages": migrated})
        return "migrated"

    _write_json(MEMORY_FILE, {"messages": []})
    return "reset"


# ─────────────────────────────────────────────
# Memoria de conversación (corta)
# ─────────────────────────────────────────────

def load_memory() -> MemoryFile:
    return _read_json(MEMORY_FILE, {"messages": []})  # type: ignore[return-value]


def save_memory(data: MemoryFile) -> None:
    _write_json(MEMORY_FILE, data)


def append_message(role: str, content: str) -> None:
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
    _write_json(MEMORY_FILE, {"messages": []})


# ─────────────────────────────────────────────
# Perfil del usuario
# ─────────────────────────────────────────────

def load_profile() -> ProfileData:
    return _read_json(PROFILE_FILE, {})  # type: ignore[return-value]


def save_profile(data: ProfileData) -> None:
    _write_json(PROFILE_FILE, data)


# ─────────────────────────────────────────────
# D1: Limpieza y deduplicación de project_facts
# ─────────────────────────────────────────────

_FACTS_CANONICAL: dict[str, list[str]] = {
    "project_name":    ["nombre_proyecto", "nombre del proyecto", "project name"],
    "current_phase":   ["fase_actual", "fase actual", "current_phase_label", "phase"],
    "phase_label":     ["label_fase", "phase label", "phase_name"],
    "current_focus":   ["foco_actual", "foco actual", "focus"],
    "rag_status":      ["estado_rag", "estado rag", "rag status"],
    "memory_status":   ["estado_memoria", "estado memoria", "memory status"],
    "current_version": ["version_actual", "version actual", "version"],
    "stack":           ["tecnologias", "tecnologías", "stack_tecnologico"],
}

_FACTS_ALIAS_MAP: dict[str, str] = {
    alias: canonical
    for canonical, aliases in _FACTS_CANONICAL.items()
    for alias in aliases
}


def clean_project_facts(data: dict[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for raw_key, value in data.items():
        if not isinstance(value, str) or not value.strip():
            continue
        normalized = raw_key.strip().lower().replace(" ", "_").replace("-", "_")
        canonical = _FACTS_ALIAS_MAP.get(normalized, normalized)
        cleaned[canonical] = value.strip()
    return cleaned


def load_project_facts() -> dict[str, str]:
    return _read_json(PROJECT_FACTS_FILE, {})  # type: ignore[return-value]


def save_project_facts(data: dict[str, str]) -> None:
    _write_json(PROJECT_FACTS_FILE, clean_project_facts(data))


def update_project_fact(key: str, value: str) -> None:
    data = load_project_facts()
    data[key] = value
    _write_json(PROJECT_FACTS_FILE, clean_project_facts(data))


def save_project_fact(key: str, value: str) -> None:
    """Alias semántico de update_project_fact para uso desde tools.

    D3: invalida la caché semántica tras escribir.
    Never raises: ignora silenciosamente si key o value están vacíos.
    """
    key = key.strip()
    value = value.strip()
    if not key or not value:
        return
    update_project_fact(key, value)
    try:
        from app.semantic_cache import cache_invalidate
        cache_invalidate()
    except Exception:
        pass


# ─────────────────────────────────────────────
# Tareas
# ─────────────────────────────────────────────

def load_tasks() -> TasksFile:
    return _read_json(TASKS_FILE, {"tasks": []})  # type: ignore[return-value]


def save_tasks(data: TasksFile) -> None:
    _write_json(TASKS_FILE, data)


def add_task(title: str, priority: str = "medium", notes: str = "") -> str:
    """Agrega una nueva tarea y devuelve su ID.

    Guardia de duplicados: si ya existe una tarea pendiente con el mismo
    título (comparación case-insensitive), devuelve el ID existente sin
    crear un duplicado.
    """
    data = load_tasks()
    tasks = data.get("tasks", [])

    title_normalized = title.strip().lower()
    for existing in tasks:
        if (
            existing.get("title", "").strip().lower() == title_normalized
            and existing.get("status") == "pending"
        ):
            return existing["id"]

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

    Paso C: escribe updated_at al modificar el estado,
    habilitando detección de tareas estancadas en session briefing.

    Never raises: si task_id no existe, no hace nada.
    """
    data = load_tasks()
    for task in data.get("tasks", []):
        if task["id"] == task_id:
            task["status"] = status
            task["updated_at"] = datetime.now().isoformat(timespec="seconds")  # Paso C
            break
    _write_json(TASKS_FILE, data)


# ─────────────────────────────────────────────
# Work state (estado operativo actual)
# ─────────────────────────────────────────────

def load_work_state() -> WorkState:
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
    for w in validate_work_state(data):  # type: ignore[arg-type]
        print(w)
    return data  # type: ignore[return-value]


def save_work_state(data: WorkState) -> None:
    _write_json(WORK_STATE_FILE, data)


def update_work_state(field: str, value: str) -> None:
    """Actualiza un campo específico de work_state.json de forma dinámica.

    D3: invalida la caché semántica tras escribir.
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
    try:
        from app.semantic_cache import cache_invalidate
        cache_invalidate()
    except Exception:
        pass


def update_session_goal(goal: str) -> None:
    """Paso B: guarda el objetivo específico de la sesión actual.

    A diferencia de current_focus (permanente), session_goal
    describe qué quiere lograr el usuario HOY en esta sesión.
    Se resetea a '' al inicio de cada sesión nueva si se desea.

    Never raises.
    """
    goal = goal.strip()
    if not goal:
        return
    data = load_work_state()
    data["session_goal"] = goal  # type: ignore[typeddict-unknown-key]
    data["last_updated"] = datetime.now().strftime("%Y-%m-%d")  # type: ignore[typeddict-unknown-key]
    _write_json(WORK_STATE_FILE, data)
    try:
        from app.semantic_cache import cache_invalidate
        cache_invalidate()
    except Exception:
        pass


# ─────────────────────────────────────────────
# Memoria episódica (8A: con indexación en Chroma)
# ─────────────────────────────────────────────

MAX_EPISODES = 10


def save_episode(summary: str, turns: int) -> None:
    """Guarda un resumen de sesión en episodic_memory.json e indexa en Chroma."""
    data: EpisodicMemory = _read_json(EPISODIC_MEMORY_FILE, {"episodes": []})  # type: ignore[assignment]
    episodes = data.get("episodes", [])

    now = datetime.now()
    new_episode: dict = {
        "date":    now.strftime("%Y-%m-%d"),
        "time":    now.strftime("%H:%M"),
        "turns":   turns,
        "summary": summary.strip(),
    }
    episodes.append(new_episode)

    data["episodes"] = episodes[-MAX_EPISODES:]
    _write_json(EPISODIC_MEMORY_FILE, data)

    try:
        from app.episode_store import index_episode
        index_episode(new_episode)
    except Exception:
        pass


def load_last_episode() -> EpisodeItem | None:
    """Devuelve el episodio más reciente o None si no hay ninguno.

    Paso A: el dict devuelto incluye todos los campos opcionales del schema
    (exitoso, carril_dominante, tareas_completadas) si fueron escritos
    por episode_store.close_session_episode(). El caller puede leerlos
    directamente sin transformación adicional.
    """
    data: EpisodicMemory = _read_json(EPISODIC_MEMORY_FILE, {"episodes": []})  # type: ignore[assignment]
    episodes = data.get("episodes", [])
    return episodes[-1] if episodes else None
