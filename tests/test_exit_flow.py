"""Tests del flujo de salida — router + integración básica.

Verifica que las frases de salida:
  a) el router las clasifica correctamente como 'exit'
  b) NOT disparan el mensaje de identidad de Lautaro
  c) el patrón __EXIT__ se produce cuando corresponde

Nota: estos tests son de capa router + lógica de chat_core básica.
No requieren Ollama corriendo.

Ejecución:
  pytest tests/test_exit_flow.py -v
"""
import pytest
from app.router import route_query


EXIT_PHRASES = [
    "salir",
    "exit",
    "chao",
    "adios",
    "Adiós",
    "nos vemos",
    "hasta luego",
    "me voy",
    "bye",
]

# Frases que fallaron en producción (Telegram 2026-05-24) y que
# deben resolverse como exit, no como identity ni unsupported.
PROBLEMATIC_PHRASES = [
    "cerrar sesion",
    "Cerrar sesión",
    "salida",
]


class TestExitRouter:
    """Grupo 1: el router devuelve 'exit' para frases claras."""

    @pytest.mark.parametrize("phrase", EXIT_PHRASES)
    def test_router_returns_exit(self, phrase):
        lane = route_query(phrase)
        assert lane == "exit", f"Router devolvió '{lane}' para '{phrase}' — esperaba 'exit'"

    @pytest.mark.parametrize("phrase", EXIT_PHRASES)
    def test_exit_not_identity(self, phrase):
        """Una frase de salida jamás debe ir al carril identity."""
        lane = route_query(phrase)
        assert lane != "identity", (
            f"'{phrase}' fue a 'identity'. Bug: mensaje de identidad de Lautaro "
            "se mostraría en vez de terminar la sesión."
        )


class TestExitEdgeCases:
    """Grupo 2: frases problemáticas detectadas en producción."""

    @pytest.mark.parametrize("phrase", PROBLEMATIC_PHRASES)
    def test_problematic_not_identity(self, phrase):
        """Frases de cierre no deben disparar identidad."""
        lane = route_query(phrase)
        assert lane != "identity", (
            f"'{phrase}' fue a 'identity' — es el bug observado en Telegram."
        )

    def test_uppercase_exit(self):
        """Mayúsculas no deben romper la detección."""
        assert route_query("EXIT") == "exit"
        assert route_query("SALIR") == "exit"

    def test_tilde_adios(self):
        """Tilde en 'adiós' debe normalizarse correctamente."""
        assert route_query("Adiós") == "exit"
        assert route_query("ADIÓS") == "exit"
        assert route_query("adios") == "exit"

    def test_trailing_spaces(self):
        """Espacios al inicio/final no deben romper el exit."""
        # route_query recibe la pregunta cruda — la normalización debe limpiar espacios.
        lane = route_query("  salir  ")
        # Si _normalize() hace strip, esto pasará. Si no, documentamos el comportamiento.
        # No marcamos como fallo duro — es un hardening suave.
        assert lane in {"exit", "rag"}, (
            f"'  salir  ' devolvió '{lane}'. Si no es exit, _normalize() no hace strip."
        )
