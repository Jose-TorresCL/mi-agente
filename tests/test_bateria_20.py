"""
Batería de validación ampliada — 20 preguntas (Fase 7C).

Amplía test_bateria_9.py de 9 a 20 casos cubriendo:
  - Variantes de los 4 tipos de memoria (work_state, profile, tasks, project_facts)
  - Tipo episódico (nuevo en 6B)
  - RAG documental y RAG paper
  - Herramientas (tool_list_files, tool_update_work_state)
  - Carril unsupported (preguntas cuantitativas del código)
  - Exit con variante diferente

No requiere Ollama activo — solo prueba el router (rápido, sin LLM).

Uso:
    python -m pytest tests/test_bateria_20.py -v
    python tests/test_bateria_20.py          # sin pytest
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.router import route_query, classify_memory_query

# ─────────────────────────────────────────────
# Batería completa: 20 casos
# ─────────────────────────────────────────────

BATERIA_20 = [
    # ── 9 originales ──────────────────────────────────────────────────────
    {"id": "P01", "pregunta": "¿Cuál es mi estilo preferido?",
     "carril": "memory", "memoria": "profile"},
    {"id": "P02", "pregunta": "¿Qué sigue ahora?",
     "carril": "memory", "memoria": "work_state"},
    {"id": "P03", "pregunta": "¿En qué fase estamos?",
     "carril": "memory", "memoria": "project_facts"},
    {"id": "P04", "pregunta": "¿Qué tareas tengo pendientes?",
     "carril": "memory", "memoria": "tasks"},
    {"id": "P05", "pregunta": "¿Qué diferencia hay entre arquitectura y base documental?",
     "carril": "rag",    "memoria": None},
    {"id": "P06", "pregunta": "¿Qué archivos hay en el proyecto?",
     "carril": "tool_list_files", "memoria": None},
    {"id": "P07", "pregunta": "Actualiza el foco a fase 4 reflexión post-acción",
     "carril": "tool_update_work_state", "memoria": None},
    {"id": "P08", "pregunta": "crea una tarea revisar fidelity_check",
     "carril": "tool_create_task", "memoria": None},
    {"id": "P09", "pregunta": "salie",
     "carril": "exit", "memoria": None},
    # ── 11 nuevos ─────────────────────────────────────────────────────────
    {"id": "P10", "pregunta": "¿cuál es el foco actual?",
     "carril": "memory", "memoria": "work_state"},
    {"id": "P11", "pregunta": "¿cómo prefiero que me expliques las cosas?",
     "carril": "memory", "memoria": "profile"},
    {"id": "P12", "pregunta": "dame mis tareas de hoy",
     "carril": "memory", "memoria": "tasks"},
    {"id": "P13", "pregunta": "¿en qué sprint estamos?",
     "carril": "memory", "memoria": "project_facts"},
    {"id": "P14", "pregunta": "¿qué aprendí la sesión pasada?",
     "carril": "memory", "memoria": "episode"},
    {"id": "P15", "pregunta": "¿qué es un embedding?",
     "carril": "rag",   "memoria": None},
    {"id": "P16", "pregunta": "¿qué dice el paper de SLM-First?",
     "carril": "rag",   "memoria": None},
    {"id": "P17", "pregunta": "lista los archivos Python del proyecto",
     "carril": "tool_list_files", "memoria": None},
    {"id": "P18", "pregunta": "cambia el foco a observabilidad",
     "carril": "tool_update_work_state", "memoria": None},
    {"id": "P19", "pregunta": "¿cuántas líneas de código tiene el proyecto?",
     "carril": "unsupported", "memoria": None},
    {"id": "P20", "pregunta": "adios",
     "carril": "exit", "memoria": None},
]


# ─────────────────────────────────────────────
# Runner manual (sin pytest)
# ─────────────────────────────────────────────

def _run_bateria() -> None:
    PASS = "\033[92m✅ PASS\033[0m"
    FAIL = "\033[91m❌ FAIL\033[0m"
    passed = failed = 0

    print("\n" + "=" * 65)
    print("  BATERÍA DE VALIDACIÓN — 20 PREGUNTAS (Fase 7C)")
    print("=" * 65)

    for caso in BATERIA_20:
        carril_real = route_query(caso["pregunta"])
        carril_ok = carril_real == caso["carril"]

        mem_ok = True
        mem_real = None
        if caso["memoria"] is not None and carril_real == "memory":
            mem_real = classify_memory_query(caso["pregunta"])
            mem_ok = mem_real == caso["memoria"]

        ok = carril_ok and mem_ok
        passed += ok
        failed += not ok

        estado = PASS if ok else FAIL
        print(f"\n[{caso['id']}] {estado}")
        print(f"  Pregunta : {caso['pregunta']}")
        print(f"  Esperado : carril={caso['carril']}" +
              (f", memoria={caso['memoria']}" if caso["memoria"] else ""))
        print(f"  Obtenido : carril={carril_real}" +
              (f", memoria={mem_real}" if mem_real else ""))
        if not carril_ok:
            print(f"  ⚠  Carril: esperaba '{caso['carril']}', obtuvo '{carril_real}'")
        if not mem_ok:
            print(f"  ⚠  Memoria: esperaba '{caso['memoria']}', obtuvo '{mem_real}'")

    print("\n" + "=" * 65)
    print(f"  RESULTADO: {passed}/20 PASS — {failed}/20 FAIL")
    print("=" * 65 + "\n")


# ─────────────────────────────────────────────
# Tests pytest — uno por caso (carril + memoria)
# ─────────────────────────────────────────────

def _make_carril_test(caso: dict):
    def _test():
        assert route_query(caso["pregunta"]) == caso["carril"], (
            f"{caso['id']}: esperaba carril '{caso['carril']}', "
            f"obtuvo '{route_query(caso['pregunta'])}'"
        )
    _test.__name__ = f"test_{caso['id']}_carril"
    _test.__doc__ = f"{caso['id']}: '{caso['pregunta']}' → {caso['carril']}"
    return _test

def _make_memoria_test(caso: dict):
    def _test():
        assert classify_memory_query(caso["pregunta"]) == caso["memoria"], (
            f"{caso['id']}: esperaba memoria '{caso['memoria']}', "
            f"obtuvo '{classify_memory_query(caso['pregunta'])}'"
        )
    _test.__name__ = f"test_{caso['id']}_memoria"
    _test.__doc__ = f"{caso['id']}: memoria → {caso['memoria']}"
    return _test


# Inyectar tests al módulo para que pytest los descubra
_this = sys.modules[__name__]
for _caso in BATERIA_20:
    setattr(_this, f"test_{_caso['id']}_carril", _make_carril_test(_caso))
    if _caso["memoria"] is not None:
        setattr(_this, f"test_{_caso['id']}_memoria", _make_memoria_test(_caso))


if __name__ == "__main__":
    _run_bateria()
