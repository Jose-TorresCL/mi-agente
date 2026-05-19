# Roadmap del proyecto

> ⚠️ **Documento vivo** — última actualización: 19/05/2026  
> Las fases completadas son registro histórico permanente.  
> Solo la sección "Fase actual" describe el estado real hoy.

Fase actual: **Fase 6 — Cerrar invariantes arquitecturales**

---

## Principio rector

> Antes de agregar, consolida.  
> Antes de crecer, limpia las fronteras.  
> Sin métricas, no puedes mejorar.

Cada tarea se clasifica como:
- 🔴 Crítico — bloquea el crecimiento sano del sistema
- 🟠 Importante — mejora significativa sin riesgo alto
- 🟡 Útil — genera valor sin urgencia
- 🟢 Futuro — deseable cuando las bases estén firmes

---

## Fase 6 — Cerrar invariantes (en curso)

**Objetivo**: el sistema nunca toma decisiones incorrectas por problemas
de plomería interna. Cada invariante tiene un test que lo protege.

| Subtarea | Descripción | Prioridad | Estado |
|---|---|---|---|
| 6A | Fix estructural caché semántico | 🔴 | 🔄 En curso |
| 6B | Recuperación selectiva real por tipo de memoria | 🟠 | 🔲 Pendiente |
| 6C | fidelity_check endurecido (docs vacíos, respuesta corta) | 🟠 | 🔲 Pendiente |
| 6D | Tests de arquitectura (imports prohibidos entre capas) | 🟡 | 🔲 Pendiente |

Detalle completo en `fase6-tareas.md`.

---

## Fase 7 — Observabilidad y evaluación continua

**Objetivo**: tener números que digan si el sistema mejora o empeora
con cada cambio. Sin métricas no se puede decidir si un cambio vale la pena.

| Subtarea | Descripción | Prioridad |
|---|---|---|
| 7A | Logger de métricas por turno → `storage/metrics.jsonl` | 🔴 |
| 7B | Script `show_metrics.py` — tabla terminal con tiempos y carriles | 🟠 |
| 7C | Evaluación RAG end-to-end: ampliar batería de 9 a 20 preguntas | 🟠 |
| 7D | Umbral adaptativo de caché — entradas > 7 días se recalculan | 🟡 |

### Métricas objetivo (Fase 7)

| Métrica | Objetivo |
|---|---|
| Tiempo de retrieval Chroma | < 200ms por consulta |
| Tiempo de respuesta LLM | < 8s en ThinkPad i7 8ª gen |
| % respuestas con evidencia documental | ≥ 75% |
| % consultas resueltas sin LLM (caché + keywords) | > 30% |
| Distribución de carriles | visible en dashboard |

---

## Fase 8 — Experience Index (memoria agentic)

**Objetivo**: el agente aprende de lo que ya hizo. Cuando una situación
nueva es similar a una pasada, recupera qué funcionó — sin fine-tuning,
solo con Chroma y los episodios que ya guardas.

Inspiración conceptual: ExpRAG (indexar trayectorias como documentos)
y A-Mem (marcar experiencias como exitosas/problemáticas).

| Subtarea | Descripción | Prioridad |
|---|---|---|
| 8A | Indexar episodios de sesión en `experience_index` (Chroma separado) | 🟠 |
| 8B | Recuperar experiencias relevantes en carril `memory` | 🟠 |
| 8C | Marcado de calidad de episodios (exitoso / fallido) | 🟡 |
| 8D | `MemoryType` enum formal en `schemas.py` (WORKING, SEMANTIC, EPISODIC, PROCEDURAL) | 🟡 |

### Cómo funciona el Experience Index

```
Fin de sesión → save_episode() guarda resumen en memory_store
                         ↓
             indexacion.py --only-episodes
                         ↓
          experience_index en Chroma (índice separado)
                         ↓
Nueva pregunta → búsqueda en experience_index (score > 0.80)
                         ↓
      Episodio relevante se añade al contexto del prompt
```

**Criterio de éxito**: pregunta "¿cómo resolví el problema de encoding?"
recupera el episodio correcto sin que lo hayas programado explícitamente.

---

## Prioridad de aprendizaje

| Fase | Concepto clave | Nivel |
|---|---|---|
| 6A–6B | Context routing selectivo | Fundamental |
| 6C–6D | Defensive programming + tests de arquitectura | Intermedio |
| 7A–7B | Observabilidad con jsonl | Fundamental |
| 7C–7D | Evaluación RAG y cache aging | Intermedio |
| 8A–8B | Experience index con Chroma | Avanzado |
| 8C–8D | Feedback loop + tipos formales de memoria | Avanzado |

---

## Cuándo migrar de JSON a SQLite

No antes de Fase 8C. La migración solo vale la pena cuando:
- Los episodios superen ~500 entradas, O
- Los tiempos de lectura de `memory_store` superen 200ms

Hasta entonces: JSON + Chroma es perfecto para el hardware actual.

---

## Historia de fases

| Fase | Foco principal | Estado |
|---|---|---|
| Fase 1 | RAG básico + indexación | ✅ Completa |
| Fase 2 | Memoria estructurada + tools + router simple | ✅ Completa |
| Fase 3A | Router híbrido keywords + LLM | ✅ Completa |
| Fase 3B | Clasificador embeddings + intent_index | ✅ Completa |
| Fase 4 | Caché, fidelity check, episodios, anti-alucinación | ✅ Completa |
| Fase 5A | Refactor modular completo | ✅ Completa |
| Fase 5B | Suite 67+ tests pasando | ✅ Completa |
| Fase 5C | Deduplicación project_facts + inyección automática | ✅ Completa |
| Fase 5D | memory_manager como guardián único | ✅ Completa |
| Fase 5E | Batería evaluación fija (9 preguntas) | ✅ Completa |
| Fase 5F | Papers indexados (SLM-First, MoA) | ✅ Completa |
| Fase 5G | Exclusión docs baja calidad del índice | ✅ Completa |
| Fase 6 | Cerrar invariantes arquitecturales | 🔄 En curso |
| Fase 7 | Observabilidad y evaluación continua | 🔲 Pendiente |
| Fase 8 | Experience Index — memoria agentic | 🔲 Pendiente |
