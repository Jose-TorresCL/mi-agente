# Diagnóstico: latencia de embeddings en CPU

**Fecha de investigación:** 05–07/08/2026
**Documentado:** 26/08/2026
**Estado:** cerrado — causa raíz encontrada y fix aplicado

## Contexto

Las llamadas de embeddings (semantic_cache, fidelity_check, indexación RAG)
presentaban latencia alta y resultados pobres bajo CPU (sin GPU).
Esta nota registra qué se probó, qué se descartó y qué funcionó,
para no repetir la investigación en el futuro.

## Hipótesis descartadas

### 1. `OLLAMA_NUM_PARALLEL`

**Descartada.** No aplica a modelos de embedding — solo afecta la
generación (LLMs). Confirmado en el issue #8778 de ollama/ollama.

Lección: antes de adoptar una variable de entorno, verificar que
aplique al tipo de modelo en uso (embedding ≠ generación).

### 2. `num_thread=3`

**Descartada.** Mejora medida: 1.7% — dentro del ruido de medición.

Lección: en CPU, mejoras bajo ~5% son ruido, no optimización.
No perseguir micro-ajustes de threads para esta carga.

## Causa raíz (la que importaba)

El problema real no era de rendimiento sino de **configuración de modelo**:
`semantic_cache` usaba `llama3.2` (modelo de generación) para calcular
embeddings en vez de `nomic-embed-text` (modelo dedicado).

Fix aplicado: constante `EMBEDDING_MODEL` + endpoint actual `/api/embed`.
Detalle formal de la decisión: ver `data/docs/adr/ADR-004-fidelity-check.md`.
Scores de verificación: [COMPLETAR con los scores reales medidos el 07/08].

## Optimización posterior (26/08/2026)

`keep_alive=-1` aplicado a `nomic-embed-text` en los 4 puntos que crean
clientes de embeddings (`semantic_cache.py`, `episode_store.py`,
`indexing_core.py`, `intent_index.py`).

Efecto: el modelo (376 MB) queda residente en RAM — se eliminan las
recargas que ocurrían tras ~5 min sin uso. Verificado con
`ollama ps` → `UNTIL: Forever`.

Para liberar la RAM si hiciera falta: `ollama stop nomic-embed-text`.

## Datos medidos

- Scores de verificación: max_similitud=0.784 (umbral=0.55) — medido 01/09/2026, post-fix confirmado en producción local.

## Resumen ejecutivo

| Intento | Resultado |
|---|---|
| OLLAMA_NUM_PARALLEL | Descartado — no aplica a embeddings (issue #8778) |
| num_thread=3 | Descartado — 1.7% = ruido |
| Modelo correcto (nomic-embed-text) | Causa raíz — fix aplicado |
| keep_alive=-1 | Optimización real — residente en RAM |
