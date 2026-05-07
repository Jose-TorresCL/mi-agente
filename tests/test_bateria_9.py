"""
Batería de validación — 9 preguntas del informe de diagnóstico de Lautaro.

Verifica que cada pregunta sea enrutada al carril correcto.
No requiere Ollama activo — solo prueba el router (rápido, sin LLM).

Uso:
    python -m pytest tests/test_bateria_9.py -v
    python tests/test_bateria_9.py          # sin pytest
"""
from __future__ import annotations

import sys
from pathlib import Path

# Asegura que el proyecto raíz esté en el path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.router import route_query, classify_memory_query

# ─────────────────────────────────────────────
# Las 9 preguntas del informe con carril esperado
# ─────────────────────────────────────────────

BATERIA = [
    {
        "id": "P1",
        "tipo": "Perfil",
        "pregunta": "¿Cuál es mi estilo preferido?",
        "carril_esperado": "memory",
        "memoria_esperada": "profile",
        "descripcion": "Debe ir a memory y clasificarse como profile",
    },
    {
        "id": "P2",
        "tipo": "Workstate",
        "pregunta": "¿Qué sigue ahora?",
        "carril_esperado": "memory",
        "memoria_esperada": "work_state",
        "descripcion": "Debe ir a memory y clasificarse como work_state",
    },
    {
        "id": "P3",
        "tipo": "Facts",
        "pregunta": "¿En qué fase estamos?",
        "carril_esperado": "memory",
        "memoria_esperada": "project_facts",
        "descripcion": "Debe ir a memory y clasificarse como project_facts",
    },
    {
        "id": "P4",
        "tipo": "Tareas",
        "pregunta": "¿Qué tareas tengo pendientes?",
        "carril_esperado": "memory",
        "memoria_esperada": "tasks",
        "descripcion": "Debe ir a memory y clasificarse como tasks",
    },
    {
        "id": "P5",
        "tipo": "RAG",
        "pregunta": "¿Qué diferencia hay entre arquitectura y base documental?",
        "carril_esperado": "rag",
        "memoria_esperada": None,
        "descripcion": "Pregunta documental — debe ir a rag",
    },
    {
        "id": "P6",
        "tipo": "Tool lectura",
        "pregunta": "¿Qué archivos hay en el proyecto?",
        "carril_esperado": "tool_list_files",
        "memoria_esperada": None,
        "descripcion": "Debe ir a tool_list_files",
    },
    {
        "id": "P7",
        "tipo": "Tool escritura",
        "pregunta": "Actualiza el foco a fase 4 reflexión post-acción",
        "carril_esperado": "tool_update_work_state",
        "memoria_esperada": None,
        "descripcion": "Debe ir a tool_update_work_state",
    },
    {
        "id": "P8",
        "tipo": "Confirmación humana",
        "pregunta": "crea una tarea revisar fidelity_check",
        "carril_esperado": "tool_create_task",
        "memoria_esperada": None,
        "descripcion": "Crear tarea explícita — debe ir a tool_create_task, NO crear tarea automática",
    },
    {
        "id": "P9",
        "tipo": "Salida",
        "pregunta": "salie",
        "carril_esperado": "exit",
        "memoria_esperada": None,
        "descripcion": "Typo de salida — debe interceptarse como exit antes del router",
    },
]


# ─────────────────────────────────────────────
# Runner manual (sin pytest)
# ─────────────────────────────────────────────

def _run_bateria() -> None:
    """Ejecuta la batería y muestra resultados con formato claro."""
    PASS = "\033[92m✅ PASS\033[0m"
    FAIL = "\033[91m❌ FAIL\033[0m"

    passed = 0
    failed = 0
    results = []

    print("\n" + "=" * 60)
    print("  BATERÍA DE VALIDACIÓN — 9 PREGUNTAS DE LAUTARO")
    print("=" * 60)

    for caso in BATERIA:
        pregunta = caso["pregunta"]
        esperado = caso["carril_esperado"]
        mem_esperada = caso["memoria_esperada"]

        # Evaluar carril
        carril_real = route_query(pregunta)
        carril_ok = carril_real == esperado

        # Evaluar sub-ruta de memory si aplica
        mem_ok = True
        mem_real = None
        if mem_esperada is not None and carril_real == "memory":
            mem_real = classify_memory_query(pregunta)
            mem_ok = mem_real == mem_esperada

        ok = carril_ok and mem_ok

        if ok:
            passed += 1
            estado = PASS
        else:
            failed += 1
            estado = FAIL

        results.append({
            "caso": caso,
            "carril_real": carril_real,
            "mem_real": mem_real,
            "ok": ok,
        })

        # Imprimir resultado
        print(f"\n[{caso['id']}] {caso['tipo']} {estado}")
        print(f"  Pregunta : {pregunta}")
        print(f"  Esperado : carril={esperado}" + (f", memoria={mem_esperada}" if mem_esperada else ""))
        print(f"  Obtenido : carril={carril_real}" + (f", memoria={mem_real}" if mem_real else ""))
        if not ok:
            if not carril_ok:
                print(f"  ⚠  Carril incorrecto: esperaba '{esperado}', obtuvo '{carril_real}'")
            if not mem_ok:
                print(f"  ⚠  Sub-ruta incorrecta: esperaba '{mem_esperada}', obtuvo '{mem_real}'")

    print("\n" + "=" * 60)
    print(f"  RESULTADO: {passed}/9 PASS — {failed}/9 FAIL")
    print("=" * 60 + "\n")

    if failed > 0:
        print("Revisa los casos FAIL antes de continuar con el siguiente sprint.\n")
    else:
        print("✨ Todo verde. Lautaro responde correctamente las 9 preguntas base.\n")


# ─────────────────────────────────────────────
# Tests pytest (uno por caso)
# ─────────────────────────────────────────────

def test_P1_perfil_carril():
    """P1: ¿Cuál es mi estilo preferido? → memory"""
    assert route_query("¿Cuál es mi estilo preferido?") == "memory"

def test_P1_perfil_subruta():
    """P1: sub-ruta debe ser profile"""
    assert classify_memory_query("¿Cuál es mi estilo preferido?") == "profile"

def test_P2_workstate_carril():
    """P2: ¿Qué sigue ahora? → memory"""
    assert route_query("¿Qué sigue ahora?") == "memory"

def test_P2_workstate_subruta():
    """P2: sub-ruta debe ser work_state"""
    assert classify_memory_query("¿Qué sigue ahora?") == "work_state"

def test_P3_facts_carril():
    """P3: ¿En qué fase estamos? → memory"""
    assert route_query("¿En qué fase estamos?") == "memory"

def test_P3_facts_subruta():
    """P3: sub-ruta debe ser project_facts"""
    assert classify_memory_query("¿En qué fase estamos?") == "project_facts"

def test_P4_tareas_carril():
    """P4: ¿Qué tareas tengo pendientes? → memory"""
    assert route_query("¿Qué tareas tengo pendientes?") == "memory"

def test_P4_tareas_subruta():
    """P4: sub-ruta debe ser tasks"""
    assert classify_memory_query("¿Qué tareas tengo pendientes?") == "tasks"

def test_P5_rag():
    """P5: pregunta documental → rag"""
    assert route_query("¿Qué diferencia hay entre arquitectura y base documental?") == "rag"

def test_P6_tool_list_files():
    """P6: listar archivos → tool_list_files"""
    assert route_query("¿Qué archivos hay en el proyecto?") == "tool_list_files"

def test_P7_tool_update_work_state():
    """P7: actualizar foco → tool_update_work_state"""
    assert route_query("Actualiza el foco a fase 4 reflexión post-acción") == "tool_update_work_state"

def test_P8_tool_create_task():
    """P8: crear tarea explícita → tool_create_task"""
    assert route_query("crea una tarea revisar fidelity_check") == "tool_create_task"

def test_P9_salida():
    """P9: typo de salida → exit"""
    assert route_query("salie") == "exit"


if __name__ == "__main__":
    _run_bateria()
