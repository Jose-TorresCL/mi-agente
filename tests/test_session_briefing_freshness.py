from __future__ import annotations
from datetime import datetime, timedelta
from unittest.mock import patch

from app.memory_manager import get_session_briefing


def test_freshness_score_from_last_episode(monkeypatch):
    # Simular load_last_episode para que devuelva fecha hace 5 días
    five_days_ago = (datetime.now() - timedelta(days=5)).isoformat()
    monkeypatch.setattr('app.memory_store.load_last_episode', lambda: { 'date': five_days_ago })
    monkeypatch.setattr('app.memory_store.load_work_state', lambda: {})
    monkeypatch.setattr('app.memory_store.load_tasks', lambda: {})

    briefing = get_session_briefing()
    assert 'freshness_score' in briefing
    assert 0.8 < briefing['freshness_score'] <= 1.0
