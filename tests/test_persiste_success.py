from pathlib import Path
import json

import pytest


@pytest.fixture
def metrics_tmp(tmp_path, monkeypatch):
    import app.metrics as m

    metrics_dir = tmp_path / "logs"
    metrics_file = metrics_dir / "metrics.jsonl"

    monkeypatch.setattr(m, "_METRICS_DIR", metrics_dir)
    monkeypatch.setattr(m, "_METRICS_FILE", metrics_file)

    m.reset_metrics()

    return metrics_file


def _read_entries(metrics_file: Path) -> list[dict]:
    if not metrics_file.exists():
        pytest.fail("No se creó el archivo de métricas")

    lines = metrics_file.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_persiste_fidelity_status(metrics_tmp):
    import app.metrics as m

    m.record_turn(
        route="rag",
        intent_type="rag",
        fidelity_status="verified",
        cached=True,
        num_docs=3,
    )

    entries = _read_entries(metrics_tmp)

    assert len(entries) == 1

    entry = entries[0]
    assert entry["route"] == "rag"
    assert entry["intent_type"] == "rag"
    assert entry["fidelity_status"] == "verified"
    assert entry["cached"] is True
    assert entry["num_docs"] == 3


def test_persiste_fidelity_status_default(metrics_tmp):
    import app.metrics as m

    m.record_turn(
        route="memory",
        intent_type="memory",
    )

    entries = _read_entries(metrics_tmp)

    assert len(entries) == 1

    entry = entries[0]
    assert entry["route"] == "memory"
    assert entry["intent_type"] == "memory"
    assert entry["fidelity_status"] == "not_applicable"


def test_record_turn_agrega_una_linea_por_turno(metrics_tmp):
    import app.metrics as m

    m.record_turn(
        route="memory",
        intent_type="memory",
    )
    m.record_turn(
        route="rag",
        intent_type="rag",
        fidelity_status="verified",
    )

    entries = _read_entries(metrics_tmp)

    assert len(entries) == 2
    assert entries[0]["route"] == "memory"
    assert entries[1]["route"] == "rag"

def test_total_ms_se_persiste_como_suma(metrics_tmp):
    import app.metrics as m

    m.record_turn(
        route="rag",
        intent_type="rag",
        retrieval_ms=200,
        llm_ms=800,
    )

    entry = _read_entries(metrics_tmp)[0]

    assert entry["retrieval_ms"] == 200
    assert entry["llm_ms"] == 800
    assert entry["total_ms"] == 1000