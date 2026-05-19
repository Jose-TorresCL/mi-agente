# ADR-004 — Calidad RAG: MMR, fidelity_check y contexto selectivo

**Fecha original:** 11/05/2026 (MMR + encoding + context selectivo en diseño)  
**Última actualización:** 19/05/2026 (Fix 6C — fidelity_check 3 reglas implementado)  
**Estado:** ✅ IMPLEMENTADO  
**Autor:** Jose Torres + Lautaro  
**ADRs relacionados:** ADR-001 (router), ADR-003 (memory_manager), ADR-005 (carriles)

> **Nota de versionado:** Originalmente registraba MMR, encoding y context selectivo
> como decisiones pendientes. En Fase 6B–6C todas quedaron implementadas y el
> `fidelity_check` fue endurecido con 3 reglas explícitas.

---

## Contexto

Tras indexar documentos del proyecto, se identificaron tres problemas de calidad
que limitaban las respuestas del agente:

1. **Retriever por similitud pura**: devuelve los k chunks más parecidos, que pueden
   ser todos del mismo archivo (falta diversidad de fuentes).
2. **RAG respondía sin soporte documental real**: el LLM generaba respuestas aunque
   los chunks recuperados no tuvieran evidencia para la pregunta.
3. **Contexto de memoria inyectado siempre completo**: tokens innecesarios para
   preguntas documentales que no necesitan workstate ni tareas.

---

## Decisión 1 — MMR en el retriever (Fase 5)

**Qué es MMR**: Maximal Marginal Relevance balancea relevancia y diversidad.
En vez de los 5 chunks más similares (que pueden ser redundantes), selecciona
candidatos relevantes *y* distintos entre sí.

```python
# rag_engine.py
vectordb.as_retriever(
    search_type="mmr",
    search_kwargs={"k": 5, "fetch_k": 20, "lambda_mult": 0.6}
)
```

- `fetch_k=20`: candidatos iniciales antes de filtrar por diversidad
- `lambda_mult=0.6`: prioriza levemente relevancia sobre diversidad (0.5 = equilibrio, 1.0 = solo relevancia)
- Alternativa descartada: `similarity_score_threshold` — requiere umbral fijo que no funciona igual para todos los tipos de preguntas

---

## Decisión 2 — fidelity_check con 3 reglas (Fase 4 + Fix 6C)

**Problema**: el LLM generaba respuestas aunque los docs recuperados fueran
irrelevantes o estuvieran vacíos. No había forma de detectarlo automáticamente.

**Solución**: `fidelity_check.py` verifica soporte documental antes de devolver
la respuesta. Si falla, devuelve un mensaje de abstención explícito.

### Las 3 reglas (Fix 6C — Fase 6C):

```python
# fidelity_check.py
def fidelity_check(source_docs, chunks_texts, answer) -> tuple[bool, float]:

    # Regla 1: sin docs → bloqueo directo
    if not source_docs:
        return False, 0.0

    # Regla 2: chunks vacíos → bloqueo directo  
    if not chunks_texts or all(len(c.strip()) == 0 for c in chunks_texts):
        return False, 0.0

    # Regla 3: respuesta corta SIN evidencia numérica en chunks → bloqueo
    # (Fix 6C explícito: respuestas < 7 palabras que no tienen soporte)
    if len(answer.split()) < 7 and not _has_numeric_evidence(chunks_texts, answer):
        return False, 0.0

    # Verificación semántica normal...
    return _semantic_fidelity(source_docs, answer)
```

**Test de verificación**:
```python
# test_fidelity_warn1.py — cubre los 3 casos
assert fidelity_check(docs=[], answer="cualquier cosa") == (False, 0.0)
assert fidelity_check(docs=[doc], chunks=[], answer="x") == (False, 0.0)
assert fidelity_check(docs=[doc], chunks=["hola"], answer="sí") == (False, 0.0)
```

---

## Decisión 3 — Context selectivo por intención (Fase 6B)

Ver ADR-003 Decisión 2. El context selectivo se implementó en `memory_manager.get_context_for()`.
El carril `rag` recibe solo RAG chunks + perfil mínimo. El carril `memory` es TERMINAL.

---

## Decisión 4 — Exclusión de documentos baja calidad (Fase 5G)

Se excluyeron 3 archivos del índice Chroma por ser genéricos o desactualizados.
El índice resultó en 269 chunks desde documentos curados del proyecto.

---

## Consecuencias

- MMR elimina redundancia de fuentes en bloques "Basado en:" — más cobertura.
- `fidelity_check` elimina respuestas sin soporte documental en 3 casos borde.
- Context selectivo reduce tokens del prompt ~40% en preguntas RAG.
- Si `fidelity_check` empeora recall, ajustar `lambda_mult` de 0.6 a 0.7.

## Archivos clave

- `app/rag_engine.py` — MMR configurado
- `app/fidelity_check.py` — 3 reglas implementadas
- `app/memory_manager.py` — get_context_for()
- `tests/test_fidelity_warn1.py` — cubre los 3 casos borde
