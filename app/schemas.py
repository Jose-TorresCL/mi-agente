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

  Para validar al arrancar (detecta corrupción de archivos):
    from app.schemas import validate_storage
    validate_storage()   # imprime advertencias si hay claves desconocidas

Archivos JSON y sus schemas:
  storage/work_state.json      →  WorkState
  storage/tasks.json           →  TasksFile  (contiene lista de TaskItem)
  storage/profile.json         →  ProfileData
  storage/memory.json          →  MemoryFile  (contiene lista de Message)
  storage/project_facts.json   →  dict[str, str]  (clave libre = valor str)
  storage/episodic_memory.json →  EpisodicMemory  (contiene lista de EpisodeItem)

Contratos de retorno internos (R1-A):
  process_turn()    →  tuple[str, list]  (ver DecisionResult para estructura semántica)
  _decide_rag()     →  RagResult
  DecisionResult    →  TypedDict con los campos semánticos de cada respuesta interna

Nota sobre TypedDict y total=False:
  Los campos marcados como opcional (con total=False en la subclase)
  pueden estar ausentes en el JSON. Los campos en la clase base con
  total=True son obligatorios.
"""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, TypedDict


# ───────────────────────────────────────────────
# MemoryType — clasificación de capas de memoria (8D)
# ───────────────────────────────────────────────

class MemoryType(str, Enum):
    """Clasificación de capas de memoria del agente.

    Usada para anotar funciones en memory_manager.py y como contrato
    explícito sobre qué tipo de memoria accede cada función.

    Valores:
        WORKING:    Memoria de trabajo — contexto operacional de la sesión
                    activa. Incluye work_state y tareas pendientes.
                    Volátil: cambia turno a turno.

        SEMANTIC:   Memoria semántica — hechos estables del proyecto y
                    perfil del usuario. Persistente entre sesiones.

        EPISODIC:   Memoria episódica — resúmenes de sesiones anteriores.
                    Permite recuperar qué se hizo en el pasado.

        PROCEDURAL: Memoria procedimental — reglas, herramientas y
                    comportamientos del agente (tool_registry, prompts).
                    No se lee en tiempo de ejecución de memoria — es el
                    propio código del agente.

    Ejemplo de uso en memory_manager.py:
        def get_working_context() -> str:  # MemoryType: WORKING
            ...
    """
    WORKING    = "working"
    SEMANTIC   = "semantic"
    EPISODIC   = "episodic"
    PROCEDURAL = "procedural"


# ───────────────────────────────────────────────
# DecisionResult — contrato de retorno interno (R1-A)
# ───────────────────────────────────────────────

class DecisionResult(TypedDict, total=False):
    """Contrato semántico del retorno de process_turn().

    process_turn() sigue devolviendo tuple[str, list] en runtime para no
    romper el contrato público actual. Este TypedDict documenta la
    semántica de cada respuesta y se usará para tipar diccionarios de
    metadatos internos cuando se necesite pasar más información entre capas.

    Campos:
        route:       Carril elegido por el router.
                     Valores: "rag", "memory", "tool_*", "episode",
                               "unsupported", "exit"
        response:    Texto final generado para el usuario.
        cached:      True si la respuesta se sirvió desde caché semántica.
        source:      Origen de la respuesta:
                       "cache"   — caché semántica
                       "chroma"  — recuperación RAG
                       "json"    — memoria estructurada (JSON)
                       "tool"    — tool registrada
                       "llm"     — LLM sin RAG
                       "direct"  — respuesta directa sin modelo
        source_docs: Lista de documentos recuperados (puede estar vacía).
        retrieval_ms: Tiempo de recuperación en milisegundos.
        llm_ms:      Tiempo de generación LLM en milisegundos.
        tokens_est:  Estimación de tokens generados.
        metadata:    Diccionario opcional para datos adicionales.
    """
    route:        str
    response:     str
    cached:       bool
    source:       str
    source_docs:  list
    retrieval_ms: int
    llm_ms:       int
    tokens_est:   int
    metadata:     dict[str, Any]


class RagResult(TypedDict):
    """Contrato de retorno de _decide_rag() en intelligence.py.

    Permite tipar el retorno de la función interna RAG sin cambiar
    su firma pública hasta que se haga una refactorización mayor.

    Campos:
        answer:       Texto generado por el LLM (o mensaje de error de fidelidad).
        source_docs:  Lista de documentos recuperados de Chroma.
        retrieval_ms: Tiempo de recuperación Chroma en milisegundos.
        llm_ms:       Tiempo de generación LLM en milisegundos.
        cached:       True si la respuesta vino del caché semántico.
    """
    answer:       str
    source_docs:  list
    retrieval_ms: int
    llm_ms:       int
    cached:       bool


# ───────────────────────────────────────────────
# storage/work_state.json
# ───────────────────────────────────────────────

class WorkStateRequired(TypedDict, total=True):
    """Campos obligatorios de work_state.json."""
    current_focus: str
    next_step: str
    last_completed: str


class WorkState(WorkStateRequired, total=False):
    """Schema completo de storage/work_state.json."""
    current_phase: str
    last_completed_step: str    # alias legacy — usar last_completed en código nuevo
    current_blockers: list[str]
    session_goal: str
    notes: list[str]
    last_updated: str
    last_session: str           # legacy — generado por versiones anteriores del código


_WORK_STATE_KNOWN_KEYS = {
    "current_focus", "next_step", "last_completed",
    "current_phase", "last_completed_step",
    "current_blockers", "session_goal", "notes", "last_updated",
    "last_session",  # legacy — presente en work_state.json de sesiones anteriores
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
        warnings.append(
            f"[schemas:warn] claves desconocidas en work_state: {sorted(unknown)}"
        )
    return warnings


# ───────────────────────────────────────────────
# storage/tasks.json
# ───────────────────────────────────────────────

class TaskItemRequired(TypedDict, total=True):
    """Campos obligatorios de cada tarea."""
    id: str
    title: str
    status: str
    priority: str
    created_at: str


class TaskItem(TaskItemRequired, total=False):
    """Schema completo de un item de tarea en tasks.json."""
    notes: str
    completed_at: str


class TasksFile(TypedDict):
    """Schema de storage/tasks.json (nivel raíz)."""
    tasks: list[TaskItem]


_TASK_KNOWN_KEYS = {"id", "title", "status", "priority", "created_at", "notes", "completed_at"}


# ───────────────────────────────────────────────
# storage/profile.json
# ───────────────────────────────────────────────

class ProfileData(TypedDict, total=False):
    """Schema de storage/profile.json (todo opcional — crece con el uso)."""
    name: str
    level: str
    project: str
    preferred_style: str
    preferred_flow: str


# ───────────────────────────────────────────────
# storage/memory.json
# ───────────────────────────────────────────────

class Message(TypedDict):
    """Schema de cada mensaje en storage/memory.json."""
    role: str
    content: str
    timestamp: str


class MemoryFile(TypedDict):
    """Schema de storage/memory.json (nivel raíz)."""
    messages: list[Message]


# Claves conocidas de Message — al nivel de módulo para reutilización
_MSG_KNOWN_KEYS = {"role", "content", "timestamp"}


# ───────────────────────────────────────────────
# storage/episodic_memory.json
# ───────────────────────────────────────────────

class EpisodeItemRequired(TypedDict, total=True):
    """Campos obligatorios de cada episodio en episodic_memory.json."""
    date: str
    time: str
    turns: int
    summary: str


class EpisodeItem(EpisodeItemRequired, total=False):
    """Schema completo de cada episodio en episodic_memory.json.

    Los campos opcionales (total=False) son escritos por episode_store.py
    al indexar y cerrar sesión (8C):
        carril_dominante:   carril más usado en la sesión.
        tareas_completadas: número de tareas completadas en la sesión.
        exitoso:            "true" | "false" | "unmarked" — resultado de la sesión.
    """
    carril_dominante:   str
    tareas_completadas: int
    exitoso:            str   # "true" | "false" | "unmarked"


class EpisodicMemory(TypedDict):
    """Schema de storage/episodic_memory.json (nivel raíz)."""
    episodes: list[EpisodeItem]


# Claves conocidas de EpisodeItem — al nivel de módulo para reutilización
_EP_KNOWN_KEYS = {
    "date", "time", "turns", "summary",
    # campos opcionales escritos por episode_store.py (8C)
    "carril_dominante", "tareas_completadas", "exitoso",
}


# ───────────────────────────────────────────────
# project_facts.json — no necesita TypedDict
# ───────────────────────────────────────────────
# project_facts.json tiene claves libres (el usuario inventa el nombre del hecho).
# Por eso su tipo es simplemente:  dict[str, str]
# No hay TypedDict para él — eso es correcto y no es un bug.
ProjectFacts = dict  # dict[str, str] en runtime


# ───────────────────────────────────────────────
# validate_storage() — test de arranque
# ───────────────────────────────────────────────

_STORAGE_DIR = Path("storage")


def _load_json_safe(path: Path) -> dict | list | None:
    """Lee un JSON sin lanzar excepciones.

    Returns:
        El objeto parseado, o None si el archivo no existe o tiene error.

    Never raises.
    """
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def validate_storage() -> list[str]:
    """Lee los archivos JSON de storage/ y detecta claves desconocidas.

    Verifica:
      - storage/work_state.json  contra WorkState
      - storage/tasks.json       contra TaskItem (por cada tarea)
      - storage/memory.json      contra Message (por cada mensaje)
      - storage/episodic_memory.json  contra EpisodeItem
      - storage/profile.json     (solo avisa si no es dict)

    Returns:
        Lista de strings con advertencias. Lista vacía = todo limpio.
        También imprime cada advertencia en consola.

    Never raises.

    Uso rápido:
        python -c "from app.schemas import validate_storage; validate_storage()"
    """
    warnings: list[str] = []

    # ─ work_state.json ──────────────────────────────────────────────
    ws = _load_json_safe(_STORAGE_DIR / "work_state.json")
    if ws is None:
        warnings.append("[storage] work_state.json no existe aún (normal en primera ejecución)")
    elif isinstance(ws, dict):
        warnings.extend(validate_work_state(ws))
    else:
        warnings.append("[storage:error] work_state.json no es un objeto JSON válido")

    # ─ tasks.json ────────────────────────────────────────────────
    tasks_file = _load_json_safe(_STORAGE_DIR / "tasks.json")
    if tasks_file is None:
        warnings.append("[storage] tasks.json no existe aún (normal en primera ejecución)")
    elif isinstance(tasks_file, dict):
        for i, task in enumerate(tasks_file.get("tasks", [])):
            if isinstance(task, dict):
                unknown = set(task.keys()) - _TASK_KNOWN_KEYS
                if unknown:
                    warnings.append(
                        f"[storage:warn] task[{i}] claves desconocidas: {sorted(unknown)}"
                    )
    else:
        warnings.append("[storage:error] tasks.json no es un objeto JSON válido")

    # ─ memory.json ───────────────────────────────────────────────
    memory_file = _load_json_safe(_STORAGE_DIR / "memory.json")
    if memory_file is None:
        warnings.append("[storage] memory.json no existe aún (normal en primera ejecución)")
    elif isinstance(memory_file, dict):
        for i, msg in enumerate(memory_file.get("messages", [])):
            if isinstance(msg, dict):
                unknown = set(msg.keys()) - _MSG_KNOWN_KEYS
                if unknown:
                    warnings.append(
                        f"[storage:warn] message[{i}] claves desconocidas: {sorted(unknown)}"
                    )
    else:
        warnings.append("[storage:error] memory.json no es un objeto JSON válido")

    # ─ episodic_memory.json ───────────────────────────────────────
    ep_file = _load_json_safe(_STORAGE_DIR / "episodic_memory.json")
    if ep_file is None:
        warnings.append("[storage] episodic_memory.json no existe aún (normal en primera ejecución)")
    elif isinstance(ep_file, dict):
        for i, ep in enumerate(ep_file.get("episodes", [])):
            if isinstance(ep, dict):
                unknown = set(ep.keys()) - _EP_KNOWN_KEYS
                if unknown:
                    warnings.append(
                        f"[storage:warn] episode[{i}] claves desconocidas: {sorted(unknown)}"
                    )
    else:
        warnings.append("[storage:error] episodic_memory.json no es un objeto JSON válido")

    # ─ profile.json ───────────────────────────────────────────────
    profile = _load_json_safe(_STORAGE_DIR / "profile.json")
    if profile is None:
        warnings.append("[storage] profile.json no existe aún (normal en primera ejecución)")
    elif not isinstance(profile, dict):
        warnings.append("[storage:error] profile.json no es un objeto JSON válido")

    # ─ Reporte final ──────────────────────────────────────────────
    if warnings:
        for w in warnings:
            print(w)
    else:
        print("[storage] ✅ Todos los archivos JSON son válidos.")

    return warnings
