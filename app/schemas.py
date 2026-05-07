"""Schemas TypedDict — Nivel 2 del plan de contratos

Qué es esto:
  Define la forma exacta de cada archivo JSON que usa el proyecto.
  Es la "fuente de verdad" sobre qué claves existen y de qué tipo son.

Por qué importa:
  Sin esto, tools.py puede escribir 'last_completed' y memory_store.py
  puede leer 'last_completed_step' — el mismo bug que ya tuvimos.
  Con esto, el IDE y mypy detectan la desalineación al escribir el código.

Cómo usarlo:
  Importar el TypedDict correspondiente en el módulo que lee/escribe ese JSON:

    from app.schemas import WorkState, TaskItem

  Para validar en runtime (opcional):
    from app.schemas import validate_work_state
    warnings = validate_work_state(data)

Archivos JSON y sus schemas:
  storage/work_state.json      →  WorkState
  storage/tasks.json           →  TasksFile  (contiene lista de TaskItem)
  storage/profile.json         →  ProfileData
  storage/memory.json          →  MemoryFile  (contiene lista de Message)
  storage/project_facts.json   →  dict[str, str]  (clave libre = valor str)
  storage/episodic_memory.json →  EpisodicMemory  (contiene lista de EpisodeItem)

Nota sobre TypedDict y total=False:
  Los campos marcados como opcional (con total=False en la subclase)
  pueden estar ausentes en el JSON. Los campos en la clase base con
  total=True son obligatorios.
"""
from __future__ import annotations

from typing import TypedDict


# ─────────────────────────────────────────────
# storage/work_state.json
# ─────────────────────────────────────────────

class WorkStateRequired(TypedDict, total=True):
    """Campos obligatorios de work_state.json."""
    current_focus: str          # qué está haciendo el usuario ahora
    next_step: str              # cuál es el siguiente paso registrado
    last_completed: str         # último paso completado con fecha


class WorkState(WorkStateRequired, total=False):
    """Schema completo de storage/work_state.json.

    Campos opcionales (pueden estar ausentes en archivos antiguos):
    """
    current_phase: str          # fase del proyecto (ej: 'fase_4')
    last_completed_step: str    # alias legacy — usar last_completed en código nuevo
    current_blockers: list[str] # lista de bloqueantes activos
    session_goal: str           # objetivo de la sesión actual
    notes: list[str]            # notas libres
    last_updated: str           # timestamp de última escritura (YYYY-MM-DD HH:MM)


# Conjunto de claves permitidas — usado por validate_work_state()
_WORK_STATE_KNOWN_KEYS = {
    "current_focus", "next_step", "last_completed",
    "current_phase", "last_completed_step",
    "current_blockers", "session_goal", "notes", "last_updated",
}


def validate_work_state(data: dict) -> list[str]:
    """Detecta claves inesperadas en un dict de work_state.

    Args:
        data: dict leído desde work_state.json.

    Returns:
        Lista de strings con advertencias. Lista vacía = sin problemas.

    Never raises.
    """
    warnings: list[str] = []
    unknown = set(data.keys()) - _WORK_STATE_KNOWN_KEYS
    if unknown:
        warnings.append(f"[schemas:warn] claves desconocidas en work_state: {sorted(unknown)}")
    return warnings


# ─────────────────────────────────────────────
# storage/tasks.json
# ─────────────────────────────────────────────

class TaskItemRequired(TypedDict, total=True):
    """Campos obligatorios de cada tarea en tasks.json."""
    id: str          # formato T-MMDDHHMISS  (ej: T-0506132952)
    title: str       # descripción de la tarea
    status: str      # 'pending' | 'completed'
    priority: str    # 'low' | 'medium' | 'high'
    created_at: str  # ISO 8601 (ej: 2026-05-06T13:29:52)


class TaskItem(TaskItemRequired, total=False):
    """Schema completo de un item de tarea."""
    notes: str          # notas adicionales
    completed_at: str   # ISO 8601 — solo presente cuando status='completed'


class TasksFile(TypedDict):
    """Schema de storage/tasks.json (nivel raíz)."""
    tasks: list[TaskItem]


# ─────────────────────────────────────────────
# storage/profile.json
# ─────────────────────────────────────────────

class ProfileData(TypedDict, total=False):
    """Schema de storage/profile.json.

    Todo optional porque el archivo puede crecer con claves nuevas
    a medida que el usuario interactúa con Lautaro.
    """
    name: str               # nombre del usuario (ej: 'José')
    level: str              # nivel técnico (ej: 'junior')
    project: str            # nombre del proyecto principal
    preferred_style: str    # estilo de respuesta preferido
    preferred_flow: str     # flujo de explicación preferido


# ─────────────────────────────────────────────
# storage/memory.json  (memoria de conversación corta)
# ─────────────────────────────────────────────

class Message(TypedDict):
    """Schema de cada mensaje en storage/memory.json."""
    role: str        # 'user' | 'assistant'
    content: str     # texto del mensaje
    timestamp: str   # ISO 8601 (ej: 2026-05-07T14:03:22)


class MemoryFile(TypedDict):
    """Schema de storage/memory.json (nivel raíz)."""
    messages: list[Message]


# ─────────────────────────────────────────────
# storage/episodic_memory.json
# ─────────────────────────────────────────────

class EpisodeItem(TypedDict):
    """Schema de cada episodio en storage/episodic_memory.json."""
    date: str        # YYYY-MM-DD
    time: str        # HH:MM
    turns: int       # número de turnos en la sesión
    summary: str     # resumen generado por el LLM al cerrar la sesión


class EpisodicMemory(TypedDict):
    """Schema de storage/episodic_memory.json (nivel raíz)."""
    episodes: list[EpisodeItem]


# ─────────────────────────────────────────────
# project_facts.json — no necesita TypedDict
# ─────────────────────────────────────────────
# project_facts.json tiene claves libres (el usuario inventa el nombre del hecho).
# Por eso su tipo es simplemente:  dict[str, str]
# No hay TypedDict para él — eso es correcto y no es un bug.

# Alias para documentar la intención en firmas de funciones:
ProjectFacts = dict  # dict[str, str] en runtime
