"""Tests de arquitectura — 6D + R1 (robustecimiento de contratos).

Verifica que las capas del sistema respetan los contratos de dependencia
definidos en ADR-001, ADR-002 y el plan de robustecimiento R1.

Reglas verificadas (6D):
  1. chat_ui.py NO importa memory_store ni memory_manager directamente.
  2. intelligence.py NO importa chat_ui ni chat.py.
  3. fidelity_check.py NO importa intelligence.py.
  4. router.py NO importa intelligence.py ni rag_engine.py.

Reglas nuevas (R1-C/D/E):
  5. intelligence.py NO importa memory_store directamente.
     Debe pasar por memory_manager — nunca tocar el store crudo.
  6. tools.py NO importa memory_store directamente.
     Las tools acceden a memoria solo a través de memory_manager.
  7. router.py NO importa chromadb ni langchain_chroma directamente.
     El router es una función pura de clasificación; Chroma pertenece
     a rag_engine y episode_store, no al router.

Cómo funciona: lee el contenido de cada archivo y verifica que las
importaciones prohibidas no aparezcan. No ejecuta el código — solo
análisis estático de texto (AST).
"""
import ast
from pathlib import Path
import pytest

APP_DIR = Path("app")


def _get_imports(filepath: Path) -> set[str]:
    """Extrae los módulos importados desde un archivo Python.

    Usa ast para un análisis estático real (no regex).
    Retorna el conjunto de nombres de módulos importados.
    """
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (FileNotFoundError, SyntaxError) as e:
        pytest.skip(f"No se puede analizar {filepath}: {e}")
        return set()

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


class TestArchitecturalConstraints:
    """Contratos de dependencia entre capas (ADR-001, ADR-002)."""

    def test_chat_ui_does_not_import_memory_store(self):
        """chat_ui.py no debe importar memory_store directamente.

        La UI accede a memoria solo a través de chat_core.
        """
        chat_ui = APP_DIR / "chat_ui.py"
        if not chat_ui.exists():
            pytest.skip("chat_ui.py no existe en este entorno")
        imports = _get_imports(chat_ui)
        forbidden = {"app.memory_store", "memory_store"}
        violations = imports & forbidden
        assert not violations, (
            f"chat_ui.py importa capas de persistencia directamente: {violations}. "
            "La UI debe acceder a memoria solo a través de chat_core."
        )

    def test_chat_ui_does_not_import_memory_manager(self):
        """chat_ui.py no debe importar memory_manager directamente."""
        chat_ui = APP_DIR / "chat_ui.py"
        if not chat_ui.exists():
            pytest.skip("chat_ui.py no existe en este entorno")
        imports = _get_imports(chat_ui)
        forbidden = {"app.memory_manager", "memory_manager"}
        violations = imports & forbidden
        assert not violations, (
            f"chat_ui.py importa memory_manager directamente: {violations}."
        )

    def test_intelligence_does_not_import_chat_ui(self):
        """intelligence.py no debe importar chat_ui ni chat.py.

        La capa de inteligencia es agnóstica a la UI.
        """
        intel = APP_DIR / "intelligence.py"
        if not intel.exists():
            pytest.skip("intelligence.py no existe")
        imports = _get_imports(intel)
        forbidden = {"app.chat_ui", "chat_ui", "app.chat", "chat"}
        violations = imports & forbidden
        assert not violations, (
            f"intelligence.py importa la capa de UI: {violations}. "
            "La inteligencia no debe conocer la UI."
        )

    def test_fidelity_check_does_not_import_intelligence(self):
        """fidelity_check.py no debe importar intelligence.py.

        Evita dependencias circulares: intelligence → fidelity_check → intelligence.
        """
        fidelity = APP_DIR / "fidelity_check.py"
        if not fidelity.exists():
            pytest.skip("fidelity_check.py no existe")
        imports = _get_imports(fidelity)
        forbidden = {"app.intelligence", "intelligence"}
        violations = imports & forbidden
        assert not violations, (
            f"fidelity_check.py importa intelligence.py: {violations}. "
            "Esto crearía una dependencia circular."
        )

    def test_router_does_not_import_intelligence(self):
        """router.py no debe importar intelligence.py ni rag_engine.py.

        El router es una función pura de clasificación sin efectos secundarios.
        """
        router = APP_DIR / "router.py"
        if not router.exists():
            pytest.skip("router.py no existe")
        imports = _get_imports(router)
        forbidden = {"app.intelligence", "intelligence", "app.rag_engine", "rag_engine"}
        violations = imports & forbidden
        assert not violations, (
            f"router.py importa capas de ejecución: {violations}. "
            "El router debe ser una función pura de clasificación."
        )


class TestR1ContractConstraints:
    """Contratos de R1 — encapsulación de storage y Chroma (R1-C/D/E)."""

    def test_intelligence_does_not_import_memory_store_directly(self):
        """intelligence.py NO debe importar memory_store directamente.

        R1-C: intelligence.py accede a memoria únicamente a través de
        memory_manager. memory_store es el guardabosques crudo del disco;
        solo memory_manager tiene permiso para abrirlo.
        """
        intel = APP_DIR / "intelligence.py"
        if not intel.exists():
            pytest.skip("intelligence.py no existe")
        imports = _get_imports(intel)
        forbidden = {"app.memory_store", "memory_store"}
        violations = imports & forbidden
        assert not violations, (
            f"intelligence.py importa memory_store directamente: {violations}. "
            "Debe acceder a memoria solo a través de memory_manager — ADR-003."
        )

    def test_tools_does_not_import_memory_store_directly(self):
        """tools.py NO debe importar memory_store directamente.

        R1-D: Las tools son acciones de alto nivel. Acceden a memoria
        a través de memory_manager, no del store crudo.
        """
        tools = APP_DIR / "tools.py"
        if not tools.exists():
            pytest.skip("tools.py no existe")
        imports = _get_imports(tools)
        forbidden = {"app.memory_store", "memory_store"}
        violations = imports & forbidden
        assert not violations, (
            f"tools.py importa memory_store directamente: {violations}. "
            "Las tools deben acceder a memoria solo a través de memory_manager."
        )

    def test_router_does_not_import_chroma_directly(self):
        """router.py NO debe importar chromadb ni langchain_chroma.

        R1-E: El router clasifica intenciones — no hace retrieval.
        Chroma pertenece exclusivamente a rag_engine y episode_store.
        """
        router = APP_DIR / "router.py"
        if not router.exists():
            pytest.skip("router.py no existe")
        imports = _get_imports(router)
        forbidden = {"chromadb", "langchain_chroma", "langchain_community.vectorstores"}
        violations = imports & forbidden
        assert not violations, (
            f"router.py importa Chroma directamente: {violations}. "
            "El router es función pura de clasificación — Chroma va en rag_engine/episode_store."
        )
