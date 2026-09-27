"""Estado efímero de la sesión actual.

Acumula métricas durante la conversación para enriquecer el episodio
al cerrar la sesión (8C).

No persiste a disco — solo existe en RAM durante el proceso.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from app.memory_store import load_work_state, load_tasks

@dataclass(slots=True)
class SessionState:
    """Estado efímero de una sesión de chat en RAM."""

    started_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%dT%H:%M")
    )
    carril_counts: Counter = field(default_factory=Counter)
    tareas_completadas: int = 0
    turns: int = 0

    def track_turn(self, carril: str, tareas_nuevas: int = 0) -> None:
        self.carril_counts[carril] += 1
        self.tareas_completadas += tareas_nuevas
        self.turns += 1

    def get_carril_dominante(self) -> str:
        if not self.carril_counts:
            return "unknown"
        return self.carril_counts.most_common(1)[0][0]

    def get_tareas_completadas(self) -> int:
        return self.tareas_completadas

    def get_session_doc_id(self) -> str:
        return self.started_at

    def get_snapshot(self) -> dict:
        work_state = load_work_state()
        tasks = load_tasks().get("tasks", [])
        pending_tasks = [t for t in tasks if t.get("status") != "done"]
        return {
            "current_focus": work_state.get("current_focus", ""),
            "last_completed_step": work_state.get("last_completed_step", ""),
            "next_step": work_state.get("next_step", ""),
            "pending_tasks": pending_tasks[:5],
        }
_legacy_session = SessionState()

def track_turn(carril: str, tareas_nuevas: int = 0) -> None:
    """Registra un turno: incrementa contador del carril y tareas completadas.

    Llamar desde intelligence.process_turn() después de cada respuesta.

    Args:
        carril:        Nombre del carril usado ('rag', 'memory', 'episode', etc.)
        tareas_nuevas: Número de tareas marcadas done en este turno (default 0).
    """
    _legacy_session.track_turn(carril, tareas_nuevas)



def get_carril_dominante() -> str:
    """Devuelve el carril más utilizado en la sesión.

    Returns:
        Nombre del carril más frecuente, o 'unknown' si no hay turnos.
    """
    return _legacy_session.get_carril_dominante()


def get_tareas_completadas() -> int:
    """Devuelve el número de tareas completadas en la sesión."""
    return _legacy_session.get_tareas_completadas()


def get_session_doc_id() -> str:
    """Devuelve el doc_id del episodio activo (formato 'YYYY-MM-DDTHH:MM').

    Este ID coincide con el que episode_store genera al indexar el episodio
    al inicio de la sesión.

    Returns:
        str — ID del episodio actual.
    """
    return _legacy_session.get_session_doc_id()


# ─────────────────────────────────────────────
# Snapshot de estado de trabajo (sin cambios)
# ─────────────────────────────────────────────

def get_session_snapshot() -> dict:
    return _legacy_session.get_snapshot()
