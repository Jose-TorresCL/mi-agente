"""Verificación de fidelidad RAG.

Qué hace:
  1. Similitud semántica: compara la respuesta contra el contexto recuperado
     usando embeddings coseno. Si la respuesta no se parece lo suficiente
     al contexto, se considera sospechosa.

  2. Verificación de claims numéricos: si la respuesta contiene números
     concretos (enteros, decimales, porcentajes, años...), comprueba que
     cada número aparezca literalmente en alguno de los chunks fuente.
     Si un número no tiene respaldo literal, la respuesta se bloquea.

Excepciones intencionadas:
  - Números de 1 dígito (1-9): omitidos.
  - Años (1900-2099): omitidos.
  - Números en la pregunta original: omitidos.
  - IDs de tarea / timestamps del sistema: omitidos.

Optimización perf:
  - Bypass para preguntas triviales/saludos.
  - Similitud semántica: 2 llamadas HTTP (embed respuesta + embed contexto concatenado).
  - Verificación numérica: 0 llamadas HTTP (comparación textual pura).

Umbral dinámico:
  - Preguntas cortas (<=4 tokens): 0.40
  - Preguntas normales (5-12 tokens): 0.55
  - Preguntas largas (>12 tokens): 0.60

Contrato de retorno:
  verify_fidelity SIEMPRE retorna tuple[bool, float].
  NUNCA lanza excepciones.

  Rango normal del float: [0.0, 1.0] (similitud coseno o bypass seguro).
  Valor sentinel especial: -1.0 significa "no se pudo verificar" (embeddings
  agotaron reintentos). is_faithful sigue en True para no bloquear al usuario,
  pero el caller (ver intelligence.py) debe tratarlo como advertencia, no
  como éxito real de verificación.
"""
from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


FIDELITY_THRESHOLD = 0.55
SHORT_ANSWER_WORDS = 7
NO_EVIDENCE_MSG = "No tengo suficiente evidencia en el contexto recuperado."

LOGS_DIR = Path("storage") / "logs"
FAILURES_LOG = LOGS_DIR / "fidelity_failures.jsonl"
SUCCESSES_LOG = LOGS_DIR / "fidelity_successes.jsonl"
UNCERTAIN_LOG = LOGS_DIR / "fidelity_uncertain.jsonl"

from app.semantic_cache import get_embedding


FIDELITY_EMERGENCY_MODE = "bypass"  # options: 'bypass' | 'uncertain'

_MAX_CONTEXT_CHARS = 4000

_RE_SINGLE_DIGIT = re.compile(r"^\d$")
_RE_YEAR = re.compile(r"^(19|20)\d{2}$")
_RE_TASK_ID = re.compile(r"^\d{9,12}$")
_RE_NUMBERS = re.compile(r"\b\d[\d.,]*\b")

_EMBED_RETRY_SLEEP = 6
_EMBED_RETRY_ATTEMPTS = 2

_TRIVIAL_QUESTION_PATTERNS = {
    "hola",
    "holi",
    "buenas",
    "buenos dias",
    "buen día",
    "buen dia",
    "buenas tardes",
    "buenas noches",
    "gracias",
    "ok",
    "oki",
    "dale",
    "perfecto",
    "listo",
    "sí",
    "si",
    "no",
}


# ─────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────


def _cosine(a: list[float], b: list[float]) -> float:
    """Similitud coseno entre dos vectores. Retorna 0.0 si alguno es cero."""
    dot = sum(x * y for x, y in zip(a, b))
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
        clean = num.rstrip(".,")
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

    is_percent = token.endswith("%")
    if is_percent:
        token = token[:-1].strip()

    is_k = token.lower().endswith("k")
    if is_k:
        token = token[:-1].strip()

    token = token.replace(" ", "")
    if not token:
        return None

    if token.count(".") > 0 and token.count(",") > 0:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif token.count(",") > 0:
        if len(token.split(",")[-1]) == 3:
            token = token.replace(",", "")
        else:
            token = token.replace(",", ".")
    elif token.count(".") > 0:
        if len(token.split(".")[-1]) == 3:
            token = token.replace(".", "")

    try:
        value = Decimal(token)
    except InvalidOperation:
        return None

    if value == value.to_integral():
        normalized = str(int(value))
    else:
        normalized = format(value.normalize(), "f")

    if is_k:
        try:
            value = Decimal(normalized) * Decimal(1000)
            if value == value.to_integral():
                normalized = str(int(value))
            else:
                normalized = format(value.normalize(), "f")
        except InvalidOperation:
            return None

    if is_percent:
        return normalized + "%"

    return normalized


def _is_trivial_question(question: str) -> bool:
    """Detecta saludos y mensajes triviales que no necesitan fidelity."""
    q = " ".join(question.lower().strip().split())
    if not q:
        return False
    if q in _TRIVIAL_QUESTION_PATTERNS:
        return True
    if len(q.split()) <= 2 and q in _TRIVIAL_QUESTION_PATTERNS:
        return True
    return False


def _build_context_text(chunks_texts: list[str], max_chars: int = _MAX_CONTEXT_CHARS) -> str:
    """Concatena chunks recuperados en un solo contexto corto."""
    parts: list[str] = []
    total = 0

    for txt in chunks_texts:
        clean = txt.strip()
        if not clean:
            continue
        remaining = max_chars - total
        if remaining <= 0:
            break
        piece = clean[:remaining]
        parts.append(piece)
        total += len(piece) + 2

    return "\n\n".join(parts).strip()


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
        normalized
        for num in chunk_nums
        if (normalized := _normalize_number_token(num)) is not None
    }

    for num in answer_nums:
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
            "question": question[:120],
            "score": round(score, 4),
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
            "question": question[:120],
            "score": round(score, 4),
            "threshold": threshold,
            "method": method,
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
            "question": question[:120],
            "reason": reason,
        }
        with UNCERTAIN_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def fidelity_stats() -> dict:
    """Lee logs y devuelve un resumen de fidelidad."""
    def _count_lines(path: Path) -> int:
        if not path.exists():
            return 0
        try:
            return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        except Exception:
            return 0

    total_ok = _count_lines(SUCCESSES_LOG)
    total_blocked = _count_lines(FAILURES_LOG)
    total_uncertain = _count_lines(UNCERTAIN_LOG)
    total = total_ok + total_blocked
    rejection_rate = (total_blocked / total) if total > 0 else 0.0

    return {
        "total_ok": total_ok,
        "total_blocked": total_blocked,
        "total_uncertain": total_uncertain,
        "total": total,
        "rejection_rate": round(rejection_rate, 4),
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

    if _is_trivial_question(question):
        print("[fidelity:skip] pregunta trivial/saludo, se omite verificación")
        log_fidelity_success(question or answer, 1.0, threshold, method="trivial_bypass")
        return True, 1.0

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

    context_text = _build_context_text(chunks_texts)
    if not context_text:
        reason = "contexto concatenado vacío"
        print(f"[fidelity:uncertain] {reason}")
        if FIDELITY_EMERGENCY_MODE == "bypass":
            return True, 1.0
        log_fidelity_uncertain(question or answer, reason)
        return False, 0.0

    try:
        ans_embedding = get_embedding(answer)
    except Exception:
        reason = "error embed respuesta"
        print(f"[fidelity:uncertain] {reason}")
        if FIDELITY_EMERGENCY_MODE == "bypass":
            return True, 1.0
        log_fidelity_uncertain(question or answer, reason)
        return False, 0.0

    attempt = 0
    while ans_embedding is None and attempt < _EMBED_RETRY_ATTEMPTS:
        attempt += 1
        print(
            f"[fidelity:retry] embed devolvió None — intento {attempt}/{_EMBED_RETRY_ATTEMPTS}, "
            f"reintentando en {_EMBED_RETRY_SLEEP}s"
        )
        time.sleep(_EMBED_RETRY_SLEEP)
        try:
            ans_embedding = get_embedding(answer)
        except Exception:
            ans_embedding = None

    if ans_embedding is None:
        reason = f"embed respuesta devolvió None tras {_EMBED_RETRY_ATTEMPTS} reintentos (Ollama ocupado post-LLM)"
        print(f"[fidelity:unverified] {reason}")
        log_fidelity_uncertain(question or answer, reason)
        return True, -1.0

    try:
        context_embedding = get_embedding(context_text)
    except Exception:
        context_embedding = None

    if context_embedding is None:
        reason = "no se obtuvo embedding del contexto concatenado"
        print(f"[fidelity:uncertain] {reason}")
        if FIDELITY_EMERGENCY_MODE == "bypass":
            return True, 1.0
        log_fidelity_uncertain(question or answer, reason)
        return False, 0.0

    sim = _cosine(ans_embedding, context_embedding)

    if sim >= threshold:
        print(f"[fidelity:ok] max_similitud={sim:.3f} (umbral={threshold})")
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
    if mode == "semantic":
        return semantic_validation(answer, source_docs, question)
    raise ValueError(f"Modo de validación no soportado: '{mode}'. Usa 'numeric' o 'semantic'.")