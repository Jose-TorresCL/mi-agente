"""Contrato de configuración de la integración bot_trading (ADR-010, riesgo R4).

Qué protege esta batería:
  1. `BOT_TRADING_PATH` nunca es vacío (si lo fuera, tools_trading.py
     ejecutaría "" como comando dentro de un subprocess: fallo tardío y opaco).
  2. Las rutas derivadas (python del bot y script) cuelgan de esa raíz.
  3. La variable de entorno realmente sobrescribe el valor por defecto.
  4. `BOT_TRADING_TIMEOUT` es un entero positivo y tolera basura en el entorno.
  5. Nadie volvió a hardcodear la ruta absoluta dentro de `app/`.

Ejecutar:  pytest tests/test_config_bot_trading.py -v
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

from app import config


def test_bot_trading_path_no_es_vacio():
    assert str(config.BOT_TRADING_PATH).strip(), "BOT_TRADING_PATH no puede ser vacío"
    assert isinstance(config.BOT_TRADING_PATH, Path)


def test_rutas_derivadas_cuelgan_de_la_raiz():
    raiz = str(config.BOT_TRADING_PATH)
    assert raiz in str(config.BOT_TRADING_PYTHON)
    assert raiz in str(config.BOT_TRADING_SCRIPT)
    assert str(config.BOT_TRADING_SCRIPT).endswith("consulta_mercado.py")


def test_variable_de_entorno_sobrescribe(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TRADING_PATH", str(tmp_path))
    recargado = importlib.reload(config)
    try:
        assert recargado.BOT_TRADING_PATH == tmp_path
        assert recargado.BOT_TRADING_PYTHON.is_relative_to(tmp_path)
    finally:
        monkeypatch.delenv("BOT_TRADING_PATH", raising=False)
        importlib.reload(config)


def test_timeout_es_entero_positivo():
    assert isinstance(config.BOT_TRADING_TIMEOUT, int)
    assert config.BOT_TRADING_TIMEOUT > 0


@pytest.mark.parametrize(
    "valor,esperado",
    [("30", 30), ("", 15), (None, 15), ("abc", 15), ("-5", 15), ("0", 15)],
)
def test_timeout_tolera_valores_invalidos(valor, esperado):
    assert config._leer_timeout(valor) == esperado


def test_bot_trading_disponible_no_revienta():
    # En CI el bot no existe: debe responder False, nunca lanzar.
    assert config.bot_trading_disponible() in (True, False)


def test_ningun_modulo_hardcodea_la_ruta_absoluta():
    """La ruta solo puede aparecer en config.py y .env.example."""
    culpables = []
    for archivo in Path("app").rglob("*.py"):
        if archivo.name == "config.py":
            continue
        texto = archivo.read_text(encoding="utf-8", errors="ignore")
        if "Proyectos\\bot_trading" in texto or "Proyectos/bot_trading" in texto:
            culpables.append(str(archivo))
    assert not culpables, f"Ruta absoluta hardcodeada en: {culpables}"
