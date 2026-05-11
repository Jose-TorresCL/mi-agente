"""Verificación de fidelidad RAG — 10a

Qué hace:
  Compara la respuesta generada por el LLM contra los chunks recuperados
  usando similitud de embeddings. Si la respuesta no se parece lo suficiente
  a ningún chunk, se considera sospechosa (posible alucinación).

Cómo funciona:
  1. Se calcula el embedding de la respuesta del LLM.
  2. Se concatenan todos los chunks recuperados en un solo texto.
  3. Se calcula el embedding del contexto concatenado (1 sola llamada).
  4. Se toma la similitud coseno entre respuesta y contexto.
  5. Si supera el umbral dinámico → la respuesta es fiel.
  6. Si no → la respuesta es sospechosa y se reemplaza por NO_EVIDENCE_MSG.

Optimización perf (commit actual):
  Antes: 1 embed(respuesta) + N embeds(chunk_i) = 1+N llamadas HTTP
  Ahora: 1 embed(respuesta) + 1 embed(contexto_concat) = 2 llamadas HTTP
  Para k=5 chunks: de 6 llamadas a 2 (ahorro del 67%).

  Compensación: perdemos la similitud chunk-a-chunk pero ganamos velocidad.
  En la práctica la similitud contra el contexto completo es equivalente
  o mejor que el máximo individual, porque el LLM suele sintetizar varios chunks.

Umbral dinámico (fix ADR-004):
  Preguntas cortas (<=4 tokens): 0.40
  Preguntas normales (5-12 tokens): 0.55 — umbral base conservador.
  Preguntas largas (>12 tokens): 0.60

Limitaciones conocidas:
  - Respuestas muy cortas («Sí», «No») tendrán similitud baja aunque sean correctas.
    SHORT_ANSWER_BYPASS: si la respuesta tiene menos de 7 palabras, se pasa.
  - Si Ollama está caído, la función retorna (True, 1.0) para no bloquear.

Cambios (fix 5b/5c):
  - SHORT_ANSWER_WORDS: 20 → 7
  - Sin chunks: ahora bloquea (False, 0.0)

Cambios (B3):
  - log_fidelity_failure(): registra cada bloqueo en storage/logs/fidelity_failures.jsonl

Cambios (ADR-004):
  - Umbral dinámico según longitud de la pregunta (_dynamic_threshold)

Cambios (perf — commit actual):
  - verify_fidelity usa 1 embed para todos los chunks (contexto concatenado)
  - Reduce de 1+N a 2 llamadas HTTP por consulta RAG

Contrato de retorno (nivel 1):
  verify_fidelity SIEMPRE retorna tuple[bool, float].
  NUNCA lanza excepciones — cualquier fallo interno retorna (True, 1.0).
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

FIDELITY_THRESHOLD  = 0.55   # umbral BASE — preguntas de 5-12 tokens
SHORT_ANSWER_WORDS  = 7      # fix 5b: era 20 — solo bypass para respuestas de 1-2 palabras
NO_EVIDENCE_MSG     = "No tengo suficiente evidencia en el contexto recuperado."

LOGS_DIR            = Path("storage") / "logs"
FAILURES_LOG        = LOGS_DIR / "fidelity_failures.jsonl"

# Reutiliza el cliente singleton de semantic_cache — no crea uno nuevo
from app.semantic_cache import get_embedding

# Número máximo de caracteres del contexto concatenado que se pasa a embed.
# nomic-embed-text acepta hasta ~8192 tokens; 4000 chars ≈ 800-1000 tokens — margen seguro.
_MAX_CONTEXT_CHARS = 4000


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


def _dynamic_threshold(question: str) -> float:
    """Calcula el umbral de fidelidad según la longitud de la pregunta.

    Lógica:
      Preguntas muy cortas (<=4 tokens) como ¿qué es MMR? o define RAG
      generan respuestas con baja similitud léxica a los chunks aunque sean
      correctas. Bajamos el umbral para no bloquearlas.

      Preguntas largas (>12 tokens) aportan más contexto: la respuesta fiel
      debería parecerse más al chunk. Subimos levemente el umbral.

    Args:
        question: Texto de la pregunta del usuario.

    Returns:
        float: umbral a usar para esta pregunta específica.
    """
    token_count = len(question.split())
    if token_count <= 4:
        return 0.40   # pregunta muy corta — umbral permisivo
    if token_count > 12:
        return 0.60   # pregunta larga — umbral más estricto
    return FIDELITY_THRESHOLD  # 0.55 — rango normal


def log_fidelity_failure(question: str, score: float, threshold: float) -> None:
    """Registra un bloqueo de fidelidad en storage/logs/fidelity_failures.jsonl.

    Args:
        question:  Texto de la consulta del usuario (se trunca a 120 chars).
        score:     Similitud máxima encontrada (float en [0.0, 1.0]).
        threshold: Umbral dinámico que se aplicó en esta consulta.

    Never raises: cualquier fallo de escritura se descarta silenciosamente.
    """
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "question":  question[:120],
            "score":     round(score, 4),
            "threshold": threshold,
        }
        with FAILURES_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Never raises — el log es opcional, no bloquea al usuario


def verify_fidelity(answer: str, source_docs: list, question: str = "") -> tuple[bool, float]:
    """Verifica si la respuesta está soportada por los chunks recuperados.

    Optimización perf: en lugar de embeddear cada chunk individualmente
    (1+N llamadas HTTP), concatena todos los chunks en un solo texto y
    hace 1 sola llamada de embedding para el contexto (2 llamadas total).

    Args:
        answer:      Texto generado por el LLM.
        source_docs: Lista de Document devuelta por el retriever.
        question:    Texto de la pregunta (opcional, para umbral dinámico).

    Returns:
        tuple[bool, float]:
          - bool  True  → respuesta fiel, mostrar al usuario.
                  False → respuesta sospechosa, reemplazar por NO_EVIDENCE_MSG.
          - float similitud entre respuesta y contexto (0.0 si no aplica).

    Never raises: cualquier fallo interno retorna (True, 1.0) para no bloquear.
    """
    threshold = _dynamic_threshold(question) if question else FIDELITY_THRESHOLD

    # Caso 1: sin chunks — fix 5c: bloqueamos, no hay evidencia posible
    if not source_docs:
        print("[fidelity:block] sin chunks recuperados — bloqueando respuesta")
        log_fidelity_failure(answer, 0.0, threshold)
        return False, 0.0

    # Caso 2: respuesta muy corta — bypass solo para «Sí», «No», etc.
    word_count = len(answer.split())
    if word_count < SHORT_ANSWER_WORDS:
        print(f"[fidelity:skip] respuesta corta ({word_count} palabras), se pasa")
        return True, 1.0

    # Caso 3: verificación real por similitud de embeddings
    # — embed de la respuesta
    try:
        ans_embedding = get_embedding(answer)
    except Exception:
        print("[fidelity:skip] error al obtener embedding de respuesta, se pasa")
        return True, 1.0

    if ans_embedding is None:
        print("[fidelity:skip] Ollama no disponible, se pasa")
        return True, 1.0

    # — embed del contexto: concatenar todos los chunks en un solo texto (1 llamada)
    chunks_texts = [
        (doc.page_content if hasattr(doc, "page_content") else str(doc)).strip()
        for doc in source_docs
        if (doc.page_content if hasattr(doc, "page_content") else str(doc)).strip()
    ]
    if not chunks_texts:
        print("[fidelity:block] chunks sin contenido — bloqueando respuesta")
        log_fidelity_failure(answer, 0.0, threshold)
        return False, 0.0

    contexto = " ".join(chunks_texts)[:_MAX_CONTEXT_CHARS]

    try:
        context_embedding = get_embedding(contexto)
    except Exception:
        print("[fidelity:skip] error al embeddear contexto, se pasa")
        return True, 1.0

    if context_embedding is None:
        print("[fidelity:skip] Ollama no disponible al embeddear contexto, se pasa")
        return True, 1.0

    sim = _cosine(ans_embedding, context_embedding)

    if sim >= threshold:
        print(f"[fidelity:ok]  max_similitud={sim:.3f} (umbral={threshold})")
        return True, sim

    print(f"[fidelity:low] max_similitud={sim:.3f} < umbral={threshold} — bloqueando respuesta")
    log_fidelity_failure(answer, sim, threshold)
    return False, sim
