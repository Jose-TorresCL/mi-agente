from __future__ import annotations
from datetime import datetime, timedelta
from unittest.mock import patch

from app.memory_manager import get_session_briefing


def test_freshness_score_from_last_episode(monkeypatch):
    # Simular load_last_episode para que devuelva fecha hace 5 días
    five_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    monkeypatch.setattr('app.memory_manager.load_last_episode', lambda: { 'date': five_days_ago })
    monkeypatch.setattr('app.memory_manager.load_work_state', lambda: {})
    monkeypatch.setattr('app.memory_manager.load_tasks', lambda: {})

    briefing = get_session_briefing()
    assert 'freshness_score' in briefing
    # Cinco días = sesión retomable, pero ya no "muy fresca".
    # freshness_score solo informa el briefing; no bloquea memoria,
    # routing ni recuperación de episodios.
    assert 0.75 < briefing["freshness_score"] <= 0.85