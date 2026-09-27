"""
Tests para show_metrics.py — tablero de métricas en consola.

Objetivos:
  1. _load_metrics() lee correctamente un metrics.jsonl de prueba.
  2. _show_table() no lanza excepciones con datos válidos.
  3. La salida incluye el conteo de turnos y los carriles esperados.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_metrics_example(path: Path) -> None:
    """
    Escribe un metrics.jsonl mínimo con 3 turnos de ejemplo:

      - rag       (con retrieval y llm)
      - memory    (solo llm, sin retrieval)
      - tool_analizar_mercado (con cached=True)
    """
    entries = [
        {
            "timestamp": "2026-08-10T15:00:00",
            "route": "rag",
            "intent_type": "rag:docs",
            "channel": "cli",
            "retrieval_ms": 300,
            "llm_ms": 1500,
            "total_ms": 1800,
            "tokens_est": 200,
            "cached": False,
            "num_docs": 4,
        },
        {
            "timestamp": "2026-08-10T15:01:00",
            "route": "memory",
            "intent_type": "memory:work_state",
            "channel": "cli",
            "retrieval_ms": 0,
            "llm_ms": 500,
            "total_ms": 500,
            "tokens_est": 80,
            "cached": False,
            "num_docs": 0,
        },
        {
            "timestamp": "2026-08-10T15:02:00",
            "route": "tool_analizar_mercado",
            "intent_type": "trading:analisis",
            "channel": "telegram",
            "retrieval_ms": 200,
            "llm_ms": 1200,
            "total_ms": 1400,
            "tokens_est": 150,
            "cached": True,
            "num_docs": 3,
        },
    ]
    path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
        encoding="utf-8",
    )


@pytest.fixture()
def metrics_file_tmp(tmp_path) -> Path:
    """
    Crea un metrics.jsonl de prueba en un directorio temporal.
    """
    metrics_path = tmp_path / "metrics.jsonl"
    _write_metrics_example(metrics_path)
    return metrics_path


def test_load_metrics_lee_tres_filas(metrics_file_tmp):
    """
    Verifica que _load_metrics() lee las 3 filas del archivo de prueba.
    """
    import show_metrics as sm

    rows = sm._load_metrics(metrics_file_tmp)
    assert len(rows) == 3

    routes = {row["route"] for row in rows}
    assert {"rag", "memory", "tool_analizar_mercado"} <= routes


def test_show_table_no_explota_y_muestra_conteo(metrics_file_tmp, capsys):
    """
    Verifica que _show_table() no lanza y que la salida incluye:

      - el número de turnos analizados,
      - los nombres de carril esperados.
    """
    import show_metrics as sm

    rows = sm._load_metrics(metrics_file_tmp)

    # No debe lanzar ninguna excepción
    sm._show_table(rows)

    captured = capsys.readouterr().out

    # Chequeos suaves para no acoplarse al formato exacto:
    assert "METRICAS - 3 turnos analizados" in captured
    assert "DISTRIBUCION POR CARRIL" in captured

    # Carriles esperados
    assert "rag" in captured
    assert "memory" in captured
    assert "tool_analizar_mercado" in captured

    # Sección de contexto por tipo de intención
    assert "CONTEXTO POR TIPO DE INTENCION" in captured