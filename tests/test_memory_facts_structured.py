from app.intelligence import _decide_memory

def test_facts_estructurada_no_llama_llm(monkeypatch):
    monkeypatch.setattr("app.intelligence.get_project_facts",
                        lambda: {"current_phase": "fase 2", "stack": "python"})
    llamadas = {"n": 0}
    monkeypatch.setattr("app.intelligence._synthesize_memory_answer",
                        lambda *a, **kw: llamadas.update(n=llamadas["n"] + 1) or "LLM")
    respuesta = _decide_memory("¿cuál es la fase actual del proyecto?", ["project_facts"])
    assert llamadas["n"] == 0
    assert "fase 2" in respuesta

def test_facts_reasoning_si_usa_llm(monkeypatch):
    monkeypatch.setattr("app.intelligence.get_project_facts",
                        lambda: {"current_phase": "fase 2", "stack": "python"})
    llamadas = {"n": 0}
    monkeypatch.setattr("app.intelligence._synthesize_memory_answer",
                        lambda *a, **kw: llamadas.update(n=llamadas["n"] + 1) or "LLM")
    _decide_memory("¿por qué conviene que el proyecto siga en esta fase?", ["project_facts"])
    assert llamadas["n"] == 1