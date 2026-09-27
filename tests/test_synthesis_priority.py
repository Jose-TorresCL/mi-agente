def test_prompt_sintesis_exige_prioridad_explicita():
    from app.prompts import MEMORY_SYNTHESIS_PROMPT
    low = MEMORY_SYNTHESIS_PROMPT.lower()
    assert "prioridad" in low
    assert "alta" in low or "high" in low