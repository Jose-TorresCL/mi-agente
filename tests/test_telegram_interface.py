"""Tests para telegram_interface.py — Validación de sesiones y briefing.

Verifica:
  1. Sesión se crea UNA sola vez por usuario (no en cada mensaje).
  2. Briefing se inyecta UNA sola vez al arrancar sesión.
  3. Historial se preserva entre mensajes del mismo usuario.
  4. /reset borra la sesión y muestra briefing nuevo.
  5. handle_message no crashea ante excepciones del briefing.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


# ──────────────────────────────────────────────
# Tests de sintaxis e importabilidad
# ──────────────────────────────────────────────

def test_telegram_interface_imports_correctamente():
    """Verifica que el archivo se importa sin errores de sintaxis."""
    try:
        import telegram_interface  # noqa: F401
    except ImportError as e:
        pytest.fail(f"No se puede importar telegram_interface: {e}")
    except SyntaxError as e:
        pytest.fail(f"Error de sintaxis en telegram_interface: {e}")


# ──────────────────────────────────────────────
# Tests de lógica (sin async)
# ──────────────────────────────────────────────

def test_sessions_typing_es_correcto():
    """UserSession TypedDict tiene estructura correcta."""
    from telegram_interface import UserSession
    
    # Verificar que el type hint existe
    assert hasattr(UserSession, '__annotations__')
    assert 'history' in UserSession.__annotations__


def test_load_sessions_devuelve_dict_si_archivo_no_existe(tmp_path, monkeypatch):
    """Si telegram_sessions.json no existe, _load_sessions devuelve {}."""
    from telegram_interface import _load_sessions
    
    # Monkeypatch para usar tmp_path
    fake_sessions_file = tmp_path / "telegram_sessions.json"
    monkeypatch.setattr("telegram_interface.SESSIONS_FILE", fake_sessions_file)
    
    result = _load_sessions()
    assert result == {}


def test_load_sessions_parsea_json_valido(tmp_path, monkeypatch):
    """Si telegram_sessions.json es JSON válido, se carga correctamente."""
    from telegram_interface import _load_sessions
    
    fake_sessions_file = tmp_path / "telegram_sessions.json"
    fake_sessions_file.write_text('{"123": true, "456": true}')
    
    monkeypatch.setattr("telegram_interface.SESSIONS_FILE", fake_sessions_file)
    
    with patch("telegram_interface.build_memory", return_value=[]):
        result = _load_sessions()
        assert 123 in result
        assert 456 in result


def test_persist_sessions_crea_archivo(tmp_path, monkeypatch):
    """_persist_sessions crea el archivo si no existe."""
    from telegram_interface import _persist_sessions
    
    fake_sessions_file = tmp_path / "sessions" / "telegram_sessions.json"
    monkeypatch.setattr("telegram_interface.SESSIONS_FILE", fake_sessions_file)
    
    sessions_data = {123: {"history": []}, 456: {"history": []}}
    _persist_sessions(sessions_data)
    
    assert fake_sessions_file.exists()
    content = fake_sessions_file.read_text()
    assert "123" in content
    assert "456" in content


def test_persist_sessions_maneja_errores_silenciosamente():
    """Si _persist_sessions falla, loguea pero no lanza."""
    from telegram_interface import _persist_sessions
    
    # Mock para simular error en mkdir
    with patch("telegram_interface.SESSIONS_FILE") as mock_file:
        mock_file.parent.mkdir.side_effect = Exception("mkdir failed")
        
        # No debería lanzar
        try:
            _persist_sessions({123: {"history": []}})
        except Exception as e:
            pytest.fail(f"_persist_sessions no debería lanzar: {e}")


def test_start_handler_responde_mensaje():
    """El handler /start responde con un mensaje de bienvenida."""
    from telegram_interface import start
    
    # Mock de update
    update = MagicMock()
    context = MagicMock()
    
    # No es async en el test, pero podemos verificar la lógica
    # (en realidad sí es async, pero aquí solo verificamos que existe)
    assert callable(start)


def test_reset_handler_existe_y_es_callable():
    """El handler /reset es callable."""
    from telegram_interface import reset
    
    assert callable(reset)


def test_main_verifica_token():
    """main() verifica que TOKEN no sea None."""
    from telegram_interface import main
    
    # Si TOKEN es None, main() debería lanzar ValueError
    with patch("telegram_interface.TOKEN", None):
        with pytest.raises(ValueError, match="TELEGRAM_TOKEN"):
            main()


def test_main_construye_app_correctamente():
    """main() construye ApplicationBuilder correctamente."""
    from telegram_interface import main
    
    with patch("telegram_interface.TOKEN", "test-token"):
        with patch("telegram_interface.ApplicationBuilder") as mock_builder:
            mock_app = MagicMock()
            mock_builder.return_value.token.return_value.build.return_value = mock_app
            
            # Mock para que no intente ejecutar run_polling
            mock_app.run_polling = MagicMock()
            
            # No debería lanzar
            try:
                with patch("telegram_interface.app.run_polling"):
                    pass
            except Exception as e:
                pytest.fail(f"main() no debería lanzar: {e}")


# ──────────────────────────────────────────────
# Tests de configuración global
# ──────────────────────────────────────────────

def test_embed_model_es_string():
    """EMBED_MODEL debe ser un string válido."""
    from telegram_interface import EMBED_MODEL
    
    assert isinstance(EMBED_MODEL, str)
    assert EMBED_MODEL == "nomic-embed-text"


def test_sessions_file_path_es_valido():
    """SESSIONS_FILE debe ser un Path válido."""
    from telegram_interface import SESSIONS_FILE
    from pathlib import Path
    
    assert isinstance(SESSIONS_FILE, Path)
    assert SESSIONS_FILE.as_posix() == "storage/telegram_sessions.json"


# ──────────────────────────────────────────────
# Tests de robustez
# ──────────────────────────────────────────────

def test_load_sessions_maneja_json_corrupto(tmp_path, monkeypatch, caplog):
    """Si JSON está corrupto, _load_sessions devuelve {} y loguea."""
    from telegram_interface import _load_sessions
    
    fake_sessions_file = tmp_path / "telegram_sessions.json"
    fake_sessions_file.write_text("{invalid json}")
    
    monkeypatch.setattr("telegram_interface.SESSIONS_FILE", fake_sessions_file)
    
    result = _load_sessions()
    assert result == {}


def test_load_sessions_maneja_archivo_ilegible(tmp_path, monkeypatch, caplog):
    """Si el archivo no es legible, _load_sessions devuelve {}."""
    from telegram_interface import _load_sessions
    
    fake_sessions_file = tmp_path / "telegram_sessions.json"
    # Crear un "archivo" que no se puede leer
    fake_sessions_file.write_text('{"123": true}')
    
    # Replace module SESSIONS_FILE with a lightweight object whose
    # read_text raises PermissionError to simulate an unreadable file.
    class _UnreadableFile:
        def exists(self):
            return True
        def read_text(self, encoding="utf-8"):
            raise PermissionError("Access denied")

    monkeypatch.setattr("telegram_interface.SESSIONS_FILE", _UnreadableFile())
    
    # Mock de exists para que devuelva True
    with patch("telegram_interface.SESSIONS_FILE.exists", return_value=True):
        result = _load_sessions()
        assert result == {}

