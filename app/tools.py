from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime

from app.memory_store import (
    save_project_fact,
    add_task,
    update_task_status,
    update_work_state,
    load_tasks,
)

PROJECT_ROOT = Path(".")
ALLOWED_DIRS = [
    PROJECT_ROOT / "app",
    PROJECT_ROOT / "data" / "docs",
    PROJECT_ROOT / "storage"
]

SKIP_DIR_NAMES = {"__pycache__", ".git", ".venv", "chroma_db", "chroma", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
# Fix 3: añadimos .bak a las extensiones omitidas
SKIP_SUFFIXES = {".pyc", ".bak"}
VALID_PRIORITIES = {"low", "medium", "high"}

# Campos permitidos para actualizar work_state (lista blanca de seguridad)
ALLOWED_WORK_STATE_FIELDS = {
    "current_focus",
    "current_phase",
    "last_completed_step",
    "next_step",
    "current_blockers",
    "session_goal",
}

# Aliases en español para los campos de work_state
WORK_STATE_FIELD_ALIASES = {
    "foco":                   "current_focus",
    "foco actual":            "current_focus",
    "focus":                  "current_focus",
    "fase":                   "current_phase",
    "fase actual":            "current_phase",
    "phase":                  "current_phase",
    "último paso":            "last_completed_step",
    "ultimo paso":            "last_completed_step",
    "último paso completado": "last_completed_step",
    "siguiente paso":         "next_step",
    "next step":              "next_step",
    "bloqueante":             "current_blockers",
    "bloqueo":                "current_blockers",
    "blockers":               "current_blockers",
    "meta sesión":            "session_goal",
    "meta de sesión":         "session_goal",
    "objetivo sesión":        "session_goal",
    "session goal":           "session_goal",
}

# Prefijos de navegación que se deben eliminar del valor extraído
_VALUE_PREFIXES = [
    "el foco a",
    "foco a",
    "la fase a",
    "fase a",
    "siguiente paso a",
    "el siguiente paso a",
    "último paso a",
    "el último paso a",
    "bloqueante a",
    "bloqueo a",
    "work_state a",
]


def _is_allowed(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except Exception:
        return False

    for base in ALLOWED_DIRS:
        try:
            if resolved.is_relative_to(base.resolve()):
                return True
        except AttributeError:
            base_resolved = base.resolve()
            if str(resolved).startswith(str(base_resolved)):
                return True
    return False


def _should_skip(path: Path) -> bool:
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return True
    if path.suffix in SKIP_SUFFIXES:
        return True
    return False


def list_project_files() -> list[str]:
    files = []
    for base in ALLOWED_DIRS:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if _should_skip(p):
                continue
            if p.is_file():
                files.append(str(p.relative_to(PROJECT_ROOT)))
    return sorted(files)


def extract_file_path(text: str) -> str | None:
    cleaned = text.strip()
    markers = ["data/", "data\\\\", "app/", "app\\\\", "storage/", "storage\\\\"]
    lower_text = cleaned.lower()

    for marker in markers:
        idx = lower_text.find(marker.lower())
        if idx == -1:
            continue
        candidate = cleaned[idx:].strip()
        candidate = candidate.strip('"').strip("'").strip("`")
        candidate = candidate.rstrip("?.!,;:")
        for stop in [" y ", " luego ", " después ", " despues "]:
            stop_idx = candidate.lower().find(stop)
            if stop_idx != -1:
                candidate = candidate[:stop_idx].strip()
        return candidate
    return None


def read_project_file(path: str, max_chars: int = 8000) -> str:
    p = Path(path)
    if not _is_allowed(p):
        return "Ruta no permitida. Usa solo archivos dentro de app/, data/docs/ o storage/."
    if not p.exists() or not p.is_file():
        return "Archivo no encontrado."
    text = p.read_text(encoding="utf-8", errors="ignore")
    return text[:max_chars]


# ─────────────────────────────────────────────
# Tools de escritura seguras
# ─────────────────────────────────────────────

def tool_save_fact(question: str) -> str:
    prefixes = [
        "guarda como hecho que",
        "guarda como hecho:",
        "guarda como hecho",
        "guardar hecho que",
        "registra que",
        "anota que",
        "guarda el hecho que",
        "registra el hecho que",
        "guarda esto como hecho:",
        "guarda esto como hecho",
    ]
    content = question.strip()
    for prefix in prefixes:
        if content.lower().startswith(prefix):
            content = content[len(prefix):].strip()
            break

    if not content:
        return "No pude guardar el hecho: no entendí el contenido."

    key = f"hecho_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    save_project_fact(key, content)
    return f"✓ Hecho guardado: \"{content}\""


def tool_create_task(title: str, priority: str = "medium", notes: str = "") -> str:
    """Crea una nueva tarea en tasks.json."""
    title = title.strip()
    priority = priority.strip().lower()
    notes = notes.strip()

    if not title:
        return "No pude crear la tarea: falta el título."
    if priority not in VALID_PRIORITIES:
        priority = "medium"

    task_id = add_task(title=title, priority=priority, notes=notes)
    return f"✓ Tarea creada: [{task_id}] {title} (prioridad: {priority})"


# ─────────────────────────────────────────────
# Tool: completar tarea  (Fase 2)
# ─────────────────────────────────────────────

def extract_task_id(text: str) -> str:
    """Extrae un ID de tarea del texto del usuario."""
    match = re.search(r"T-(\d+)", text, re.IGNORECASE)
    if match:
        return f"T-{match.group(1)}"

    match = re.search(r"\b(\d{3})\b", text)
    if match:
        return f"T-{match.group(1)}"

    return ""


def tool_complete_task(task_id: str) -> str:
    """Marca una tarea existente como completada dado su ID."""
    if not task_id:
        return "No pude identificar el ID de la tarea. Indícalo así: T-001, T-002..."

    tasks_data = load_tasks()
    tasks = tasks_data.get("tasks", [])

    found = False
    for task in tasks:
        if task.get("id", "").upper() == task_id.upper():
            if task.get("status") == "completed":
                return f"ℹ️  La tarea {task_id} ya estaba marcada como completada."
            task["status"] = "completed"
            task["completed_at"] = datetime.now().isoformat(timespec="seconds")
            found = True
            break

    if not found:
        available = [t.get("id") for t in tasks]
        return f"❌ No encontré la tarea '{task_id}'. Tareas disponibles: {available}"

    update_task_status(task_id, "completed")
    return f"✅ Tarea {task_id} marcada como completada."


# ─────────────────────────────────────────────
# Tool: actualizar work_state  (Fase 2)
# ─────────────────────────────────────────────

def parse_work_state_update(text: str) -> tuple[str | None, str | None]:
    """Extrae (field, value) de una frase de actualización de work_state."""
    text_lower = text.lower()

    detected_field: str | None = None
    for alias in sorted(WORK_STATE_FIELD_ALIASES, key=len, reverse=True):
        if alias in text_lower:
            detected_field = WORK_STATE_FIELD_ALIASES[alias]
            break

    if not detected_field:
        for field in ALLOWED_WORK_STATE_FIELDS:
            if field in text_lower:
                detected_field = field
                break

    if not detected_field:
        return None, None

    patterns = [
        r"(?:a|al|en|hacia|por)\s+(.+?)(?:\s*[.!?]|$)",
        r"[:=]\s*(.+?)(?:\s*[.!?]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip().strip("\"'")
            value_lower = value.lower()
            for prefix in sorted(_VALUE_PREFIXES, key=len, reverse=True):
                if value_lower.startswith(prefix):
                    value = value[len(prefix):].strip()
                    break
            if value:
                return detected_field, value

    return detected_field, None


def tool_update_work_state(field: str, value: str) -> str:
    """Actualiza un campo específico de work_state.json desde conversación."""
    if field not in ALLOWED_WORK_STATE_FIELDS:
        return (
            f"❌ Campo '{field}' no permitido.\n"
            f"Campos disponibles: {sorted(ALLOWED_WORK_STATE_FIELDS)}"
        )
    if not value or not value.strip():
        return "No pude actualizar: el valor está vacío."

    update_work_state(field, value.strip())
    return f"✅ work_state actualizado: {field} → '{value.strip()}'"
