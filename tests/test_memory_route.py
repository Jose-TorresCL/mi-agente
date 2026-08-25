"""
Tests de integración para el fix 6A: carril memory es terminal.

Verifica que _decide_memory siempre devuelve un string (nunca None)
y que process_turn con route='memory' no cae al carril RAG.

Estos tests mockean las funciones de memory_manager para no depender
de archivos JSON en storage/.

Actualizado D5: _decide_memory(question, intents) — intents se detectan
una sola vez en process_turn y se pasan como argumento.

Incluye contrato de work_state:
una consulta directa debe responder desde datos estructurados sin usar LLM.
"""

from unittest.mock import patch

from app.intelligence import _decide_memory
from app.router import classify_memory_query


class TestDecideMemoryAlwaysReturnsString:
    """Fix 6A: _decide_memory nunca devuelve None."""

    def test_unknown_question_returns_string_not_none(self):
        """Una pregunta sin intención de memoria devuelve string, no None."""
        result = _decide_memory(
            "¿Cuál es la capital de Francia?",
            intents=[],
        )

        assert result is not None, "_decide_memory nunca debe retornar None"
        assert isinstance(result, str)
        assert len(result) > 0

    def test_unknown_question_contains_helpful_hint(self):
        """El mensaje de 'no encontré' incluye ayuda sobre memoria."""
        result = _decide_memory(
            "dime algo aleatorio",
            intents=[],
        )

        assert "No encontré" in result or "memoria" in result.lower()

    @patch(
        "app.intelligence.get_profile",
        return_value={
            "user_name": "José",
            "user_level": "junior",
        },
    )
    def test_profile_question_returns_profile(self, mock_profile):
        """Pregunta de perfil devuelve datos estructurados del perfil."""
        result = _decide_memory(
            "¿cuál es mi perfil?",
            intents=["profile"],
        )

        assert result is not None
        assert isinstance(result, str)
        assert "José" in result or "junior" in result or "Perfil" in result
        mock_profile.assert_called_once()

    @patch(
        "app.intelligence.get_tasks",
        return_value={"tasks": []},
    )
    def test_tasks_question_no_tasks(self, mock_tasks):
        """Pregunta de tareas sin pendientes devuelve un mensaje claro."""
        result = _decide_memory(
            "¿qué tareas tengo pendientes?",
            intents=["tasks"],
        )

        assert result is not None
        assert isinstance(result, str)
        mock_tasks.assert_called_once()

    @patch(
        "app.intelligence.get_work_state",
        return_value={
            "current_focus": "memoria automática",
            "last_completed": "fix del logger",
            "next_step": "correr tests",
            "current_blockers": [],
        },
    )
    @patch("app.intelligence.generate_raw")
    def test_work_state_responde_directo_sin_llm(
        self,
        mock_generate_raw,
        mock_get_work_state,
    ):
        """
        Una consulta directa de work_state responde desde datos estructurados.

        No debe usar LLM: el foco, último paso y siguiente paso ya existen
        en work_state y deben devolverse sin latencia ni síntesis frágil.
        """
        result = _decide_memory(
            "¿Cuál es mi foco actual?",
            intents=["work_state"],
        )

        assert isinstance(result, str)
        assert "memoria automática" in result
        assert "fix del logger" in result
        assert "correr tests" in result

        mock_get_work_state.assert_called_once()
        mock_generate_raw.assert_not_called()


class TestClassifyMemoryQueryEpisode:
    """Fix 6B: classify_memory_query reconoce el tipo 'episode'."""

    def test_episode_question_classified_as_episode(self):
        """Pregunta sobre sesiones anteriores devuelve 'episode'."""
        result = classify_memory_query(
            "¿qué aprendí la semana pasada?",
        )

        assert result == "episode", f"Esperaba 'episode', obtuve '{result}'"

    def test_episode_question_variant(self):
        """Variante de sesión anterior también devuelve 'episode'."""
        result = classify_memory_query(
            "¿qué trabajamos en la sesión anterior?",
        )

        assert result == "episode"

    def test_episode_avance_question(self):
        """Pregunta por avances pasados devuelve 'episode'."""
        result = classify_memory_query(
            "¿qué avancé ayer?",
        )

        assert result == "episode"

    def test_work_state_not_classified_as_episode(self):
        """Una pregunta de estado actual no debe clasificarse como episode."""
        result = classify_memory_query(
            "¿en qué estoy trabajando ahora?",
        )

        assert result == "work_state"

    def test_unknown_question_returns_none(self):
        """Pregunta sin keywords de memoria devuelve None."""
        result = classify_memory_query(
            "¿cuál es la capital de Francia?",
        )

        assert result is None