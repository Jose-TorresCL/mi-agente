"""Motor RAG — recuperación y generación de respuestas documentales.

Responsabilidades:
- retrieve_context() → busca chunks relevantes en Chroma y devuelve texto + docs
- build_chain() → construye la cadena LangChain con prompt y LLM
- generate_raw() → genera texto libre con el LLM sin cadena RAG

El módulo no gestiona memoria ni historial — eso es responsabilidad de
intelligence.py y memory_manager.py. Solo accede a vectordb y al LLM.

Fix C2: cliente LLM unificado con generate_raw() — elimina duplicación
de lógica de HTTP entre build_chain y _decide_exit.

Fix memory_context: build_chain ya no inyecta memory_context via
concatenación de strings. El placeholder {memory_context} vive en
QA_SYSTEM_PROMPT y se resuelve en chain.invoke() desde intelligence.py.
Esto alinea el template con las 4 variables declaradas en prompts.py:
{memory_context}, {chat_history}, {context}, {question}.

Fix timeout: _LLM_TIMEOUT y _GENERATE_TIMEOUT subidos a 120s para alinear
con llm_client.py y evitar fallback en síntesis de memoria bajo carga CPU.

Fix think: qwen3:8b activa thinking mode por defecto, triplicando latencia
en CPU. Se desactiva con think=False en ChatOllama y en options de
generate_raw. num_ctx limitado a 4096 para reducir uso de memoria.
"""
from __future__ import annotations

import requests

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.config import MODEL_NAME, OLLAMA_URL
from app.logger import get_logger

log = get_logger(__name__)

_RETRIEVER_K = 4
_LLM_TIMEOUT = 120
_GENERATE_TIMEOUT = 120


def retrieve_context(query: str, vectordb) -> tuple[str, list]:
    """Recupera los chunks más relevantes de Chroma para la consulta dada.

    Usa el retriever de LangChain (similarity search, top-K=4) sobre el
    vectorstore Chroma. Concatena el contenido de los documentos recuperados
    en un bloque de texto listo para inyectar en el prompt del LLM.

    Args:
        query:    Pregunta del usuario en texto libre.
        vectordb: Instancia de Chroma (LangChain) ya inicializada.
                  Si es None o el retriever falla, devuelve strings vacíos.

    Returns:
        Tuple (context_text, source_docs):
        context_text → str con los chunks concatenados (separados por '\n\n').
                       String vacío si no se recuperó nada.
        source_docs  → list[Document] devuelto por el retriever.
                       Lista vacía si falla o vectordb es None.

    Nunca lanza excepciones — los errores se loguean como WARNING.
    """
    if vectordb is None:
        return "", []
    try:
        retriever = vectordb.as_retriever(search_kwargs={"k": _RETRIEVER_K})
        docs = retriever.invoke(query)
        context_text = "\n\n".join(
            doc.page_content for doc in docs if doc.page_content.strip()
        )
        return context_text, docs
    except Exception as exc:
        log.warning("retrieve_context falló: %s", exc)
        return "", []


def build_chain(system_prompt: str):
    """Construye la cadena LangChain (prompt + LLM + parser) para respuestas RAG.

    La cadena espera un dict con exactamente las claves declaradas en
    QA_SYSTEM_PROMPT (app/prompts.py):
    - 'memory_context' → contexto de memoria selectiva (puede ser string vacío)
    - 'chat_history'   → historial de conversación comprimido
    - 'context'        → texto de chunks recuperados de Chroma
    - 'question'       → pregunta del usuario

    IMPORTANTE: memory_context NO se inyecta aquí via concatenación. Vive
    como variable {memory_context} en el template para que chain.invoke()
    lo resuelva correctamente desde intelligence.py.

    Args:
        system_prompt: Prompt de sistema (desde app.prompts.QA_SYSTEM_PROMPT).
                       Debe contener los 4 placeholders mencionados arriba.

    Returns:
        Cadena LangChain invocable (.invoke(dict)) que devuelve el texto
        generado como string.

    El MODEL_NAME y OLLAMA_URL se leen de app.config.
    Timeout de generación: _LLM_TIMEOUT (120s).
    think=False desactiva el reasoning mode de qwen3 para reducir latencia.
    num_ctx=4096 limita la ventana de contexto para reducir uso de RAM.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "Historial:\n{chat_history}\n\nContexto:\n{context}\n\nPregunta: {question}"),
    ])
    llm = ChatOllama(
        model=MODEL_NAME,
        base_url=OLLAMA_URL,
        timeout=_LLM_TIMEOUT,
        num_ctx=4096,
        think=False,
    )
    return prompt | llm | StrOutputParser()


def generate_raw(
    prompt: str,
    temperature: float = 0.3,
    num_predict: int = 150,
    timeout: int = _GENERATE_TIMEOUT,
) -> str | None:
    """Genera texto libre con el LLM sin construir una cadena RAG completa.

    Llama directamente a la API HTTP de Ollama (/api/generate) con el prompt
    recibido. Usada para síntesis de memoria, resúmenes episódicos y
    cualquier generación que no requiera retrieval de documentos.

    Args:
        prompt:      Texto completo del prompt a enviar al modelo.
        temperature: Temperatura de muestreo (0.0 = determinista, 1.0 = creativo).
                     Por defecto 0.3 para respuestas equilibradas.
        num_predict: Límite de tokens a generar. Por defecto 150.
                     Bajar a 45 para resúmenes de sesión (D4-B).
        timeout:     Timeout HTTP en segundos. Por defecto 120s.

    Returns:
        String con la respuesta generada, sin espacios sobrantes.
        None si la llamada HTTP falla o Ollama no está disponible.

    Nunca lanza excepciones — los errores se loguean como WARNING.
    think=False desactiva el reasoning mode de qwen3 para reducir latencia.
    """
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": num_predict,
                    "num_ctx": 4096,
                },
                "think": False,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "").strip() or None
    except Exception as exc:
        log.warning("generate_raw falló: %s", exc)
        return None
