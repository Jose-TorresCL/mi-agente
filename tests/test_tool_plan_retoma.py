"""Batería mínima para app/tool_plan_retoma.py (tool de solo lectura).

Qué se verifica:
  1. El plan real del repo (analysis/retoma_plan.json) se lee y trae las 4 claves.
  2. Una sección concreta se devuelve sola, y los alias en español funcionan.
  3. Una sección inexistente NO revienta: ok=False con error_code UNKNOWN_SECTION.
  4. Archivo ausente → ok=False con PLAN_NOT_FOUND (never raises).
  5. JSON inválido → ok=False con INVALID_JSON.

Ejecutar:  pytest tests/test_tool_plan_retoma.py -v
"""
from __future__ import annotations

from pathlib import Path

from app.tool_plan_retoma import (
    PLAN_FILE,
    SECCIONES,
    build_episode_plan_retoma,
    tool_plan_retoma,
)


def test_plan_completo_tiene_las_cuatro_secciones():
    r = tool_plan_retoma()
    assert r["ok"] is True
    for clave in SECCIONES:
        assert clave in r["data"]["contenido"], f"falta la sección {clave}"


def test_seccion_concreta_y_alias():
    directa = tool_plan_retoma("next_actions")
    alias = tool_plan_retoma("acciones")
    assert directa["ok"] is True
    assert directa["data"]["seccion"] == "next_actions"
    assert alias["data"]["seccion"] == "next_actions"
    assert isinstance(directa["data"]["contenido"], list)


def test_seccion_desconocida_no_revienta():
    r = tool_plan_retoma("presupuesto_de_marte")
    assert r["ok"] is False
    assert r["error_code"] == "UNKNOWN_SECTION"


def test_archivo_ausente_devuelve_plan_not_found():
    r = tool_plan_retoma(None, ruta=Path("analysis") / "no_existe_este_plan.json")
    assert r["ok"] is False
    assert r["error_code"] == "PLAN_NOT_FOUND"


def test_json_invalido_devuelve_invalid_json(tmp_path):
    malo = tmp_path / "roto.json"
    malo.write_text("{ esto no es json", encoding="utf-8")
    r = tool_plan_retoma(None, ruta=malo)
    assert r["ok"] is False
    assert r["error_code"] == "INVALID_JSON"


def test_build_episode_tiene_contrato_de_episodio():
    ep = build_episode_plan_retoma("2026-08-03", "20:58", ruta=PLAN_FILE)
    assert ep is not None
    assert ep["type"] == "plan_retoma"
    assert ep["date"] == "2026-08-03"
    assert ep["summary"]
    assert "next_actions" in ep["details"]
