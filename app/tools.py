from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(".")
ALLOWED_DIRS = [
    PROJECT_ROOT / "app",
    PROJECT_ROOT / "data" / "docs",
    PROJECT_ROOT / "storage"
]

SKIP_DIR_NAMES = {"__pycache__", ".git", ".venv", "chroma_db","chroma", ".pytest_cache",".mypy_cache",".ruff_cache",}
SKIP_SUFFIXES = {".pyc"}

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

    markers = [
        "data/",
        "data\\",
        "app/",
        "app\\",
        "storage/",
        "storage\\",
    ]

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