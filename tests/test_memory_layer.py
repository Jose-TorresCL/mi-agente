"""Test arquitectural: verifica que las capas de memoria están separadas.

Este test NO prueba lógica de negocio — prueba que la arquitectura
de capas es correcta:

  Capa externa (tools, chat_core)
      ↓ usa
  memory_manager   (capa de servicio)
      ↓ usa
  memory_store     (capa de persistencia I/O)
      ↓ usa
  storage/*.json

Reglas que valida:
  R1: memory_manager importa memory_store (relación correcta)
  R2: memory_manager NO importa tools ni chat_core (sin dependencias inversas)
  R3: tools importa memory_manager, NO importa memory_store directamente
  R4: chat_core importa memory_manager, NO importa memory_store directamente
  R5: memory_manager expone las interfaces públicas esperadas
  R6: save_fact rechaza key o value vacíos
  R7: create_task rechaza title vacío
"""
from __future__ import annotations

import importlib
import inspect
import sys

import pytest


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def mm():
    """Importa memory_manager una sola vez para todos los tests del módulo."""
    return importlib.import_module("app.memory_manager")


@pytest.fixture(scope="module")
def tools_mod():
    return importlib.import_module("app.tools")


@pytest.fixture(scope="module")
def chat_core_mod():
    return importlib.import_module("app.chat_core")


# ─────────────────────────────────────────────
# R1 — memory_manager usa memory_store
# ─────────────────────────────────────────────

def test_R1_memory_manager_imports_memory_store(mm):
    """memory_manager debe importar memory_store."""
    source = inspect.getsource(mm)
    assert "memory_store" in source, (
        "memory_manager.py debe importar desde app.memory_store"
    )


# ─────────────────────────────────────────────
# R2 — memory_manager NO tiene dependencias inversas
# ─────────────────────────────────────────────

def test_R2_memory_manager_no_imports_tools(mm):
    """memory_manager NO debe importar tools ni chat_core."""
    source = inspect.getsource(mm)
    assert "from app.tools" not in source, (
        "memory_manager no debe depender de tools (dependencia inversa)"
    )
    assert "from app.chat_core" not in source, (
        "memory_manager no debe depender de chat_core (dependencia inversa)"
    )
    assert "import tools" not in source
    assert "import chat_core" not in source


# ─────────────────────────────────────────────
# R3 — tools usa memory_manager, NO memory_store
# ─────────────────────────────────────────────

def test_R3_tools_uses_memory_manager(tools_mod):
    """tools.py debe importar memory_manager para operaciones de memoria."""
    source = inspect.getsource(tools_mod)
    assert "memory_manager" in source, (
        "tools.py debe importar desde app.memory_manager"
    )


def test_R3_tools_not_import_memory_store_directly(tools_mod):
    """tools.py NO debe importar memory_store directamente."""
    source = inspect.getsource(tools_mod)
    # Permitido: comentarios con el nombre
    # No permitido: from app.memory_store import ... o import app.memory_store
    import re
    direct_import = re.search(
        r'^\s*from\s+app\.memory_store\s+import',
        source,
        re.MULTILINE,
    )
    assert direct_import is None, (
        "tools.py no debe hacer 'from app.memory_store import' directamente.\n"
        "Usa memory_manager como intermediario."
    )


# ─────────────────────────────────────────────
# R4 — chat_core usa memory_manager, NO memory_store
# ─────────────────────────────────────────────

def test_R4_chat_core_uses_memory_manager(chat_core_mod):
    """chat_core.py debe importar memory_manager."""
    source = inspect.getsource(chat_core_mod)
    assert "memory_manager" in source, (
        "chat_core.py debe importar desde app.memory_manager"
    )


def test_R4_chat_core_not_import_memory_store_directly(chat_core_mod):
    """chat_core.py NO debe importar memory_store directamente."""
    source = inspect.getsource(chat_core_mod)
    import re
    direct_import = re.search(
        r'^\s*from\s+app\.memory_store\s+import',
        source,
        re.MULTILINE,
    )
    assert direct_import is None, (
        "chat_core.py no debe hacer 'from app.memory_store import' directamente.\n"
        "Usa memory_manager como intermediario."
    )


# ─────────────────────────────────────────────
# R5 — interfaces públicas de memory_manager
# ─────────────────────────────────────────────

@pytest.mark.parametrize("func_name", [
    # Contexto
    "get_full_context",
    "get_working_context",
    "get_semantic_context",
    "get_episodic_context",
    # Lectura directa
    "get_profile",
    "get_project_facts",
    "get_tasks",
    "get_work_state",
    "get_last_episode",
    # Escritura
    "save_fact",
    "update_state",
    "create_task",
    "complete_task",
    "record_episode",
])
def test_R5_memory_manager_public_interface(mm, func_name):
    """memory_manager debe exponer todas las interfaces públicas esperadas."""
    assert hasattr(mm, func_name), (
        f"memory_manager no expone '{func_name}'. "
        f"Agrégalo o verifica el nombre."
    )
    assert callable(getattr(mm, func_name)), (
        f"'{func_name}' en memory_manager no es callable."
    )


# ─────────────────────────────────────────────
# R6 — save_fact rechaza vacíos
# ─────────────────────────────────────────────

def test_R6_save_fact_rejects_empty_key(mm):
    """save_fact debe retornar False si la key está vacía."""
    result = mm.save_fact("", "algún valor")
    assert result is False, "save_fact debe retornar False con key vacía"


def test_R6_save_fact_rejects_empty_value(mm):
    """save_fact debe retornar False si el value está vacío."""
    result = mm.save_fact("alguna_clave", "")
    assert result is False, "save_fact debe retornar False con value vacío"


def test_R6_save_fact_rejects_whitespace_only(mm):
    """save_fact debe retornar False con key o value de solo espacios."""
    assert mm.save_fact("  ", "valor") is False
    assert mm.save_fact("clave", "   ") is False


# ─────────────────────────────────────────────
# R7 — create_task rechaza title vacío
# ─────────────────────────────────────────────

def test_R7_create_task_rejects_empty_title(mm):
    """create_task debe retornar string vacío si el título está vacío."""
    result = mm.create_task("")
    assert result == "", (
        f"create_task con título vacío debe retornar '', retornó: {result!r}"
    )


def test_R7_create_task_rejects_whitespace_only_title(mm):
    """create_task debe retornar string vacío con título de solo espacios."""
    result = mm.create_task("   ")
    assert result == "", (
        f"create_task con título de espacios debe retornar '', retornó: {result!r}"
    )
