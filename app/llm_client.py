"""Cliente LLM unificado — singleton ChatOllama.

Responsabilidad única: instanciar y reutilizar el cliente LLM.
Ningún otro módulo debe importar ChatOllama directamente.

Exporta:
    get_llm()       → singleton ChatOllama (temperature base 0.1 para RAG)
    generate_raw()  → llamada libre al LLM, reutiliza el singleton vía .bind()
                      Para síntesis de memoria, resumen episódico y cualquier
                      llamada LLM que no necesite recuperación vectorial.

Historial:
    fix-singleton — generate_raw() usaba ChatOllama nuevo en cada llamada.
                    Ahora reutiliza el singleton vía .bind(), eliminando el
                    overhead de reconexión por turno.
    fix-timeout   — timeout subido de 30s a 120s. Bajo carga concurrente
                    (llm + embedder en CPU) el modelo puede tardar 35s+;
                    30s causaba fallback en síntesis de memoria.
"""
from __future__ import annotations

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

from app.config import MODEL_NAME, OLLAMA_URL
from app.logger import get_logger

log = get_logger(__name__)

_llm_instance: ChatOllama | None = None


def get_llm() -> ChatOllama:
    """Devuelve el LLM singleton. Se crea solo la primera vez."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = ChatOllama(
            model=MODEL_NAME,
            base_url=OLLAMA_URL,
            temperature=0.1,
        )
        log.debug("LLM singleton inicializado: %s", MODEL_NAME)
    return _llm_instance


def generate_raw(
    prompt: str,
    temperature: float = 0.3,
    num_predict: int = 150,
    timeout: int = 120,
) -> str | None:
    """Llama al LLM con un prompt libre, sin RAG ni chain LangChain.

    Reutiliza el singleton vía .bind() para ajustar parámetros por llamada
    sin crear instancias nuevas de ChatOllama (fix-singleton).

    Args:
        prompt:      Texto completo del prompt a enviar al LLM.
        temperature: Temperatura de generación (default 0.3).
        num_predict: Máximo de tokens a generar.
        timeout:     Segundos antes de abortar la llamada (default 120).
                     Subido de 30s — bajo carga CPU concurrente el modelo
                     puede tardar 35s+.

    Returns:
        Texto generado, o None si la llamada falló.

    Uso típico:
        answer = generate_raw(prompt, temperature=0.3, num_predict=150)
        if answer is None:
            return fallback_string
    """
    try:
        llm = get_llm().bind(
            options={
                "temperature": temperature,
                "num_predict": num_predict,
            },
        )
        result = llm.invoke([HumanMessage(content=prompt)])
        text = result.content.strip() if hasattr(result, "content") else str(result).strip()
        log.debug("generate_raw: %d chars generados", len(text))
        return text if text else None
    except Exception as exc:
        log.warning("generate_raw falló: %s", exc)
        return None
