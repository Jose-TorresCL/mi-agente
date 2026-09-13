def test_qa_prompt_contains_required_placeholders():
    from app.prompts import QA_SYSTEM_PROMPT

    required = ["{question}", "{context}", "{chat_history}", "{memory_context}"]
    for placeholder in required:
        assert placeholder in QA_SYSTEM_PROMPT


def test_memory_synthesis_prompt_contains_expected_contract():
    from app.prompts import MEMORY_SYNTHESIS_PROMPT

    required = ["{context_text}", "{chat_history}", "{question}"]
    for placeholder in required:
        assert placeholder in MEMORY_SYNTHESIS_PROMPT


def test_fixed_messages_are_exposed_and_contextual():
    from app.prompts import (
        MEMORY_NOT_FOUND_MSG,
        UNSUPPORTED_MSG,
        build_memory_not_found_msg,
    )

    assert MEMORY_NOT_FOUND_MSG
    assert UNSUPPORTED_MSG
    assert "tareas pendientes" in build_memory_not_found_msg("qué tareas tengo pendientes?", "tasks")
    assert "documentación" in UNSUPPORTED_MSG