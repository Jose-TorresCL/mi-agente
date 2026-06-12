"""Schemas TypedDict — Nivel 2 del plan de contratos

Qué es esto:
  Define la forma exacta de cada archivo JSON que usa el proyecto.
  Es la \"fuente de verdad\" sobre qué claves existen y de qué tipo son.

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

Contrato de retorno de tools (R6-A):
  ToolResult        →  TypedDict estructurado que reemplaza el str crudo de tools.py.
  RiskLevel         →  Enum con los niveles de riesgo de cada tool.
  dispatch_tool()   retorna ToolResult internamente; to_str() convierte para display.
  Compatibilidad:   dispatch_tool_str() mantiene la interfaz str para intelligence.py.

Contrato de entrada (TurnContext):
  TurnContext       →  TypedDict con los 4 parámetros de process_turn()
  Permite pasar el estado de turno como un dict tipado en lugar de
  4 argumentos posicionales sueltos. chat_core construye el TurnContext
  y lo pasa a process_turn() — que acepta ambas formas para compatibilidad.

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
# RiskLevel — clasificación de riesgo de tools (R6-A)
# ───────────────────────────────────────────────

class RiskLevel(str, Enum):
    """Nivel de riesgo de una tool.

    Determina si la tool puede ejecutarse directamente o requiere
    confirmación explícita del usuario antes de actuar.

    Valores:
        READ:     Solo lectura — no modifica ningún estado.
                  Ejemplos: tool_list_files, tool_read_file.
                  Puede ejecutarse siempre sin confirmación.

        WRITE:    Escribe en memoria interna del agente (JSON storage/).
                  Ejemplos: tool_save_fact, tool_create_task,
                            tool_complete_task, tool_update_work_state,
                            tool_set_session_goal.
                  Reversible con bajo riesgo — no requiere confirmación hoy,
                  pero queda clasificado para auditoría y métricas.

        SYSTEM:   Accede a recursos externos: filesystem del usuario,
                  red, procesos del sistema operativo.
                  Ejemplos: futura tool_run_shell, tool_write_file_external.
                  SIEMPRE requiere confirmación humana antes de ejecutar.
                  No hay tools SYSTEM en producción actualmente.

    Uso en tool_registry.py:
        TOOLS["tool_save_fact"]["risk"] = RiskLevel.WRITE

    Regla de seguridad:
        dispatch_tool() debe rechazar cualquier tool con risk=SYSTEM
        a menos que venga acompañada de confirmed=True en el contexto.
    """
    READ   = "read"
    WRITE  = "write"
    SYSTEM = "system"


# ───────────────────────────────────────────────
# ToolResult — contrato de retorno de tools (R6-A)
# ───────────────────────────────────────────────

class ToolResult(TypedDict, total=False):
    """Contrato estructurado de retorno de cada tool.

    Reemplaza el str crudo que tools.py devolvía antes de R6-A.
    Permite que el código downstream (intelligence.py, tests, métricas)
    detecte éxito/error de forma programática sin parsear emojis.

    Campos obligatorios (total=True en ToolResultRequired):
        ok:          True si la operación se completó con éxito.
        message:     Texto listo para mostrar al usuario (puede incluir emojis).

    Campos opcionales (total=False aquí):
        data:        Payload estructurado de la operación.
        side_effect: Descripción del efecto secundario producido.
        error_code:  Código de error legible por máquina (solo cuando ok=False).
        tool_name:   Nombre de la tool que generó este resultado.

    Never raises — el campo ok=False comunica errores sin excepciones.
    """
    ok:          bool
    message:     str
    data:        dict[str, Any]
    side_effect: str | None
    error_code:  str
    tool_name:   str


def tool_result_to_str(result: ToolResult) -> str:
    """Convierte un ToolResult a str para display o para retorno legado.

    Equivale a result["message"] con fallback seguro.
    Usar cuando el caller espera str (intelligence.py, tool_registry legado).

    Never raises.
    """
    return result.get("message", "[sin mensaje]")


# ───────────────────────────────────────────────
# TurnContext — contrato de entrada a process_turn()
# ───────────────────────────────────────────────

class TurnContext(TypedDict):
    """Contrato de entrada a process_turn()."""
    route:        str
    query:        str
    vectordb:     Any
    chat_history: list
    channel:      str


# ───────────────────────────────────────────────
# DecisionResult — contrato de retorno interno (R1-A)
# ───────────────────────────────────────────────

class DecisionResult(TypedDict, total=False):
    """Contrato semántico del retorno de process_turn()."""
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
    """Contrato de retorno de _decide_rag() en intelligence.py."""
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
    "last_session",
}


def validate_work_state(data: dict) -> list[str]:
    """Detecta claves inesperadas en un dict de work_state. Never raises."""
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
    """Schema completo de un item de tarea en tasks.json.

    Historial:
      - updated_at: agregado para alinear con campo real en disco
        (fix schemas 25/05/2026 — detectado por validate_storage).
    """
    notes:        str
    completed_at: str
    updated_at:   str   # timestamp de última modificación de la tarea


class TasksFile(TypedDict):
    """Schema de storage/tasks.json (nivel raíz)."""
    tasks: list[TaskItem]


_TASK_KNOWN_KEYS = {
    "id", "title", "status", "priority", "created_at",
    "notes", "completed_at", "updated_at",
}


# ───────────────────────────────────────────────
# storage/profile.json
# ───────────────────────────────────────────────

class ProfileData(TypedDict, total=False):
    """Schema de storage/profile.json (todo opcional — crece con el uso).

    Claves alineadas con las que memory_store.py escribe en disco
    y memory_context.py lee con .get().

    Historial:
      - name/level/project      → renombradas a user_name/user_level/project_type
        para coincidir con la realidad del JSON en disco (fix ProfileData).
      - avoid/environment/...   → campos reales en disco incorporados
        (fix schemas 25/05/2026 — detectados por validate_storage).
    """
    # campos base
    user_name:          str
    user_level:         str
    project_type:       str
    preferred_style:    str
    preferred_flow:     str
    # campos reales presentes en storage/profile.json
    avoid:              str   # cosas que el usuario prefiere evitar
    environment:        str   # entorno de trabajo (Windows, PowerShell, etc.)
    learning_style:     str   # estilo de aprendizaje preferido
    preferred_language: str   # lenguaje de programación preferido
    preferred_workflow: str   # flujo de trabajo preferido
    principles:         str   # principios de trabajo del usuario
    project_name:       str   # nombre del proyecto actual
    strengths_noted:    str   # fortalezas observadas del usuario


_PROFILE_KNOWN_KEYS = {
    "user_name", "user_level", "project_type",
    "preferred_style", "preferred_flow",
    "avoid", "environment", "learning_style",
    "preferred_language", "preferred_workflow",
    "principles", "project_name", "strengths_noted",
}


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
    """Schema completo de cada episodio en episodic_memory.json."""
    carril_dominante:   str
    tareas_completadas: int
    exitoso:            str   # "true" | "false" | "unmarked"


class EpisodicMemory(TypedDict):
    """Schema de storage/episodic_memory.json (nivel raíz)."""
    episodes: list[EpisodeItem]


_EP_KNOWN_KEYS = {
    "date", "time", "turns", "summary",
    "carril_dominante", "tareas_completadas", "exitoso",
}


# ───────────────────────────────────────────────
# project_facts.json — no necesita TypedDict
# ───────────────────────────────────────────────
ProjectFacts = dict  # dict[str, str] en runtime


# ───────────────────────────────────────────────
# validate_storage() — test de arranque
# ───────────────────────────────────────────────

_STORAGE_DIR = Path("storage")


def _load_json_safe(path: Path) -> dict | list | None:
    """Lee un JSON sin lanzar excepciones. Never raises."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def validate_storage() -> list[str]:
    """Lee los archivos JSON de storage/ y detecta claves desconocidas.

    Returns:
        Lista de strings con advertencias. Lista vacía = todo limpio.

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
    elif isinstance(profile, dict):
        unknown = set(profile.keys()) - _PROFILE_KNOWN_KEYS
        if unknown:
            warnings.append(
                f"[storage:warn] profile.json claves desconocidas: {sorted(unknown)}"
            )
    else:
        warnings.append("[storage:error] profile.json no es un objeto JSON válido")

    # ─ Reporte final ──────────────────────────────────────────────
    if warnings:
        for w in warnings:
            print(w)
    else:
        print("[storage] ✅ Todos los archivos JSON son válidos.")

    return warnings
