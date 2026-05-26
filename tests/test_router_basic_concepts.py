"""Tests de conceptos técnicos en el router — Capa 1 + Capa 2 (embeddings).

Este archivo cubre el caso real del log de Telegram (2026-05-24):
  "qué es un embedding" → debe routear a 'rag', NO a 'identity'

Busca que Capa 1 (keywords) y Capa 2 (embeddings) trabajen en conjunto
para clasificar preguntas técnicas sin caer al carril 'identity'.

Ejecución:
  pytest tests/test_router_basic_concepts.py -v
"""
import pytest
from app.router import route_query


class TestBasicConceptsRAG:
    """Asegura que preguntas técnicas lleguen a RAG, no a identity."""

    @pytest.mark.parametrize("phrase", [
        # Variantes de "qué es"
        "qué es un embedding",
        "que es un embedding",
        "Qué es un embedding",
        "QUÉ ES UN EMBEDDING",
        
        # Otros conceptos técnicos fundamentales
        "qué es un retriever",
        "que es retriever",
        "qué es un vector store",
        "que es un vector store",
        "qué es Chroma",
        "que es chroma",
        "qué es LangChain",
        "que es langchain",
        
        # Con tildes variadas
        "qué es la búsqueda vectorial",
        "que es la busqueda vectorial",
        "qué es RAG",
        "que es rag",
        
        # Variantes de "cómo"
        "cómo funciona Chroma",
        "como funciona chroma",
        "cómo funciona el retriever",
        "como funciona el retriever",
        
        # Variantes de "cuál/cuáles"
        "cuál es la diferencia entre embedding y vector",
        "cual es la diferencia entre embedding y vector",
    ])
    def test_tech_concepts_route_to_rag(self, phrase):
        """Preguntas técnicas deben routear a 'rag', NO a 'identity'."""
        result = route_query(phrase)
        
        # En Capa 1, esperamos que RAG_HINTS capture "qué es", "cómo", etc.
        # Si no, Capa 2 (embeddings) debe entrenarse para detectarlas como RAG.
        assert result in ("rag", "memory:work_state"), (
            f"'{phrase}' debería routear a 'rag' (o memory con contexto), "
            f"pero fue '{result}'. Revisar RAG_HINTS en Capa 1 o "
            "training del intent_index en Capa 2."
        )
        
        # Crítico: NO debe ir a 'identity' (respuesta fija de Lautaro)
        assert result != "identity", (
            f"'{phrase}' NO debería routear a 'identity' "
            "(no es pregunta sobre quién es Lautaro). "
            "Revisar AGENT_IDENTITY_KEYWORDS en router.py."
        )

    @pytest.mark.parametrize("phrase", [
        # Estos SÍ van a identity — preguntas sobre el agente
        "quién eres",
        "quién eres tú",
        "qué puedes hacer",
        "para que sirves",
        "cuáles son tus capacidades",
    ])
    def test_agent_identity_distinct_from_tech_concepts(self, phrase):
        """Verifica que identity y tech concepts NO se mezclen."""
        result = route_query(phrase)
        assert result == "identity", (
            f"'{phrase}' es pregunta sobre identidad de agente, "
            f"debe ser 'identity', pero fue '{result}'."
        )


class TestEmbeddingsNotConfusedWithIdentity:
    """Valida que Capa 2 (embeddings) no clasifique incorrectamente."""

    def test_embedding_query_never_identity(self):
        """Si embeddings entrenado devuelve algo, NO debe ser 'identity'."""
        # Caso del log real: "qué es un embedding" llegó a embeddings
        phrase = "qué es un embedding"
        result = route_query(phrase)
        
        # Puede ser 'rag' (Capa 1) o algo RAG-like de Capa 2,
        # pero NUNCA 'identity'
        assert result != "identity", (
            "Crítica: El embedding model está clasificando preguntas "
            "técnicas como 'identity'. Revisar datos de entrenamiento "
            "en build_intent_index.py — ¿tiene ejemplos de 'identity' "
            "demasiado generales?"
        )

    def test_concept_vs_capability_clear_boundary(self):
        """Verifica frontera clara entre pregunta técnica y capacidad del agente."""
        tech_phrase = "qué es un embedding"
        agent_phrase = "qué puedes hacer"
        
        tech_result = route_query(tech_phrase)
        agent_result = route_query(agent_phrase)
        
        # No pueden ser iguales (una es técnica, otra es identity)
        assert tech_result != agent_result, (
            f"'{tech_phrase}' ({tech_result}) y '{agent_phrase}' ({agent_result}) "
            "tienen el mismo resultado — falta frontera."
        )


class TestCapa1RobustnessForTechQuestions:
    """Asegura que Capa 1 capture suficientes casos de RAG."""

    @pytest.mark.parametrize("phrase", [
        "qué es",  # Más genérico
        "que es",
        "cómo funciona",
        "como funciona",
        "cuál es la diferencia",
    ])
    def test_rag_hint_keywords_capture_tech_questions(self, phrase):
        """Capa 1 debe interceptar estos patterns antes de Capa 2."""
        # Si el mensaje es MUY corto, puede que no sea útil,
        # pero no debe routear a 'identity'
        result = route_query(phrase)
        
        # Aceptamos 'rag', 'memory:*', o fallback a otro
        # Lo importante es NO llegar a 'identity' con un "qué es" genérico
        assert result != "identity", (
            f"Patrón técnico básico '{phrase}' routeó a 'identity' — "
            "Capa 1 (RAG_HINTS) debe interceptarlo."
        )
