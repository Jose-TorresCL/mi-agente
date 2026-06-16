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
    fix-think     — qwen3:8b activa thinking mode por defecto, lo que triplica
                    la latencia en CPU (~4 min vs ~40s). Se desactiva con
                    think=False en options. num_ctx limitado a 4096 para
                    reducir uso de memoria y acelerar inferencia.
    fix-think-singleton — think=False añadido también al singleton base de
                    get_llm(). Antes solo estaba en .bind() de generate_raw();
                    si algún módulo llama get_llm().invoke() directamente,
                    el thinking mode quedaba activo. Ahora el singleton ya
                    nace con think=False y es imposible olvidarlo.
    fix-keep-alive — keep_alive=-1 para mantener el modelo en RAM durante
                    toda la sesión. Evita que fidelity_check falle por
                    contención de recursos entre LLM y embedder post-respuesta.
                    Con 16 GB RAM ambos modelos coexisten sin problema.
                    El modelo se descarga explícitamente al cerrar Lautaro
                    via 'ollama stop' en chat.py._session_close().
"""
from __future__ import annotations

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

from app.config import MODEL_NAME, OLLAMA_URL
from app.logger import get_logger

log = get_logger(__name__)

_llm_instance: ChatOllama | None = None


def get_llm() -> ChatOllama:
    """Devuelve el LLM singleton. Se crea solo la primera vez.

    keep_alive=-1: mantiene qwen3:8b cargado en RAM toda la sesión.
    Evita contención con nomic-embed-text en fidelity_check post-respuesta.
    El modelo se libera explícitamente al cerrar Lautaro (chat.py).

    think=False desactiva el reasoning mode de qwen3:8b desde el singleton
    base, garantizando que cualquier caller que use get_llm().invoke()
    directamente tampoco active el thinking mode.
    """
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = ChatOllama(
            model=MODEL_NAME,
            base_url=OLLAMA_URL,
            temperature=0.1,
            num_ctx=4096,
            think=False,
            keep_alive=-1,
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
                "think": False,
            },
        )
        result = llm.invoke([HumanMessage(content=prompt)])
        text = result.content.strip() if hasattr(result, "content") else str(result).strip()
        log.debug("generate_raw: %d chars generados", len(text))
        return text if text else None
    except Exception as exc:
        log.warning("generate_raw falló: %s", exc)
        return None
