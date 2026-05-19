"""Estado efímero de la sesión actual.

Acumula métricas durante la conversación para enriquecer el episodio
al cerrar la sesión (8C).

No persiste a disco — solo existe en RAM durante el proceso.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime

from app.memory_store import load_work_state, load_tasks

# ─────────────────────────────────────────────
# Estado mutable de sesión
# ─────────────────────────────────────────────

_carril_counts: Counter = Counter()   # cuántas veces se usó cada carril
_tareas_completadas: int = 0          # tareas marcadas done en esta sesión
_session_start: str = datetime.now().strftime("%Y-%m-%dT%H:%M")


def track_turn(carril: str, tareas_nuevas: int = 0) -> None:
    """Registra un turno: incrementa contador del carril y tareas completadas.

    Llamar desde intelligence.process_turn() después de cada respuesta.

    Args:
        carril:        Nombre del carril usado ('rag', 'memory', 'episode', etc.)
        tareas_nuevas: Número de tareas marcadas done en este turno (default 0).
    """
    _carril_counts[carril] += 1
    global _tareas_completadas
    _tareas_completadas += tareas_nuevas


def get_carril_dominante() -> str:
    """Devuelve el carril más utilizado en la sesión.

    Returns:
        Nombre del carril más frecuente, o 'unknown' si no hay turnos.
    """
    if not _carril_counts:
        return "unknown"
    return _carril_counts.most_common(1)[0][0]


def get_tareas_completadas() -> int:
    """Devuelve el número de tareas completadas en la sesión."""
    return _tareas_completadas


def get_session_doc_id() -> str:
    """Devuelve el doc_id del episodio activo (formato 'YYYY-MM-DDTHH:MM').

    Este ID coincide con el que episode_store genera al indexar el episodio
    al inicio de la sesión.

    Returns:
        str — ID del episodio actual.
    """
    return _session_start


# ─────────────────────────────────────────────
# Snapshot de estado de trabajo (sin cambios)
# ─────────────────────────────────────────────

def get_session_snapshot() -> dict:
    work_state = load_work_state()
    tasks = load_tasks().get("tasks", [])

    pending_tasks = [t for t in tasks if t.get("status") != "done"]

    return {
        "current_focus":       work_state.get("current_focus", ""),
        "last_completed_step": work_state.get("last_completed_step", ""),
        "next_step":           work_state.get("next_step", ""),
        "pending_tasks":       pending_tasks[:5],
    }
