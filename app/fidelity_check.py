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
    Por eso SHORT_ANSWER_BYPASS: si la respuesta tiene menos de 7 palabras,
    se considera fiel automáticamente (evitar falsos negativos).
  - Si Ollama está caído, la función retorna (True, 1.0) para no bloquear.

Umbral recomendado:
  0.55 — conservador, solo bloquea respuestas claramente desconectadas del contexto.
  Bajar a 0.45 para ser más permisivo. No subir de 0.65 (demasiados falsos negativos).

Cambios (fix 5b/5c):
  - SHORT_ANSWER_WORDS: 20 → 7  (solo bypass para "Sí", "No", respuestas de 1-2 palabras)
  - Sin chunks: ahora bloquea (False, 0.0) en lugar de pasar (True)

Contrato de retorno (nivel 1):
  verify_fidelity SIEMPRE retorna tuple[bool, float].
  NUNCA lanza excepciones — cualquier fallo interno retorna (True, 1.0).
"""
from __future__ import annotations

import math

FIDELITY_THRESHOLD  = 0.55   # similitud mínima respuesta↔chunk
SHORT_ANSWER_WORDS  = 7      # fix 5b: era 20 — solo bypass para respuestas de 1-2 palabras
NO_EVIDENCE_MSG     = "No tengo suficiente evidencia en el contexto recuperado."

# Reutiliza el cliente singleton de semantic_cache — no crea uno nuevo
from app.semantic_cache import get_embedding


def _cosine(a: list[float], b: list[float]) -> float:
    """Calcula similitud coseno entre dos vectores.

    Returns:
        float en [0.0, 1.0]. Retorna 0.0 si algún vector es cero.
    Never raises.
    """
    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def verify_fidelity(answer: str, source_docs: list) -> tuple[bool, float]:
    """Verifica si la respuesta está soportada por los chunks recuperados.

    Args:
        answer:      Texto generado por el LLM.
        source_docs: Lista de Document devuelta por el retriever.

    Returns:
        tuple[bool, float]:
          - bool  True  → respuesta fiel, mostrar al usuario.
                  False → respuesta sospechosa, reemplazar por NO_EVIDENCE_MSG.
          - float similitud máxima encontrada (0.0 si no aplica o sin chunks).

    Never raises: cualquier fallo interno retorna (True, 1.0) para no bloquear.
    """
    # Caso 1: sin chunks — fix 5c: bloqueamos, no hay evidencia posible
    if not source_docs:
        print("[fidelity:block] sin chunks recuperados — bloqueando respuesta")
        return False, 0.0

    # Caso 2: respuesta muy corta — bypass solo para "Sí", "No", etc.
    word_count = len(answer.split())
    if word_count < SHORT_ANSWER_WORDS:
        print(f"[fidelity:skip] respuesta corta ({word_count} palabras), se pasa")
        return True, 1.0

    # Caso 3: verificación real por similitud de embeddings
    try:
        ans_embedding = get_embedding(answer)
    except Exception:
        print("[fidelity:skip] error al obtener embedding de respuesta, se pasa")
        return True, 1.0

    if ans_embedding is None:
        print("[fidelity:skip] Ollama no disponible, se pasa")
        return True, 1.0

    max_sim = 0.0
    for doc in source_docs:
        chunk_text = doc.page_content if hasattr(doc, "page_content") else str(doc)
        if not chunk_text.strip():
            continue
        try:
            chunk_emb = get_embedding(chunk_text)
        except Exception:
            continue
        if chunk_emb is None:
            continue
        sim = _cosine(ans_embedding, chunk_emb)
        if sim > max_sim:
            max_sim = sim

    if max_sim >= FIDELITY_THRESHOLD:
        print(f"[fidelity:ok]  max_similitud={max_sim:.3f} (umbral={FIDELITY_THRESHOLD})")
        return True, max_sim

    print(f"[fidelity:low] max_similitud={max_sim:.3f} < umbral={FIDELITY_THRESHOLD} — bloqueando respuesta")
    return False, max_sim
