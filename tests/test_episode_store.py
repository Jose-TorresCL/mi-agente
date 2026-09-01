"""Tests para episode_store.py — degradación sin infraestructura (T-0803171809).

Verifica que el índice episódico degrada limpio cuando Chroma no está
disponible o el JSON de episodios no existe. Contrato: never raises,
todo método público devuelve su fallback.
"""
from __future__ import annotations


def test_degradacion_sin_chroma(monkeypatch):
    """Con Chroma no disponible, todo degrada a fallback sin lanzar."""
    import app.episode_store as es
    monkeypatch.setattr(es, "_get_collection", lambda: None)
    assert es.search_episodes("algo") == []
    assert es.experience_lookup_with_score("algo") == (None, 0.0)
    assert es.index_episode({"date": "2026-01-01", "time": "00:00", "summary": "x"}) is False
    assert es.episode_index_stats()["available"] is False


def test_get_recent_episodes_sin_archivo(monkeypatch, tmp_path):
    """Sin episodic_memory.json devuelve lista vacía — el JSON es la fuente
    de verdad para episodios recientes y su ausencia no rompe nada."""
    import app.episode_store as es
    monkeypatch.setattr(es, "EPISODIC_MEMORY_FILE", tmp_path / "no_existe.json")
    assert es.get_recent_episodes(3) == []


def test_episode_to_doc_incluye_channel():
    from app.episode_store import _episode_to_doc
    _, metadata, _ = _episode_to_doc({
        "date": "2026-09-01", "time": "14:00", "turns": 4,
        "summary": "x", "channel": "telegram",
    })
    assert metadata["channel"] == "telegram"


def test_episode_to_doc_channel_default_unknown():
    from app.episode_store import _episode_to_doc
    _, metadata, _ = _episode_to_doc({
        "date": "2026-09-01", "time": "14:00", "turns": 1, "summary": "x",
    })
    assert metadata["channel"] == "unknown"


def test_save_episode_persiste_channel(monkeypatch, tmp_path):
    import json
    import app.memory_store as ms
    monkeypatch.setattr(ms, "EPISODIC_MEMORY_FILE", tmp_path / "ep.json")
    monkeypatch.setattr("app.episode_store.index_episode", lambda ep: True)
    ms.save_episode("resumen x", 4, channel="telegram")
    data = json.loads((tmp_path / "ep.json").read_text(encoding="utf-8"))
    assert data["episodes"][-1]["channel"] == "telegram"