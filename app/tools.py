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

# Directorios permitidos para leer/listar archivos.
# PROJECT_ROOT incluye archivos .py de la raíz (chat.py, build_intent_index.py, etc.).
# SKIP_DIR_NAMES y SKIP_SUFFIXES se encargan de filtrar .venv, __pycache__, etc.
ALLOWED_DIRS = [
    PROJECT_ROOT / "app",
    PROJECT_ROOT / "data" / "docs",
    PROJECT_ROOT / "storage",
    PROJECT_ROOT,   # raíz: permite leer chat.py, requirements.txt, etc.
]


SKIP_DIR_NAMES = {
    "__pycache__", ".git", ".venv", "chroma_db", "chroma",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", ".idea", ".vscode",
}
SKIP_SUFFIXES = {".pyc", ".bak", ".log"}
VALID_PRIORITIES = {"low", "medium", "high"}

# Extensiones permitidas para listar/leer desde la raíz.
# Evita exponer archivos binarios o sensibles.
ROOT_ALLOWED_SUFFIXES = {
    ".py", ".md", ".txt", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".json",
}


# Campos permitidos para actualizar work_state (lista blanca de seguridad)
ALLOWED_WORK_STATE_FIELDS = {
    "current_focus",
    "current_phase",
    "last_completed",
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
    """Verifica si la ruta está dentro de los directorios permitidos.
    Para archivos en la raíz del proyecto, aplica filtro de extensiones.
    """
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
            # Si el archivo está directamente en la raíz (no en subcarpeta permitida),
            # aplicar filtro de extensiones para evitar exponer archivos binarios.
            if base_resolved == root_resolved:
                # Verificar que no esté en una subcarpeta excluida
                try:
                    rel = resolved.relative_to(root_resolved)
                except ValueError:
                    continue
                # Solo archivos directamente en la raíz o en subcarpetas no excluidas
                parts = rel.parts
                if len(parts) > 1 and parts[0] in SKIP_DIR_NAMES:
                    continue
                # Filtro de extensión para archivos de la raíz
                if resolved.suffix not in ROOT_ALLOWED_SUFFIXES:
                    continue
            return True
    return False



def _should_skip(path: Path) -> bool:
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return True
    if path.suffix in SKIP_SUFFIXES:
        return True
    return False



def list_project_files() -> list[str]:
    """Lista archivos del proyecto. Para la raíz solo muestra extensiones permitidas."""
    seen = set()
    files = []
    root_resolved = PROJECT_ROOT.resolve()

    for base in ALLOWED_DIRS:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if _should_skip(p):
                continue
            if not p.is_file():
                continue
            # Para archivos en la raíz aplicar filtro de extensión
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
    """Extrae una ruta de archivo del texto del usuario.
    Detecta rutas con prefijo de carpeta conocida O nombres de archivo .py solos.
    """
    cleaned = text.strip()
    lower_text = cleaned.lower()

    # Primero: detectar rutas con prefijo de carpeta
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

    # Segundo: detectar nombre de archivo .py solo (sin ruta)
    # Ejemplo: "lee router.py" o "muéstrame chat.py"
    match = re.search(r'\b([\w_.-]+\.(?:py|md|txt|toml|yaml|yml|json))\b', cleaned, re.IGNORECASE)
    if match:
        filename = match.group(1)
        # Buscar el archivo en las carpetas conocidas
        for base in [PROJECT_ROOT / "app", PROJECT_ROOT, PROJECT_ROOT / "data" / "docs"]:
            candidate = base / filename
            if candidate.exists():
                return str(candidate.relative_to(PROJECT_ROOT))
        # Si no existe, devolver solo el nombre para que read_project_file genere error claro
        return filename

    return None



def read_project_file(path: str, max_chars: int = 8000) -> str:
    p = Path(path)
    if not _is_allowed(p):
        return f"Ruta no permitida: '{path}'. Usa archivos dentro de app/, data/docs/, storage/ o la raíz del proyecto (.py, .md, .txt, .toml, .json)."
    if not p.exists() or not p.is_file():
        return f"Archivo no encontrado: '{path}'."
    text = p.read_text(encoding="utf-8", errors="ignore")
    return text[:max_chars]



# ─────────────────────────────────────────────
# Tools de escritura seguras
# ─────────────────────────────────────────────


def _parse_key_value(content: str) -> tuple[str, str] | None:
    """Detecta si el contenido tiene formato 'clave = valor' o 'clave=valor'.

    Si lo tiene, devuelve (clave_normalizada, valor).
    Si no, devuelve None — la llamada usará hecho_timestamp como antes.
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

    key = re.sub(r'\s+', '_', raw_key.lower())

    if len(key.split('_')) > 5:
        return None

    return key, value


def tool_save_fact(content: str) -> str:
    """Guarda un hecho en project_facts.json.

    IMPORTANTE: esta función recibe el contenido YA limpio (sin prefijos).
    Los prefijos ('anota que', 'registra que', etc.) se extraen en chat_core.py
    antes de llamar a esta función. No extraer prefijos aquí para evitar
    doble extracción que trunca el texto guardado.
    """
    content = content.strip()

    if not content:
        return "No pude guardar el hecho: no entendí el contenido."

    kv = _parse_key_value(content)
    if kv:
        key, value = kv
        save_project_fact(key, value)
        return f"✓ Hecho guardado: {key} = \"{value}\""

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



def tool_update_work_state(
    texto: str = "",
    *,
    current_focus: str | None = None,
    next_step: str | None = None,
    last_completed_step: str | None = None,
) -> str:
    """Actualiza work_state.json desde conversación libre o desde kwargs directos.

    Hay dos modos de uso:

    Modo A — texto libre (comportamiento original, usado por chat_core.py):
        tool_update_work_state("actualiza el foco a fase 4")

    Modo B — kwargs directos (usado por memory_extractor, futuro):
        tool_update_work_state(next_step="escribir tests de consolidación")
        tool_update_work_state(current_focus="fase 4", next_step="refactorizar router")

    En Modo B los kwargs tienen prioridad sobre el texto libre.
    Si se pasan ambos, primero se aplican los kwargs y luego se parsea el texto.

    Args:
        texto:               Frase libre del usuario (por defecto "").
        current_focus:       Valor directo para current_focus.
        next_step:           Valor directo para next_step.
        last_completed_step: Valor directo para last_completed (se añade fecha automáticamente).

    Returns:
        str con confirmación de los campos actualizados,
        o mensaje de advertencia si no se detectó ningún cambio.

    Never raises: errores de lectura/escritura se capturan internamente.
    """
    import json

    path = Path("storage/work_state.json")
    try:
        state: dict = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        state = {}

    cambios: list[str] = []

    # ── Modo B: kwargs directos ────────────────────────────────
    if current_focus is not None:
        val = current_focus.strip()
        state["current_focus"] = val
        cambios.append(f"current_focus → '{val}'")

    if next_step is not None:
        val = next_step.strip()
        state["next_step"] = val
        cambios.append(f"next_step → '{val}'")

    if last_completed_step is not None:
        val = last_completed_step.strip()
        fecha = datetime.now().strftime("%d/%m/%Y")
        state["last_completed"] = f"{val} — {fecha}"
        cambios.append(f"last_completed → '{val}'")

    # ── Modo A: texto libre (solo si no hubo kwargs o hay texto adicional) ─
    if texto:
        texto_lower = texto.lower()

        # current_focus
        if current_focus is None:
            patrones_foco = [r"(?:actualiza el foco a|foco(?:\s+es)?(?:\s*:)?|enf[oó]cate en)\s+(.+)"]
            for pat in patrones_foco:
                m = re.search(pat, texto_lower)
                if m:
                    valor = m.group(1).strip().rstrip(".,")
                    state["current_focus"] = valor
                    cambios.append(f"current_focus → '{valor}'")
                    break

        # last_completed
        if last_completed_step is None:
            patrones_completado = [
                r"(?:complet[eé]|termin[eé]|acab[eé]|ya hice|ya termin[eé]|logramos|listo)\s+(?:de\s+|con\s+)?(.+)"
            ]
            for pat in patrones_completado:
                m = re.search(pat, texto_lower)
                if m:
                    valor = m.group(1).strip().rstrip(".,")
                    fecha = datetime.now().strftime("%d/%m/%Y")
                    state["last_completed"] = f"{valor} — {fecha}"
                    cambios.append(f"last_completed → '{valor}'")
                    break

        # next_step
        if next_step is None:
            patrones_siguiente = [
                r"(?:el siguiente paso es|siguiente paso[:\s]+|sigue[:\s]+|pr[oó]ximo paso[:\s]+)\s+(.+)"
            ]
            for pat in patrones_siguiente:
                m = re.search(pat, texto_lower)
                if m:
                    valor = m.group(1).strip().rstrip(".,")
                    state["next_step"] = valor
                    cambios.append(f"next_step → '{valor}'")
                    break

    if not cambios:
        return "⚠️ No entendí qué campo actualizar. Usa: 'foco a X', 'completé X' o 'siguiente paso es X'."

    state["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return f"⚠️ Cambios detectados pero no pude escribir work_state.json: {e}"

    return "✅ work_state actualizado:\n" + "\n".join(f"  • {c}" for c in cambios)


# ─────────────────────────────────────────────
# Sugerencia automática post-actualización
# ─────────────────────────────────────────────

def suggest_next_step() -> str:
    """
    Lee work_state.json y tasks.json y devuelve
    una sugerencia breve del siguiente paso lógico.
    Se llama desde chat_core.py después de tool_update_work_state.
    """
    import json

    ws_path = Path("storage/work_state.json")
    state = json.loads(ws_path.read_text(encoding="utf-8")) if ws_path.exists() else {}

    next_step     = state.get("next_step", "")
    current_focus = state.get("current_focus", "")
    last_done     = state.get("last_completed", "")

    tasks_data = load_tasks()
    pending = [
        t for t in tasks_data.get("tasks", [])
        if t.get("status") not in ("done", "completed")
    ]

    lines = ["", "─── Sugerencia post-actualización ───"]

    if next_step:
        lines.append(f"  ➡️  Siguiente paso registrado: {next_step}")
    elif pending:
        t = pending[0]
        lines.append(
            f"  ➡️  Tarea pendiente: [{t['id']}] {t['title']} "
            f"({t.get('priority', 'medium')})"
        )
    else:
        lines.append("  ➡️  No hay pasos ni tareas pendientes registradas.")

    if current_focus:
        lines.append(f"  🎯  Foco actual: {current_focus}")

    if last_done:
        lines.append(f"  ✅  Último completado: {last_done}")

    return "\n".join(lines)
