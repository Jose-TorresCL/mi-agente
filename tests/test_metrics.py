"""Tests para app/metrics.py — Fase 7A.

Verifica:
  1. record_turn() crea el archivo metrics.jsonl si no existe.
  2. Después de N llamadas hay exactamente N líneas.
  3. Cada línea es JSON válido con los campos obligatorios.
  4. cached=True se refleja correctamente.
  5. Never raises ante path inaccesible (directorio inexistente).
"""
from __future__ import annotations

import json
import importlib
import sys
from pathlib import Path

import pytest


# ──────────────────────────────────────────────
# Fixture: redirige _METRICS_FILE a un tmp_path
# ──────────────────────────────────────────────

@pytest.fixture()
def metrics_tmp(tmp_path, monkeypatch):
    """Redirige metrics.py para escribir en un directorio temporal."""
    # Asegura que app/metrics.py se importa desde el workspace real
    import app.metrics as m
    fake_file = tmp_path / "metrics.jsonl"
    monkeypatch.setattr(m, "_METRICS_FILE", fake_file)
    monkeypatch.setattr(m, "_METRICS_DIR", tmp_path)
    return fake_file


# ──────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────

def test_crea_archivo_si_no_existe(metrics_tmp):
    import app.metrics as m
    assert not metrics_tmp.exists()
    m.record_turn(route="rag")
    assert metrics_tmp.exists()


def test_n_turnos_n_lineas(metrics_tmp):
    import app.metrics as m
    for i in range(10):
        m.record_turn(route="rag", retrieval_ms=i * 10, llm_ms=i * 50)
    lines = metrics_tmp.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 10


def test_campos_obligatorios(metrics_tmp):
    import app.metrics as m
    m.record_turn(route="memory", llm_ms=230, tokens_est=80)
    raw = metrics_tmp.read_text(encoding="utf-8").strip()
    entry = json.loads(raw)
    for campo in ("timestamp", "route", "retrieval_ms", "llm_ms", "total_ms", "tokens_est", "cached"):
        assert campo in entry, f"Falta campo: {campo}"


def test_cached_true_se_refleja(metrics_tmp):
    import app.metrics as m
    m.record_turn(route="rag", cached=True)
    entry = json.loads(metrics_tmp.read_text(encoding="utf-8").strip())
    assert entry["cached"] is True


def test_total_ms_suma_correcta(metrics_tmp):
    import app.metrics as m
    m.record_turn(route="rag", retrieval_ms=300, llm_ms=1500)
    entry = json.loads(metrics_tmp.read_text(encoding="utf-8").strip())
    assert entry["total_ms"] == 1800


def test_never_raises_ante_ruta_invalida(monkeypatch):
    """Si _METRICS_FILE apunta a un lugar inaccesible, record_turn no lanza."""
    import app.metrics as m
    monkeypatch.setattr(m, "_METRICS_FILE", Path("/ruta/inexistente/metrics.jsonl"))
    monkeypatch.setattr(m, "_METRICS_DIR", Path("/ruta/inexistente"))
    # No debe lanzar nunca
    m.record_turn(route="rag")
