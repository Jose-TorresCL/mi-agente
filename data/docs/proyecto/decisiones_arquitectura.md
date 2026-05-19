# Decisiones de arquitectura — Índice de ADRs

> Última actualización: 19/05/2026 — Refactor Opción B: 6 ADRs balanceados.

Este archivo es el índice de todos los Architecture Decision Records (ADRs)
del proyecto. Cada ADR registra una decisión de diseño significativa:
por qué se tomó, qué alternativas se descartaron y qué consecuencias tiene.

---

## ¿Qué es un ADR?

Un ADR (Architecture Decision Record) documenta una decisión arquitectural
importante junto con su contexto y consecuencias. No es un manual de uso
sino un registro de *por qué* el sistema está construido así.

En este proyecto los ADRs son **documentos vivos con versionado explícito**:
registran la fecha original de la decisión y la fecha de última actualización
cuando una fase nueva amplía o modifica la decisión original.

---

## Registro de ADRs

| ADR | Título | Estado | Fecha original | Últ. actualización |
|---|---|---|---|---|
| [ADR-001](adr/ADR-001-router-hibrido.md) | Router híbrido 3 capas | ✅ Implementado | 06/05/2026 | Sin cambios |
| [ADR-002](adr/ADR-002-memoria-en-capas.md) | Memoria en capas y tipos formales | ✅ Implementado | 2026-04 | 19/05/2026 |
| [ADR-003](adr/ADR-003-memory-manager.md) | memory_manager como guardián y contexto selectivo | ✅ Implementado | 2026-05 | 19/05/2026 |
| [ADR-004](adr/ADR-004-mejoras-rag-calidad.md) | Calidad RAG: MMR, fidelity_check y contexto selectivo | ✅ Implementado | 11/05/2026 | 19/05/2026 |
| [ADR-005](adr/ADR-005-modos-agente-tool-codigo.md) | Carriles de decisión y arquitectura de inteligencia | ✅ Implementado | 07/05/2026 | 19/05/2026 |
| [ADR-006](adr/ADR-006-experience-index.md) | Experience Index y feedback loop episódico | ✅ Implementado | 19/05/2026 | — |

---

## Mapa de dependencias entre ADRs

```
ADR-001 (router)
    │
    ├─── ADR-003 (memory_manager + get_context_for)
    │       │
    │       └─── ADR-002 (capas de memoria + MemoryType)
    │               │
    │               └─── ADR-006 (experience_index)
    │
    └─── ADR-005 (intelligence.py + carriles + tests)
            │
            └─── ADR-004 (calidad RAG + fidelity_check)
```

---

## Principios de diseño que atraviesan todos los ADRs

1. **Dirección de dependencias unidireccional**: Conversación → Inteligencia → Memoria
2. **Un guardián por responsabilidad**: memory_manager, tool_registry, rag_engine
3. **Tests como contrato de arquitectura**: test_architecture.py enforce las fronteras
4. **Local primero**: ninguna decisión requiere infraestructura externa ni GPU
5. **Crecer sin romper**: cada fase añade sin rediseñar lo anterior
