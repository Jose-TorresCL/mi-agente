# Registro de Decisiones Arquitecturales (ADR)

Este directorio contiene los ADRs del proyecto **mi-agente**.
Cada archivo documenta una decisión técnica importante: por qué se tomó,
qué alternativas se consideraron y cuáles son sus consecuencias.

## Índice

| ID | Título | Estado |
|----|--------|--------|
| [ADR-001](ADR-001-router-hibrido.md) | Router híbrido de 3 capas | ✅ Aceptado |
| [ADR-002](ADR-002-memoria-en-capas.md) | Arquitectura de memoria en capas y tipos formales | ✅ Aceptado |
| [ADR-003](ADR-003-memory-manager.md) | `memory_manager` como guardián único | ✅ Aceptado |
| [ADR-004](ADR-004-calidad-rag.md) | Calidad RAG: caché semántica, fidelity check y exclusiones | ✅ Aceptado |
| [ADR-005](ADR-005-arquitectura-inteligencia.md) | Arquitectura de inteligencia: carriles, orquestador y tests | ✅ Aceptado |
| [ADR-006](ADR-006-experience-index.md) | Experience Index: feedback loop de calidad entre sesiones | ✅ Aceptado |

## Cómo leer un ADR

Cada documento sigue esta estructura:
- **Contexto** — qué problema existía
- **Decisión** — qué se eligió
- **Alternativas consideradas** — qué más se evaluó
- **Consecuencias** — beneficios y trade-offs
- **Estado** — Propuesto / Aceptado / Obsoleto

## Notas sobre versiones antiguas

- `ADR-004-cache-semantica.md` fue reemplazado por `ADR-004-calidad-rag.md`
  que integra caché semántica, fidelity check y lista de exclusiones.
- `ADR-005-intent-index-capa2.md` fue absorbido por `ADR-001-router-hibrido.md`
  (la Capa 2 de embeddings ya es parte del router) y `ADR-005-arquitectura-inteligencia.md`
  documenta el modelo de carriles completo.
