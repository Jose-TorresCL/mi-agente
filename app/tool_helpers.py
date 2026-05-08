"""Utilidades de parseo y filesystem para tools.py

Este módulo contiene funciones que NO modifican estado:
  - _is_allowed()          validación de rutas
  - _should_skip()         filtro para rglob
  - list_project_files()   listar archivos del proyecto
  - extract_file_path()    extraer ruta de texto libre
  - read_project_file()    leer archivo del proyecto
  - extract_task_id()      extraer ID de tarea de texto
  - _parse_key_value()     detectar formato 'clave = valor'
  - parse_work_state_update() extraer (field, value) de frase libre

Importar desde tools.py para no romper imports existentes.
"""
from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(".")

ALLOWED_DIRS = [
    PROJECT_ROOT / "app",
    PROJECT_ROOT / "data" / "docs",
    PROJECT_ROOT / "storage",
    PROJECT_ROOT,
]

SKIP_DIR_NAMES = {
    "__pycache__", ".git", ".venv", "chroma_db", "chroma",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", ".idea", ".vscode",
}
SKIP_SUFFIXES = {".pyc", ".bak", ".log"}

ROOT_ALLOWED_SUFFIXES = {
    ".py", ".md", ".txt", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".json",
}

ALLOWED_WORK_STATE_FIELDS = {
    "current_focus",
    "current_phase",
    "last_completed",
    "last_completed_step",
    "next_step",
    "current_blockers",
    "session_goal",
}

WORK_STATE_FIELD_ALIASES = {
    "foco":                   "current_focus",
    "foco actual":            "current_focus",
    "focus":                  "current_focus",
    "fase":                   "current_phase",
    "fase actual":            "current_phase",
    "phase":                  "current_phase",
    "último paso":            "last_completed",
    "ultimo paso":            "last_completed",
    "último paso completado": "last_completed",
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

_VALUE_PREFIXES = [
    "el foco a", "foco a", "la fase a", "fase a",
    "siguiente paso a", "el siguiente paso a",
    "último paso a", "el último paso a",
    "bloqueante a", "bloqueo a", "work_state a",
]


# ─────────────────────────────────────────────
# Filesystem helpers
# ─────────────────────────────────────────────

def _is_allowed(path: Path) -> bool:
    """Verifica si la ruta está dentro de los directorios permitidos."""
    try:
        resolved = path.resolve()
    except Exception:
        return False

    root_resolved = PROJECT_ROOT.resolve()

    for base in ALLOWED_DIRS:
        try:
            base_resolved = base.resolve()
            is_relative = resolved.is_relative_to(base_resolved)
        except AttributeError:
            base_resolved = base.resolve()
            is_relative = str(resolved).startswith(str(base_resolved))

        if is_relative:
            if base_resolved == root_resolved:
                try:
                    rel = resolved.relative_to(root_resolved)
                except ValueError:
                    continue
                parts = rel.parts
                if len(parts) > 1 and parts[0] in SKIP_DIR_NAMES:
                    continue
                if resolved.suffix not in ROOT_ALLOWED_SUFFIXES:
                    continue
            return True
    return False


def _should_skip(path: Path) -> bool:
    """Indica si una ruta debe omitirse al listar archivos del proyecto."""
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return True
    if path.suffix in SKIP_SUFFIXES:
        return True
    return False


def list_project_files() -> list[str]:
    """Lista archivos del proyecto dentro de los directorios permitidos."""
    seen: set[str] = set()
    files: list[str] = []
    root_resolved = PROJECT_ROOT.resolve()

    for base in ALLOWED_DIRS:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if _should_skip(p):
                continue
            if not p.is_file():
                continue
            try:
                base_resolved = base.resolve()
                if base_resolved == root_resolved:
                    if p.suffix not in ROOT_ALLOWED_SUFFIXES:
                        continue
            except Exception:
                pass
            rel = str(p.relative_to(PROJECT_ROOT))
            if rel not in seen:
                seen.add(rel)
                files.append(rel)
    return sorted(files)


def extract_file_path(text: str) -> str | None:
    """Extrae una ruta de archivo del texto del usuario."""
    cleaned = text.strip()
    lower_text = cleaned.lower()

    markers = ["data/", "data\\\\", "app/", "app\\\\", "storage/", "storage\\\\"]
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

    match = re.search(r'\b([\w_.-]+\.(?:py|md|txt|toml|yaml|yml|json))\b', cleaned, re.IGNORECASE)
    if match:
        filename = match.group(1)
        for base in [PROJECT_ROOT / "app", PROJECT_ROOT, PROJECT_ROOT / "data" / "docs"]:
            candidate = base / filename
            if candidate.exists():
                return str(candidate.relative_to(PROJECT_ROOT))
        return filename

    return None


def read_project_file(path: str, max_chars: int = 8000) -> str:
    """Lee un archivo del proyecto y devuelve su contenido como texto."""
    p = Path(path)
    if not _is_allowed(p):
        return (
            f"Ruta no permitida: '{path}'. "
            "Usa archivos dentro de app/, data/docs/, storage/ o la raíz del proyecto "
            "(.py, .md, .txt, .toml, .json)."
        )
    if not p.exists() or not p.is_file():
        return f"Archivo no encontrado: '{path}'."
    text = p.read_text(encoding="utf-8", errors="ignore")
    return text[:max_chars]


# ─────────────────────────────────────────────
# Parseo de tareas y work_state
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


def _parse_key_value(content: str) -> tuple[str, str] | None:
    """Detecta si el contenido tiene formato 'clave = valor' o 'clave=valor'.

    D3: retorna None si el valor detectado está vacío.
    """
    match = re.match(
        r'^([\w\s]{1,40}?)\s*[=:]\s*(.+)$',
        content.strip(),
        re.UNICODE,
    )
    if not match:
        return None

    raw_key = match.group(1).strip()
    value   = match.group(2).strip()

    # D3: rechazar valores vacíos
    if not value:
        return None

    key = re.sub(r'\s+', '_', raw_key.lower())
    if len(key.split('_')) > 5:
        return None

    return key, value


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
