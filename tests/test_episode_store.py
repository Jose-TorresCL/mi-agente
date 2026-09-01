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