"""Verificación de fidelidad RAG.

Qué hace:
  1. Similitud semántica: compara la respuesta contra los chunks recuperados
     usando embeddings coseno. Si la respuesta no se parece lo suficiente
     a ningún chunk, se considera sospechosa.

  2. (NUEVO Día 2) Verificación de claims numéricos: si la respuesta
     contiene números concretos (enteros, decimales, porcentajes, años...),
     comprueba que cada número aparezca literalmente en alguno de los chunks
     fuente. Si un número no tiene respaldo literal, la respuesta se bloquea.

     Motivación: el LLM puede inventar cifras precisas ("10 456 líneas",
     "98,3 %") con alta similitud semántica si el chunk habla del mismo tema.
     La verificación literal corta esas alucinaciones numéricas.

     Excepciones intencionadas:
       - Números de 1 dígito (1-9): omitidos — demasiado comunes y ambiguos.
       - Años (1900-2099): omitidos — el LLM los deduce del contexto de forma
         legítima y rara vez son el dato clave que se quiere verificar.
       - Números en la pregunta original: omitidos — son referencia del usuario,
         no claims del LLM.

Optimización perf:
  Similitud: 2 llamadas HTTP (embed respuesta + embed contexto concatenado).
  Verificación numérica: 0 llamadas HTTP (comparación textual pura).

Umbral dinámico (ADR-004):
  Preguntas cortas (≤4 tokens): 0.40
  Preguntas normales (5-12 tokens): 0.55
  Preguntas largas (>12 tokens): 0.60

Limitaciones conocidas:
  - Respuestas muy cortas (<7 palabras) con chunks: bypass de similitud.
  - Respuestas muy cortas (<7 palabras) SIN chunks: bloqueadas (fix 6C).
  - Si Ollama está caído: retorna (True, 1.0) para no bloquear al usuario
    pero NO se loguea como éxito real (bypass de emergencia).

Contrato de retorno:
  verify_fidelity SIEMPRE retorna tuple[bool, float].
  NUNCA lanza excepciones.

Métricas disponibles:
  log_fidelity_failure()  → storage/logs/fidelity_failures.jsonl
  log_fidelity_success()  → storage/logs/fidelity_successes.jsonl
  fidelity_stats()        → dict con total_ok, total_blocked, rejection_rate
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path

FIDELITY_THRESHOLD  = 0.55
SHORT_ANSWER_WORDS  = 7
NO_EVIDENCE_MSG     = "No tengo suficiente evidencia en el contexto recuperado."

LOGS_DIR            = Path("storage") / "logs"
FAILURES_LOG        = LOGS_DIR / "fidelity_failures.jsonl"
SUCCESSES_LOG       = LOGS_DIR / "fidelity_successes.jsonl"

from app.semantic_cache import get_embedding

_MAX_CONTEXT_CHARS = 4000

# Números a ignorar en la verificación literal:
#   - un solo dígito (0-9): demasiado comunes y ambiguos
#   - años plausibles (1900-2099): el LLM los deduce legítimamente del contexto
_RE_SINGLE_DIGIT = re.compile(r'^\d$')
_RE_YEAR         = re.compile(r'^(19|20)\d{2}$')

# Patrón para extraer números de texto libre:
#   acepta enteros, decimales (con . o ,), porcentajes, miles con separador
#   Ejemplos: 10456  10.456  10,456  98.3  0.86  55%
_RE_NUMBERS = re.compile(r'\b\d[\d.,]*\b')


# ─────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────

def _cosine(a: list[float], b: list[float]) -> float:
    """Similitud coseno entre dos vectores. Retorna 0.0 si alguno es cero."""
    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _dynamic_threshold(question: str) -> float:
    """Umbral de fidelidad según longitud de la pregunta."""
    token_count = len(question.split())
    if token_count <= 4:
        return 0.40
    if token_count > 12:
        return 0.60
    return FIDELITY_THRESHOLD


def _extract_numbers(text: str) -> set[str]:
    """Extrae números significativos del texto, descartando dígitos solos y años."""
    raw = _RE_NUMBERS.findall(text)
    result: set[str] = set()
    for num in raw:
        clean = num.rstrip('.,')  # quitar puntuación final
        if _RE_SINGLE_DIGIT.match(clean):
            continue
        if _RE_YEAR.match(clean):
            continue
        result.add(clean)
    return result


def _check_numeric_claims(
    answer: str,
    chunks_texts: list[str],
    question: str = "",
) -> tuple[bool, str]:
    """Verifica que los números de la respuesta aparezcan literalmente en los chunks.

    Args:
        answer:       Respuesta generada por el LLM.
        chunks_texts: Lista de textos de los chunks fuente.
        question:     Pregunta original (para excluir números mencionados por el usuario).

    Returns:
        (ok, motivo)
          ok=True  → todos los números tienen respaldo o no hay números que verificar.
          ok=False → al menos un número no aparece en ningún chunk.
          motivo: string vacío si ok, descripción del primer fallo si no ok.
    """
    # Números que aporta el LLM en la respuesta
    answer_nums = _extract_numbers(answer)
    if not answer_nums:
        return True, ""

    # Excluir números que el usuario ya mencionó en la pregunta
    if question:
        question_nums = _extract_numbers(question)
        answer_nums -= question_nums

    if not answer_nums:
        return True, ""

    # Texto completo de todos los chunks (para búsqueda literal)
    corpus = " ".join(chunks_texts)

    for num in answer_nums:
        # Aceptamos variantes con/sin separador de miles y con coma/punto decimal
        # Ejemplo: "10456" busca también "10.456" y "10,456"
        variants = {num}
        digits_only = re.sub(r'[.,]', '', num)
        if len(digits_only) > 3:
            # añadir variante con punto cada 3 dígitos (separador de miles europeo)
            parts = []
            rev = digits_only[::-1]
            for i in range(0, len(rev), 3):
                parts.append(rev[i:i+3])
            variants.add('.'.join(p[::-1] for p in reversed(parts)))
            variants.add(','.join(p[::-1] for p in reversed(parts)))

        found = any(v in corpus for v in variants)
        if not found:
            return False, f"número '{num}' no encontrado en los chunks"

    return True, ""


# ─────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────

def log_fidelity_failure(question: str, score: float, threshold: float) -> None:
    """Registra un bloqueo en storage/logs/fidelity_failures.jsonl."""
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
        pass


def log_fidelity_success(
    question: str,
    score: float,
    threshold: float,
    method: str = "semantic",
) -> None:
    """Registra una respuesta que pasó fidelidad en storage/logs/fidelity_successes.jsonl.

    Args:
        question:  Pregunta original (truncada a 120 chars).
        score:     Similitud coseno alcanzada (1.0 para bypasses de respuesta corta).
        threshold: Umbral dinámico que se aplicó para esta pregunta.
        method:    Cómo pasó la verificación:
                     'semantic'      → similitud coseno >= umbral (paso 4)
                     'short_bypass'  → respuesta corta (<7 palabras) con chunks (paso 3)

    Junto con log_fidelity_failure(), permite calcular la tasa de rechazo real:
        tasa_rechazo = failures / (failures + successes)

    Never raises.
    """
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "question":  question[:120],
            "score":     round(score, 4),
            "threshold": threshold,
            "method":    method,
        }
        with SUCCESSES_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def fidelity_stats() -> dict:
    """Lee ambos logs y devuelve un resumen de fidelidad.

    Returns:
        dict con:
          total_ok:       Número de respuestas que pasaron.
          total_blocked:  Número de respuestas bloqueadas.
          total:          total_ok + total_blocked.
          rejection_rate: Tasa de rechazo (0.0–1.0). 0.0 si no hay datos.

    Never raises.

    Uso desde terminal:
        python -c "from app.fidelity_check import fidelity_stats; print(fidelity_stats())"

    Uso desde run_eval.py o !estado:
        from app.fidelity_check import fidelity_stats
        stats = fidelity_stats()
        print(f"Tasa de rechazo: {stats['rejection_rate']:.1%}")
    """
    def _count_lines(path: Path) -> int:
        if not path.exists():
            return 0
        try:
            return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        except Exception:
            return 0

    total_ok      = _count_lines(SUCCESSES_LOG)
    total_blocked = _count_lines(FAILURES_LOG)
    total         = total_ok + total_blocked
    rejection_rate = (total_blocked / total) if total > 0 else 0.0

    return {
        "total_ok":       total_ok,
        "total_blocked":  total_blocked,
        "total":          total,
        "rejection_rate": round(rejection_rate, 4),
    }


def verify_fidelity(answer: str, source_docs: list, question: str = "") -> tuple[bool, float]:
    """Verifica si la respuesta está soportada por los chunks recuperados.

    Pipeline de verificación (en orden):
      1. Sin chunks → bloquear.
      2. Verificación numérica literal (0 llamadas HTTP).
         Si la respuesta contiene números que no aparecen en los chunks, bloquear.
      3. Bypass de similitud para respuestas muy cortas (<7 palabras) CON chunks.
         Fix 6C: si no hay chunks_texts, también se bloquea aquí.
      4. Similitud semántica (2 llamadas HTTP): embed(respuesta) vs embed(contexto).

    Args:
        answer:      Texto generado por el LLM.
        source_docs: Lista de Document devuelta por el retriever.
        question:    Texto de la pregunta (para umbral dinámico y exclusión de números).

    Returns:
        tuple[bool, float]:
          True  → respuesta fiel, mostrar al usuario.
          False → respuesta sospechosa, reemplazar por NO_EVIDENCE_MSG.
          float → similitud coseno (0.0 si bloquó antes del paso semántico).

    Never raises.
    """
    threshold = _dynamic_threshold(question) if question else FIDELITY_THRESHOLD

    # ── 1. Sin chunks: bloquear siempre ───────────────────────────────────
    if not source_docs:
        print("[fidelity:block] sin chunks — bloqueando")
        log_fidelity_failure(question or answer, 0.0, threshold)
        return False, 0.0

    chunks_texts = [
        (doc.page_content if hasattr(doc, "page_content") else str(doc)).strip()
        for doc in source_docs
        if (doc.page_content if hasattr(doc, "page_content") else str(doc)).strip()
    ]
    if not chunks_texts:
        print("[fidelity:block] chunks sin contenido — bloqueando")
        log_fidelity_failure(question or answer, 0.0, threshold)
        return False, 0.0

    # ── 2. Verificación numérica literal (0 HTTP) ──────────────────────────
    numeric_ok, numeric_reason = _check_numeric_claims(answer, chunks_texts, question)
    if not numeric_ok:
        print(f"[fidelity:block:numeric] {numeric_reason} — bloqueando")
        log_fidelity_failure(question or answer, 0.0, threshold)
        return False, 0.0

    # ── 3. Bypass para respuestas muy cortas (fix 6C) ───────────────────────
    # Requiere chunks con contenido para permitir el bypass.
    # Una respuesta genérica como 'No lo sé' sin evidencia queda bloqueada.
    word_count = len(answer.split())
    if word_count < SHORT_ANSWER_WORDS:
        # chunks_texts ya está validado arriba — si llegamos aquí hay evidencia
        print(f"[fidelity:skip] respuesta corta con chunks ({word_count} palabras), se pasa")
        log_fidelity_success(question or answer, 1.0, threshold, method="short_bypass")
        return True, 1.0

    # ── 4. Similitud semántica (2 HTTP) ─────────────────────────────────
    try:
        ans_embedding = get_embedding(answer)
    except Exception:
        print("[fidelity:skip] error embed respuesta, se pasa")
        return True, 1.0  # bypass de emergencia — no se loguea como éxito real

    if ans_embedding is None:
        print("[fidelity:skip] Ollama no disponible, se pasa")
        return True, 1.0  # bypass de emergencia — no se loguea como éxito real

    contexto = " ".join(chunks_texts)[:_MAX_CONTEXT_CHARS]
    try:
        context_embedding = get_embedding(contexto)
    except Exception:
        print("[fidelity:skip] error embed contexto, se pasa")
        return True, 1.0  # bypass de emergencia — no se loguea como éxito real

    if context_embedding is None:
        print("[fidelity:skip] Ollama no disponible (contexto), se pasa")
        return True, 1.0  # bypass de emergencia — no se loguea como éxito real

    sim = _cosine(ans_embedding, context_embedding)

    if sim >= threshold:
        print(f"[fidelity:ok]  max_similitud={sim:.3f} (umbral={threshold})")
        log_fidelity_success(question or answer, sim, threshold, method="semantic")
        return True, sim

    print(f"[fidelity:low] max_similitud={sim:.3f} < umbral={threshold} — bloqueando")
    log_fidelity_failure(question or answer, sim, threshold)
    return False, sim
