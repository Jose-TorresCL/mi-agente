"""Tests de integración para el fix 6A: carril memory es terminal.

Verifica que _decide_memory siempre devuelve un string (nunca None)
y que process_turn con route='memory' no cae al carril RAG.

Estos tests mockean las funciones de memory_manager para no depender
de archivos JSON en storage/.

Actualizado D5: _decide_memory(question, intents) — intents se detectan
una sola vez en process_turn y se pasan como argumento.
"""
import pytest
from unittest.mock import patch, MagicMock

from app.intelligence import _decide_memory
from app.router import classify_memory_query


class TestDecideMemoryAlwaysReturnsString:
    """Fix 6A: _decide_memory nunca devuelve None."""

    def test_unknown_question_returns_string_not_none(self):
        """Una pregunta que no encaja en ningún tipo conocido → string, no None."""
        # intents=[] simula que detect_memory_intents no encontró nada
        result = _decide_memory("¿Cuál es la capital de Francia?", intents=[])
        assert result is not None, "_decide_memory nunca debe retornar None"
        assert isinstance(result, str)
        assert len(result) > 0

    def test_unknown_question_contains_helpful_hint(self):
        """El mensaje de 'no encontré' incluye sugerencias de uso."""
        result = _decide_memory("dime algo aleatorio", intents=[])
        assert "No encontré" in result or "memoria" in result.lower()

    @patch("app.intelligence.get_profile", return_value={"user_name": "José", "user_level": "junior"})
    def test_profile_question_returns_profile(self, mock_profile):
        """Pregunta de perfil → respuesta con datos del perfil."""
        result = _decide_memory("¿cuál es mi perfil?", intents=["profile"])
        assert result is not None
        assert isinstance(result, str)
        # El resultado debe mencionar el nombre o nivel
        assert "José" in result or "junior" in result or "Perfil" in result

    @patch("app.intelligence.get_tasks", return_value={"tasks": []})
    def test_tasks_question_no_tasks(self, mock_tasks):
        """Pregunta de tareas sin tareas pendientes → mensaje claro."""
        result = _decide_memory("¿qué tareas tengo pendientes?", intents=["tasks"])
        assert result is not None
        assert isinstance(result, str)


class TestClassifyMemoryQueryEpisode:
    """Fix 6B: classify_memory_query reconoce el tipo 'episode'."""

    def test_episode_question_classified_as_episode(self):
        """Pregunta sobre sesiones anteriores → tipo 'episode'."""
        result = classify_memory_query("¿qué aprendí la semana pasada?")
        assert result == "episode", f"Esperaba 'episode', obtuve '{result}'"

    def test_episode_question_variant(self):
        result = classify_memory_query("¿qué trabajamos en la sesión anterior?")
        assert result == "episode"

    def test_episode_avance_question(self):
        result = classify_memory_query("¿qué avancé ayer?")
        assert result == "episode"

    def test_work_state_not_classified_as_episode(self):
        """Pregunta de estado actual no debe clasificarse como episodio."""
        result = classify_memory_query("¿en qué estoy trabajando ahora?")
        assert result == "work_state"

    def test_unknown_question_returns_none(self):
        """Pregunta sin keywords conocidas → None (comportamiento esperado del router)."""
        result = classify_memory_query("¿cuál es la capital de Francia?")
        assert result is None
