# Roadmap del proyecto

> ⚠️ **Documento vivo** — última actualización: 19/05/2026  
> Las fases completadas son registro histórico permanente.  
> Solo la sección "Fase actual" describe el estado real hoy.

Fase actual: **Fase 7 — Observabilidad y evaluación continua**

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

## Fase 7 — Observabilidad y evaluación continua (en curso)

**Objetivo**: tener números que digan si el sistema mejora o empeora
con cada cambio. Sin métricas no se puede decidir si un cambio vale la pena.

| Subtarea | Descripción | Prioridad | Estado |
|---|---|---|---|
| 7A | Logger de métricas por turno → `storage/metrics.jsonl` | 🔴 | ✅ Completa |
| 7B | Script `show_metrics.py` — tabla terminal con tiempos y carriles | 🟠 | 🔲 Pendiente |
| 7C | Evaluación RAG end-to-end: ampliar batería de 9 a 20 preguntas | 🟠 | 🔲 Pendiente |
| 7D | Umbral adaptativo de caché — entradas > 7 días se recalculan | 🟡 | 🔲 Pendiente |

### Métricas objetivo (Fase 7)

| Métrica | Objetivo |
|---|---|
| Tiempo de retrieval Chroma | < 200ms por consulta |
| Tiempo de respuesta LLM | < 8s en ThinkPad i7 8ª gen |
| % respuestas con evidencia documental | ≥ 75% |
| % consultas resueltas sin LLM (caché + keywords) | > 30% |
| Distribución de carriles | visible en dashboard |

---

## Fase 9 — Próxima (por definir)

**Objetivo**: a definir cuando Fase 7 esté completa.

Candidatos según lo aprendido:
- Planner simple para tareas multi-paso (sin autonomía total)
- Migración de JSON a SQLite cuando episodios superen ~500 entradas
- Dashboard web liviano para visualizar métricas y episodios
- Primer tool de alto riesgo controlado (shell restringida por whitelist)

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

No antes de Fase 9. La migración solo vale la pena cuando:
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
| Fase 6A | Fix estructural caché — carril memory TERMINAL | ✅ Completa |
| Fase 6B | get_context_for() — recuperación selectiva real | ✅ Completa |
| Fase 6C | fidelity_check endurecido (docs vacíos, respuesta corta) | ✅ Completa |
| Fase 6D | Tests de arquitectura (imports prohibidos entre capas) | ✅ Completa |
| Fase 7A | Logger de métricas por turno (metrics.jsonl) | ✅ Completa |
| Fase 8A | experience_index en Chroma (índice separado) | ✅ Completa |
| Fase 8B | experience_lookup en RAG + búsqueda semántica en episode | ✅ Completa |
| Fase 8C | Señal de calidad + boost +0.15 en search_episodes | ✅ Completa |
| Fase 8D | MemoryType enum + anotaciones en memory_manager | ✅ Completa |
| Fase 7 (7B–7D) | Observabilidad completa | 🔄 En curso |
| Fase 9 | Por definir tras Fase 7 completa | 🔲 Pendiente |
