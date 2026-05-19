"""R4-B — Tests de composición multi-capa de memoria.

Verifica que detect_memory_intents() y get_composed_context() funcionan
correctamente para preguntas que cruzan más de un tipo de memoria.

Principio determinista (igual que R3): NO se usa LLM ni mocks complejos.
Solo se prueba la lógica de detección y composición de capas.

Cómo correr:
    pytest tests/test_r4_memory_composition.py -v
"""
import pytest
from unittest.mock import patch

from app.memory_manager import detect_memory_intents, get_composed_context


class TestDetectMemoryIntents:
    """Verifica la detección de intenciones de memoria (1 o más tipos)."""

    # ── Preguntas de un solo tipo ─────────────────────────────────────

    def test_single_work_state(self):
        intents = detect_memory_intents("¿cuál es mi foco actual?")
        assert intents == ["work_state"]

    def test_single_tasks(self):
        intents = detect_memory_intents("¿qué tareas tengo pendientes?")
        assert "tasks" in intents
        # solo tasks, sin otros tipos
        assert len(intents) == 1

    def test_single_episode(self):
        intents = detect_memory_intents("¿qué aprendí la sesión anterior?")
        assert intents == ["episode"]

    def test_single_profile(self):
        intents = detect_memory_intents("¿cuál es mi nombre?")
        assert intents == ["profile"]

    # ── Preguntas de múltiples tipos (el corazón de R4-B) ─────────────

    def test_episode_plus_work_state(self):
        """Pregunta clásica multi-capa: sesión pasada + estado actual."""
        q = "¿qué aprendí la sesión pasada y cuál es el foco actual?"
        intents = detect_memory_intents(q)
        assert "episode" in intents, f"Falta 'episode' en {intents}"
        assert "work_state" in intents, f"Falta 'work_state' en {intents}"
        assert len(intents) == 2

    def test_work_state_plus_tasks(self):
        """Foco actual + tareas pendientes."""
        q = "¿cuál es el foco y qué tareas tengo?"
        intents = detect_memory_intents(q)
        assert "work_state" in intents
        assert "tasks" in intents

    def test_order_is_canonical(self):
        """El orden de intents sigue _INTENT_ORDER: episode antes que work_state."""
        q = "¿cuál es mi foco actual y qué aprendí antes?"
        intents = detect_memory_intents(q)
        if "episode" in intents and "work_state" in intents:
            assert intents.index("episode") < intents.index("work_state"), (
                "episode debe aparecer antes que work_state en el orden canónico"
            )

    # ── Preguntas sin señales de memoria ─────────────────────────────

    def test_no_memory_signals(self):
        """Pregunta sin keywords de memoria → lista vacía."""
        intents = detect_memory_intents("¿cuál es la capital de Francia?")
        assert intents == []

    def test_rag_question_returns_empty(self):
        """Pregunta técnica RAG → sin intenciones de memoria."""
        intents = detect_memory_intents("¿cómo funciona el router?")
        assert intents == []


class TestGetComposedContext:
    """Verifica la composición de contexto multi-capa."""

    @patch("app.memory_manager.get_episodic_context",
           return_value="Sesión anterior (2026-05-18): trabajamos en R3.")
    @patch("app.memory_manager.get_working_context",
           return_value="Foco actual: implementar R4\nSiguiente paso: agregar tests")
    def test_two_layers_composed(self, mock_working, mock_episodic):
        """Dos capas se componen con separador y etiqueta."""
        result = get_composed_context(["episode", "work_state"])
        assert "=== Sesiones anteriores ===" in result
        assert "=== Estado de trabajo ===" in result
        assert "R3" in result
        assert "R4" in result

    @patch("app.memory_manager.get_working_context",
           return_value="Foco actual: implementar R4")
    @patch("app.memory_manager.get_working_context")
    def test_empty_layer_omitted(self, mock_working, _):
        """Una capa con contenido vacío no genera sección."""
        mock_working.return_value = ""
        with patch("app.memory_manager.get_episodic_context", return_value=""):
            with patch("app.memory_manager.get_semantic_context",
                       return_value="Usuario: José (junior)"):
                result = get_composed_context(["episode", "work_state", "profile"])
                assert "=== Sesiones anteriores ===" not in result
                assert "=== Estado de trabajo ===" not in result
                assert "=== Perfil del usuario ===" in result

    def test_empty_intents_returns_empty(self):
        """Lista vacía → string vacío."""
        result = get_composed_context([])
        assert result == ""

    def test_unknown_intent_skipped_gracefully(self):
        """Tipo desconocido no lanza excepción — devuelve lo que tenga."""
        result = get_composed_context(["tipo_inexistente"])
        # No debe lanzar excepciones
        assert isinstance(result, str)
