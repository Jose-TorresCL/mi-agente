"""Contrato del registro de tools, con foco en `tool_plan_retoma`.

Qué protege esta batería:
  1. La tool está registrada, con handler llamable y riesgo READ.
  2. Los keywords pedidos están declarados en el registro.
  3. `dispatch_tool()` responde (ok=True) con y sin sección.
  4. Los alias en español ('acciones', 'next_actions', 'recomendaciones')
     resuelven a la sección correcta.
  5. **No hay regresión de router**: registrar este carril no le robó
     consultas a memory:tasks ni a memory:work_state.

Ejecutar:  pytest tests/test_tool_registry.py -v
"""
from __future__ import annotations

import pytest

from app import tool_registry
from app.router import _route_by_keywords
from app.schemas import RiskLevel
from app.tool_plan_retoma import detectar_seccion

CARRIL = "tool_plan_retoma"


# ── 1. Registro ───────────────────────────────────────────────────────────────

def test_plan_retoma_esta_registrado():
    assert CARRIL in tool_registry.TOOLS


def test_entrada_tiene_los_campos_del_contrato():
    entrada = tool_registry.TOOLS[CARRIL]
    for campo in ("fn", "carril", "descripcion", "risk", "handler"):
        assert campo in entrada, f"falta el campo '{campo}'"
    assert callable(entrada["handler"])
    assert callable(entrada["fn"])
    assert entrada["carril"] == CARRIL


def test_riesgo_es_read_no_system():
    # READ ⇒ dispatch_tool no lo bloquea. SYSTEM lo dejaría inalcanzable.
    assert tool_registry.TOOLS[CARRIL]["risk"] is RiskLevel.READ


@pytest.mark.parametrize("kw", ["plan", "retoma", "tareas", "plan_retoma"])
def test_keywords_declarados(kw):
    assert kw in tool_registry.TOOLS[CARRIL]["keywords"]


# ── 2. Despacho ───────────────────────────────────────────────────────────────

def test_dispatch_sin_seccion_devuelve_plan_completo():
    res = tool_registry.dispatch_tool(CARRIL, "muestrame el plan de retoma")
    assert res is not None
    assert res["ok"] is True
    assert res.get("message", "").strip()


def test_dispatch_devuelve_texto_no_vacio():
    texto = tool_registry.dispatch_tool_str(CARRIL, "plan de retoma")
    assert isinstance(texto, str)
    assert texto.strip()


@pytest.mark.parametrize(
    "frase,esperado",
    [
        ("dame las acciones del plan", "next_actions"),
        ("muestrame next_actions", "next_actions"),
        ("cuales son las recomendaciones del plan", "recommendations"),
        ("que secciones faltantes hay", "missing_sections"),
        ("dame la validacion", "validation"),
    ],
)
def test_alias_en_espanol_resuelven_la_seccion(frase, esperado):
    assert detectar_seccion(frase) == esperado


def test_frase_sin_seccion_no_es_error():
    # Sin sección reconocible ⇒ plan completo, no un fallo.
    assert detectar_seccion("retomemos el proyecto") is None
    res = tool_registry.dispatch_tool(CARRIL, "retomemos el proyecto")
    assert res is not None and res["ok"] is True


# ── 3. Router: alcanzable y sin regresiones ──────────────────────────────────

@pytest.mark.parametrize(
    "frase",
    [
        "muestrame el plan de retoma",
        "que dice el plan_retoma",
        "quiero retomar el proyecto",
        "dame las acciones del plan",
        "como va la auditoria de documentacion",
    ],
)
def test_router_alcanza_el_carril(frase):
    assert _route_by_keywords(frase) == CARRIL


@pytest.mark.parametrize(
    "frase,carril_esperado",
    [
        ("que tareas tengo", "memory:tasks"),
        ("tareas pendientes", "memory:tasks"),
        ("cual es el plan", "memory:work_state"),
        ("en que estoy trabajando", "memory:work_state"),
    ],
)
def test_no_roba_consultas_a_memoria(frase, carril_esperado):
    assert _route_by_keywords(frase) == carril_esperado
