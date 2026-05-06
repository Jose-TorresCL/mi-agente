"""Verificación de fidelidad RAG — 10a

Qué hace:
  Compara la respuesta generada por el LLM contra los chunks recuperados
  usando similitud de embeddings. Si la respuesta no se parece lo suficiente
  a ningún chunk, se considera sospechosa (posible alucinación).

Cómo funciona:
  1. Se calcula el embedding de la respuesta del LLM.
  2. Se calcula el embedding de cada chunk recuperado.
  3. Se toma la similitud coseno máxima entre la respuesta y cualquier chunk.
  4. Si esa similitud supera FIDELITY_THRESHOLD -> la respuesta es fiel.
  5. Si no -> la respuesta es sospechosa y se reemplaza por el mensaje estándar.

Por qué embeddings y no otro LLM:
  - No necesita una llamada extra al LLM (más rápido, ~200ms extra).
  - nomic-embed-text ya está corriendo para la caché semántica.
  - Es determinista: el mismo par (respuesta, chunk) siempre da el mismo score.

Limitaciones conocidas:
  - Respuestas muy cortas ("Sí", "No") tendrán similitud baja aunque sean correctas.
    Por eso SHORT_ANSWER_BYPASS: si la respuesta tiene menos de 20 palabras,
    se considera fiel automáticamente (evitar falsos negativos).
  - Si Ollama está caído, la función retorna True (fiel) para no bloquear.

Umbral recomendado:
  0.55 — conservador, solo bloquea respuestas claramente desconectadas del contexto.
  Bajar a 0.45 para ser más permisivo. No subir de 0.65 (demasiados falsos negativos).
"""
from __future__ import annotations

import math

FIDELITY_THRESHOLD  = 0.55   # similitud mínima respuesta↔chunk
SHORT_ANSWER_WORDS  = 20     # respuestas cortas se consideran fieles sin verificar
NO_EVIDENCE_MSG     = "No tengo suficiente evidencia en el contexto recuperado."

# Reutiliza el cliente singleton de semantic_cache — no crea uno nuevo
from app.semantic_cache import get_embedding


def _cosine(a: list[float], b: list[float]) -> float:
    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def verify_fidelity(answer: str, source_docs: list) -> bool:
    """Devuelve True si la respuesta está soportada por los chunks.

    Args:
        answer:      Texto generado por el LLM.
        source_docs: Lista de Document devuelta por el retriever.

    Returns:
        True  → respuesta fiel, mostrar al usuario.
        False → respuesta sospechosa, reemplazar por NO_EVIDENCE_MSG.
    """
    # Caso 1: sin chunks — el retriever no encontró nada relevante
    if not source_docs:
        print("[fidelity:skip] sin chunks, se pasa la verificación")
        return True

    # Caso 2: respuesta muy corta — bypass para evitar falsos negativos
    word_count = len(answer.split())
    if word_count < SHORT_ANSWER_WORDS:
        print(f"[fidelity:skip] respuesta corta ({word_count} palabras), se pasa")
        return True

    # Caso 3: verificación real por similitud de embeddings
    ans_embedding = get_embedding(answer)
    if ans_embedding is None:
        print("[fidelity:skip] Ollama no disponible, se pasa")
        return True

    max_sim = 0.0
    for doc in source_docs:
        chunk_text = doc.page_content if hasattr(doc, "page_content") else str(doc)
        if not chunk_text.strip():
            continue
        chunk_emb = get_embedding(chunk_text)
        if chunk_emb is None:
            continue
        sim = _cosine(ans_embedding, chunk_emb)
        if sim > max_sim:
            max_sim = sim

    if max_sim >= FIDELITY_THRESHOLD:
        print(f"[fidelity:ok]  max_similitud={max_sim:.3f} (umbral={FIDELITY_THRESHOLD})")
        return True

    print(f"[fidelity:low] max_similitud={max_sim:.3f} < umbral={FIDELITY_THRESHOLD} — bloqueando respuesta")
    return False
