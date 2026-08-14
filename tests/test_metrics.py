"""
Tests para app/metrics.py — Fase 7A.

Verifica:
  1. record_turn() crea el archivo metrics.jsonl si no existe.
  2. Después de N llamadas hay exactamente N líneas.
  3. Cada línea es JSON válido con los campos obligatorios.
  4. cached=True se refleja correctamente.
  5. total_ms = retrieval_ms + llm_ms.
  6. channel se persiste (ej. 'telegram').
  7. Nunca lanza ante path inaccesible (directorio inexistente).
  8. get_metrics_summary() y reset_metrics() funcionan como contrato.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ──────────────────────────────────────────────
# Fixture: redirige _METRICS_FILE a un tmp_path
# ──────────────────────────────────────────────


@pytest.fixture()
def metrics_tmp(tmp_path, monkeypatch):
    """
    Redirige app.metrics para escribir en un directorio temporal.

    Esto evita tocar storage/logs/metrics.jsonl real durante los tests.
    """
    import app.metrics as m

    fake_file = tmp_path / "metrics.jsonl"
    monkeypatch.setattr(m, "_METRICS_FILE", fake_file)
    monkeypatch.setattr(m, "_METRICS_DIR", tmp_path)

    # Asegura que el acumulador de sesión empieza limpio
    m.reset_metrics()

    return fake_file


# ──────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────


def _read_single_entry(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8").strip()
    return json.loads(raw)


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
    entry = _read_single_entry(metrics_tmp)

    for campo in ("timestamp", "route", "retrieval_ms", "llm_ms", "total_ms", "tokens_est", "cached", "num_docs"):
        assert campo in entry, f"Falta campo: {campo}"


def test_cached_true_se_refleja(metrics_tmp):
    import app.metrics as m

    m.record_turn(route="rag", cached=True)
    entry = _read_single_entry(metrics_tmp)
    assert entry["cached"] is True


def test_graba_canal_telegram(metrics_tmp):
    import app.metrics as m

    m.record_turn(route="rag", channel="telegram")
    entry = _read_single_entry(metrics_tmp)
    assert entry["channel"] == "telegram"


def test_total_ms_suma_correcta(metrics_tmp):
    import app.metrics as m

    m.record_turn(route="rag", retrieval_ms=300, llm_ms=1500)
    entry = _read_single_entry(metrics_tmp)
    assert entry["total_ms"] == 1800


def test_never_raises_ante_ruta_invalida(monkeypatch):
    """
    Si _METRICS_FILE apunta a un lugar inaccesible, record_turn no lanza.

    Esto garantiza que la capa de métricas no rompe el agente,
    incluso si el disco o el path fallan.
    """
    import app.metrics as m

    monkeypatch.setattr(m, "_METRICS_FILE", Path("/ruta/inexistente/metrics.jsonl"))
    monkeypatch.setattr(m, "_METRICS_DIR", Path("/ruta/inexistente"))

    # No debe lanzar nunca
    m.record_turn(route="rag")


def test_get_metrics_summary_y_reset(metrics_tmp):
    """
    Verifica que el acumulador en memoria se actualiza y se puede resetear.
    """
    import app.metrics as m

    # Sin turnos: todo a cero
    summary = m.get_metrics_summary()
    assert summary["turns"] == 0
    assert summary["avg_llm_ms"] == 0
    assert summary["avg_ret_ms"] == 0
    assert summary["cache_hits"] == 0
    assert summary["cache_rate"] == 0.0
    assert summary["total_tokens_est"] == 0

    # Registrar algunos turnos
    m.record_turn(route="rag", retrieval_ms=100, llm_ms=900, tokens_est=50, cached=True)
    m.record_turn(route="rag", retrieval_ms=200, llm_ms=1100, tokens_est=100, cached=False)

    summary = m.get_metrics_summary()
    assert summary["turns"] == 2
    # Promedios aproximados
    assert summary["avg_llm_ms"] == (900 + 1100) // 2
    assert summary["avg_ret_ms"] == (100 + 200) // 2
    assert summary["cache_hits"] == 1
    assert summary["cache_rate"] == round(1 / 2, 4)
    assert summary["total_tokens_est"] == 150

    # Reset y comprobar que vuelve a cero
    m.reset_metrics()
    summary_after = m.get_metrics_summary()
    assert summary_after["turns"] == 0
    assert summary_after["total_tokens_est"] == 0