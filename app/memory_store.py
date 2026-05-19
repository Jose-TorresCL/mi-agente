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
        # Verificar que los mensajes tienen el schema correcto {role, content}
        messages = data["messages"]
        valid = all(
            isinstance(m, dict) and "role" in m and "content" in m
            for m in messages
        )
        if valid or not messages:
            return "ok"
        # Mensajes con estructura incorrecta: resetear
        _write_json(MEMORY_FILE, {"messages": []})
        return "reset"

    # Formato LangChain antiguo: tiene lista plana o clave distinta
    # Intentar migrar si tiene estructura tipo [{"type": "human", "data": {...}}]
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

    # Cualquier otro formato desconocido: resetear
    _write_json(MEMORY_FILE, {"messages": []})
    return "reset"


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
# D1: Limpieza y deduplicación de project_facts
# ─────────────────────────────────────────────

# Claves canónicas conocidas — cualquier variante se normaliza a estas
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

# Mapa inverso: alias → clave canónica
_FACTS_ALIAS_MAP: dict[str, str] = {
    alias: canonical
    for canonical, aliases in _FACTS_CANONICAL.items()
    for alias in aliases
}


def clean_project_facts(data: dict[str, str]) -> dict[str, str]:
    """Normaliza y deduplica un diccionario de project_facts.

    Operaciones:
    1. Elimina valores vacíos o solo espacios.
    2. Normaliza claves: minúsculas y espacios → guión_bajo.
    3. Resuelve aliases a claves canónicas (ej: 'fase_actual' → 'current_phase').
    4. En caso de duplicado, conserva el valor más reciente (último en el dict).

    Args:
        data: dict crudo leído de project_facts.json

    Returns:
        dict limpio y deduplicado.

    Never raises.
    """
    cleaned: dict[str, str] = {}
    for raw_key, value in data.items():
        # 1. Purgar valores vacíos
        if not isinstance(value, str) or not value.strip():
            continue
        # 2. Normalizar clave
        normalized = raw_key.strip().lower().replace(" ", "_").replace("-", "_")
        # 3. Resolver alias
        canonical = _FACTS_ALIAS_MAP.get(normalized, normalized)
        # 4. Último valor gana (sobrescribe duplicados anteriores)
        cleaned[canonical] = value.strip()
    return cleaned


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
    """Sobrescribe project_facts.json. Aplica limpieza D1 antes de escribir."""
    _write_json(PROJECT_FACTS_FILE, clean_project_facts(data))


def update_project_fact(key: str, value: str) -> None:
    """Actualiza un campo específico de project_facts.json sin tocar el resto.

    Args:
        key:   Clave del hecho (ej: 'fase_actual').
        value: Valor del hecho (ej: 'fase_4').

    Never raises.
    """
    data = load_project_facts()
    data[key] = value
    # D1: limpia antes de escribir
    _write_json(PROJECT_FACTS_FILE, clean_project_facts(data))


def save_project_fact(key: str, value: str) -> None:
    """Alias semántico de update_project_fact para uso desde tools.

    D3: invalida la caché semántica tras escribir para evitar
    respuestas obsoletas en la próxima consulta RAG.

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
    # D3: invalidar caché semántica — los hechos cambiaron
    try:
        from app.semantic_cache import cache_invalidate
        cache_invalidate()
    except Exception:
        pass  # caché opcional: si falla, no bloquear la escritura


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

    Guardia de duplicados: si ya existe una tarea pendiente con el mismo
    título (comparación case-insensitive), devuelve el ID existente sin
    crear un duplicado.

    Args:
        title:    Título de la tarea.
        priority: 'low' | 'medium' | 'high'. Default 'medium'.
        notes:    Notas adicionales. Default ''.

    Returns:
        str con el ID de la tarea (nuevo o existente).

    Never raises.
    """
    data = load_tasks()
    tasks = data.get("tasks", [])

    # Guardia: evitar duplicados por título en tareas pendientes (case-insensitive)
    title_normalized = title.strip().lower()
    for existing in tasks:
        if (
            existing.get("title", "").strip().lower() == title_normalized
            and existing.get("status") == "pending"
        ):
            return existing["id"]  # ya existe, devolver ID sin duplicar

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

    D3: invalida la caché semántica tras escribir para evitar
    respuestas obsoletas en la próxima consulta RAG.

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
    # D3: invalidar caché semántica — el estado de trabajo cambió
    try:
        from app.semantic_cache import cache_invalidate
        cache_invalidate()
    except Exception:
        pass  # caché opcional: si falla, no bloquear la escritura


# ─────────────────────────────────────────────
# Memoria episódica (8A: con indexación en Chroma)
# ─────────────────────────────────────────────

MAX_EPISODES = 10  # guardamos los últimos 10 episodios; el más viejo se descarta


def save_episode(summary: str, turns: int) -> None:
    """Guarda un resumen de sesión en episodic_memory.json e indexa en Chroma.

    Args:
        summary: Texto del resumen generado por el LLM.
        turns:   Número de turnos de la sesión.

    Estructura de cada episodio: EpisodeItem (ver schemas.py).
    Mantiene solo los últimos MAX_EPISODES episodios en JSON.
    Chroma conserva TODOS los episodios indexados (sin límite de 10).

    Never raises.
    """
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

    # 8A: indexar en Chroma de forma no bloqueante
    # Si Chroma falla, el episodio ya está guardado en JSON — no se pierde nada.
    try:
        from app.episode_store import index_episode
        index_episode(new_episode)
    except Exception:
        pass  # episodio guardado en JSON aunque Chroma falle


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
