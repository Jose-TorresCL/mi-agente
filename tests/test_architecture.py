"""Tests de arquitectura — 6D.

Verifica que las capas del sistema respetan los contratos de dependencia
definidos en ADR-001 y ADR-002. Detecta drift arquitectónico silencioso.

Reglas verificadas:
  1. chat_ui.py NO importa memory_store ni memory_manager directamente.
     La UI solo conoce chat_core — la persistencia es opaca.
  2. intelligence.py NO importa chat_ui ni chat.py.
     La capa de inteligencia no conoce la UI.
  3. fidelity_check.py NO importa intelligence.py.
     El verificador de fidelidad no crea dependencias circulares.
  4. router.py NO importa intelligence.py ni rag_engine.py.
     El router es una función pura de clasificación sin efectos.

Cómo funciona: lee el contenido de cada archivo y verifica que las
importaciones prohibidas no aparezcan. No ejecuta el código — solo
análisis estático de texto.
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
