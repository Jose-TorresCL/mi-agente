# app/tools.py
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(".")
ALLOWED_DIRS = [
    PROJECT_ROOT / "app",
    PROJECT_ROOT / "data" / "docs",
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

def list_project_files() -> list[str]:
    files = []
    for base in ALLOWED_DIRS:
        if base.exists():
            for p in base.rglob("*"):
                if p.is_file():
                    files.append(str(p))
    return sorted(files)

def read_project_file(path: str, max_chars: int = 8000) -> str:
    p = Path(path)
    if not _is_allowed(p):
        return "Ruta no permitida."

    if not p.exists() or not p.is_file():
        return "Archivo no encontrado."

    text = p.read_text(encoding="utf-8", errors="ignore")
    return text[:max_chars]