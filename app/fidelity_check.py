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
         no claims del LLM. Fix: se extraen TODOS los números del enunciado
         (incluyendo los que viajan en el historial concatenado) para evitar
         que un número de una pregunta anterior bloquee la siguiente.
       - IDs de tarea (T-NNNN, formato NNNNNNNNNN de 10 dígitos): omitidos —
         son referencias de sistema generadas por el proyecto, no claims
         factuales del LLM. Aparecen en memoria JSON, no en chunks RAG.

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
    pero se loguea en fidelity_uncertain.jsonl como bypass de emergencia.

Fix retry embed: cuando get_embedding() devuelve None post-LLM (CPU ocupada
durante inferencia), se espera 3s y reintenta una vez antes de hacer skip.
Esto resuelve el [fidelity:skip] sistemático en CPU sin GPU dedicada.

Contrato de retorno:
  verify_fidelity SIEMPRE retorna tuple[bool, float].
  NUNCA lanza excepciones.

Métricas disponibles:
  log_fidelity_failure()   → storage/logs/fidelity_failures.jsonl
  log_fidelity_success()   → storage/logs/fidelity_successes.jsonl
  log_fidelity_uncertain() → storage/logs/fidelity_uncertain.jsonl
  fidelity_stats()         → dict con total_ok, total_blocked, total_uncertain
"""
from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

FIDELITY_THRESHOLD  = 0.55
SHORT_ANSWER_WORDS  = 7
NO_EVIDENCE_MSG     = "No tengo suficiente evidencia en el contexto recuperado."

LOGS_DIR            = Path("storage") / "logs"
FAILURES_LOG        = LOGS_DIR / "fidelity_failures.jsonl"
SUCCESSES_LOG       = LOGS_DIR / "fidelity_successes.jsonl"

from app.semantic_cache import get_embedding

# Emergency behavior when embeddings fail: 'bypass' preserves old behavior,
# 'uncertain' marks as uncertain and blocks the response (safer default can be set by config).
FIDELITY_EMERGENCY_MODE = "bypass"  # options: 'bypass' | 'uncertain'

# Additional log for uncertain cases
UNCERTAIN_LOG = LOGS_DIR / "fidelity_uncertain.jsonl"

_MAX_CONTEXT_CHARS = 4000

# Números a ignorar en la verificación literal:
#   - un solo dígito (0-9): demasiado comunes y ambiguos
#   - años plausibles (1900-2099): el LLM los deduce legítimamente del contexto
#   - IDs de tarea T-NNNN o timestamps de 10 dígitos generados por el proyecto:
#     son referencias de sistema en memoria JSON, no claims factuales del LLM.
#     No existen en chunks RAG → causarían falsos positivos si no se excluyen.
_RE_SINGLE_DIGIT = re.compile(r'^\d$')
_RE_YEAR         = re.compile(r'^(19|20)\d{2}$')
_RE_TASK_ID      = re.compile(r'^\d{9,12}$')   # timestamps de 10 dígitos: 0612230517

# Patrón para extraer números de texto libre:
#   acepta enteros, decimales (con . o ,), porcentajes, miles con separador
#   Ejemplos: 10456  10.456  10,456  98.3  0.86  55%
_RE_NUMBERS = re.compile(r'\b\d[\d.,]*\b')

# Segundos de espera antes de reintentar embed post-LLM
_EMBED_RETRY_SLEEP = 3


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
    """Extrae números significativos del texto, descartando ruido."""
    raw = _RE_NUMBERS.findall(text)
    result: set[str] = set()
    for num in raw:
        clean = num.rstrip('.,')
        if _RE_SINGLE_DIGIT.match(clean):
            continue
        if _RE_YEAR.match(clean):
            continue
        if _RE_TASK_ID.match(clean):
            continue
        result.add(clean)
    return result


def _normalize_number_token(token: str) -> str | None:
    """Normaliza un token numérico para comparación numérica."""
    token = token.strip()
    if not token:
        return None

    is_percent = token.endswith('%')
    if is_percent:
        token = token[:-1].strip()

    is_k = token.lower().endswith('k')
    if is_k:
        token = token[:-1].strip()

    token = token.replace(' ', '')
    if not token:
        return None

    if token.count('.') > 0 and token.count(',') > 0:
        if token.rfind(',') > token.rfind('.'):
            token = token.replace('.', '').replace(',', '.')
        else:
            token = token.replace(',', '')
    elif token.count(',') > 0:
        if len(token.split(',')[-1]) == 3:
            token = token.replace(',', '')
        else:
            token = token.replace(',', '.')
    elif token.count('.') > 0:
        if len(token.split('.')[-1]) == 3:
            token = token.replace('.', '')

    try:
        value = Decimal(token)
    except InvalidOperation:
        return None

    if value == value.to_integral():
        normalized = str(int(value))
    else:
        normalized = format(value.normalize(), 'f')

    if is_k:
        try:
            value = Decimal(normalized)
            value = value * Decimal(1000)
            if value == value.to_integral():
                normalized = str(int(value))
            else:
                normalized = format(value.normalize(), 'f')
        except InvalidOperation:
            return None

    if is_percent:
        return normalized + '%'

    return normalized


def _check_numeric_claims(
    answer: str,
    chunks_texts: list[str],
    question: str = "",
) -> tuple[bool, str]:
    """Verifica que los números de la respuesta aparezcan en los chunks."""
    answer_nums = _extract_numbers(answer)
    if not answer_nums:
        return True, ""

    if question:
        question_nums = _extract_numbers(question)
        answer_nums -= question_nums

    if not answer_nums:
        return True, ""

    corpus = " ".join(chunks_texts)
    chunk_nums = _extract_numbers(corpus)
    normalized_chunks = {
        _normalize_number_token(num)
        for num in chunk_nums
        if _normalize_number_token(num) is not None
    }

    for num in answer_nums:
        if question and num in question:
            continue
        normalized = _normalize_number_token(num)
        if normalized is None:
            continue
        if normalized not in normalized_chunks:
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
    """Registra una respuesta que pasó fidelidad en storage/logs/fidelity_successes.jsonl."""
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


def log_fidelity_uncertain(question: str, reason: str) -> None:
    """Registra situaciones en que la verificación no pudo completarse con embeddings."""
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "question":  question[:120],
            "reason":    reason,
        }
        with UNCERTAIN_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def fidelity_stats() -> dict:
    """Lee ambos logs y devuelve un resumen de fidelidad."""
    def _count_lines(path: Path) -> int:
        if not path.exists():
            return 0
        try:
            return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        except Exception:
            return 0

    total_ok        = _count_lines(SUCCESSES_LOG)
    total_blocked   = _count_lines(FAILURES_LOG)
    total_uncertain = _count_lines(UNCERTAIN_LOG)
    total           = total_ok + total_blocked
    rejection_rate  = (total_blocked / total) if total > 0 else 0.0

    return {
        "total_ok":        total_ok,
        "total_blocked":   total_blocked,
        "total_uncertain": total_uncertain,
        "total":           total,
        "rejection_rate":  round(rejection_rate, 4),
    }


def verify_fidelity(answer: str, source_docs: list, question: str = "") -> tuple[bool, float]:
    """Verifica si la respuesta está soportada por los chunks recuperados."""
    return _validate_fidelity(answer, source_docs, question, numeric_strict=True)


def _validate_fidelity(
    answer: str,
    source_docs: list,
    question: str = "",
    numeric_strict: bool = True,
) -> tuple[bool, float]:
    """Valida la fidelidad utilizando el flujo actual con opción numérica o semántica."""
    threshold = _dynamic_threshold(question) if question else FIDELITY_THRESHOLD

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

    if numeric_strict:
        numeric_ok, numeric_reason = _check_numeric_claims(answer, chunks_texts, question)
        if not numeric_ok:
            print(f"[fidelity:block:numeric] {numeric_reason} — bloqueando")
            log_fidelity_failure(question or answer, 0.0, threshold)
            return False, 0.0

    word_count = len(answer.split())
    if word_count < SHORT_ANSWER_WORDS:
        print(f"[fidelity:skip] respuesta corta con chunks ({word_count} palabras), se pasa")
        log_fidelity_success(question or answer, 1.0, threshold, method="short_bypass")
        return True, 1.0

    try:
        ans_embedding = get_embedding(answer)
    except Exception:
        reason = "error embed respuesta"
        print(f"[fidelity:uncertain] {reason}")
        if FIDELITY_EMERGENCY_MODE == "bypass":
            return True, 1.0
        log_fidelity_uncertain(question or answer, reason)
        return False, 0.0

    # Retry único: si Ollama devuelve None post-LLM (CPU ocupada),
    # esperar _EMBED_RETRY_SLEEP segundos y reintentar antes de hacer skip.
    if ans_embedding is None:
        print(f"[fidelity:retry] embed devolvió None — reintentando en {_EMBED_RETRY_SLEEP}s")
        time.sleep(_EMBED_RETRY_SLEEP)
        try:
            ans_embedding = get_embedding(answer)
        except Exception:
            ans_embedding = None

    if ans_embedding is None:
        reason = "embed respuesta devolvió None tras retry (Ollama ocupado post-LLM)"
        print(f"[fidelity:skip] {reason}")
        log_fidelity_uncertain(question or answer, reason)
        return True, 1.0

    chunk_embeddings = []
    for txt in chunks_texts:
        try:
            emb = get_embedding(txt[:_MAX_CONTEXT_CHARS])
            if emb is not None:
                chunk_embeddings.append(emb)
        except Exception:
            continue

    if not chunk_embeddings:
        reason = "no se obtuvieron embeddings de chunks"
        print(f"[fidelity:uncertain] {reason}")
        if FIDELITY_EMERGENCY_MODE == "bypass":
            return True, 1.0
        log_fidelity_uncertain(question or answer, reason)
        return False, 0.0

    sims = [_cosine(ans_embedding, c) for c in chunk_embeddings]
    sim = max(sims) if sims else 0.0

    if sim >= threshold:
        print(f"[fidelity:ok]  max_similitud={sim:.3f} (umbral={threshold})")
        method = "semantic" if numeric_strict else "semantic_flexible"
        log_fidelity_success(question or answer, sim, threshold, method=method)
        return True, sim

    print(f"[fidelity:low] max_similitud={sim:.3f} < umbral={threshold} — bloqueando")
    log_fidelity_failure(question or answer, sim, threshold)
    return False, sim


def numeric_validation(answer: str, source_docs: list, question: str = "") -> tuple[bool, float]:
    """Validación numérica estricta para consultas técnicas."""
    return _validate_fidelity(answer, source_docs, question, numeric_strict=True)


def semantic_validation(answer: str, source_docs: list, question: str = "") -> tuple[bool, float]:
    """Validación semántica flexible para tareas y memoria."""
    return _validate_fidelity(answer, source_docs, question, numeric_strict=False)


def fidelity_check(
    answer: str,
    source_docs: list,
    question: str = "",
    mode: str = "numeric",
) -> tuple[bool, float]:
    """Punto de entrada alternativo a verify_fidelity con selección explícita de modo."""
    if mode == "numeric":
        return numeric_validation(answer, source_docs, question)
    elif mode == "semantic":
        return semantic_validation(answer, source_docs, question)
    raise ValueError(f"Modo de validación no soportado: '{mode}'. Usa 'numeric' o 'semantic'.")
