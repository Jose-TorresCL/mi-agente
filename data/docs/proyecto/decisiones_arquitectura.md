# Decisiones de arquitectura — Índice de ADRs

> Última actualización: 19/09/2026.
>
> Este documento es un índice resumido. Para el registro detallado de ADRs y
> documentos complementarios, ver [`../adr/README.md`](../adr/README.md).

Cada Architecture Decision Record (ADR) registra una decisión de diseño
significativa: su contexto, alternativas consideradas, decisión, consecuencias
y estado. El índice no reemplaza los ADRs; sirve para encontrarlos y entender
qué zona del sistema cubre cada uno.

---

## Registro de ADRs

| ADR | Título | Estado | Fecha original | Última actualización |
|---|---|---|---|---|
| [ADR-001](../adr/ADR-001-router-hibrido.md) | Router híbrido de tres capas | ✅ Implementado | 06/05/2026 | Sin cambios |
| [ADR-002](../adr/ADR-002-memoria-en-capas.md) | Memoria en capas y tipos formales | ✅ Implementado | 2026-04 | 19/05/2026 |
| [ADR-003](../adr/ADR-003-memory-manager.md) | `memory_manager` como guardián y contexto selectivo | ✅ Implementado | 2026-05 | 19/05/2026 |
| [ADR-004](../adr/ADR-004-calidad-rag.md) | Calidad RAG: caché, fidelity y exclusiones | ✅ Implementado | 11/05/2026 | 19/05/2026 |
| [ADR-005](../adr/ADR-005-arquitectura-inteligencia.md) | Carriles de decisión y arquitectura de inteligencia | ✅ Implementado | 07/05/2026 | 19/05/2026 |
| [ADR-006](../adr/ADR-006-experience-index.md) | Experience Index y feedback loop episódico | ✅ Implementado | 19/05/2026 | — |
| [ADR-007](../adr/ADR-007-modelo-unico-vs-multi-modelo.md) | Modelo único versus multi-modelo | ✅ Aceptado | 2026-05 | — |
| [ADR-008](../adr/ADR-008-candidato-reemplazo-modelo.md) | Candidato de reemplazo de modelo | 🟡 En evaluación | 2026-05 | — |
| [ADR-009](../adr/ADR-009-perplexity-sync.md) | Sincronización de documentación | ✅ Aceptado | 11/06/2026 | — |
| [ADR-010](../adr/ADR-010-integracion-bot_trading.md) | Integración de `bot_trading` como tool externa de consulta | ✅ Aceptado | 03/08/2026 | — |

---

## Mapa de decisiones

```text
ADR-001 — Router híbrido
    │
    ├── ADR-003 — Memory Manager y contexto selectivo
    │       │
    │       ├── ADR-002 — Memoria en capas y tipos formales
    │       │       │
    │       │       └── ADR-006 — Experience Index y feedback episódico
    │       │
    │       └── ADR-004 — Calidad RAG, caché y fidelity
    │
    ├── ADR-005 — Inteligencia, carriles y tools
    │       │
    │       └── ADR-010 — Tool externa `bot_trading`
    │
    ├── ADR-007 — Estrategia de modelo
    │       │
    │       └── ADR-008 — Evaluación de candidato de modelo
    │
    └── ADR-009 — Sincronización de documentación
```

El mapa muestra relaciones de contexto y dependencia conceptual. No implica que
los módulos de código se importen entre sí.

---

## Principios reflejados

1. **Dirección de dependencias clara**: conversación → inteligencia → memoria.
2. **Un guardián por responsabilidad**: `memory_manager`, `tool_registry` y
   `rag_engine` concentran reglas de negocio específicas.
3. **Tests como contrato**: las fronteras arquitectónicas y los flujos críticos
   deben tener pruebas repetibles.
4. **Local primero, fronteras explícitas**: el núcleo funciona localmente; toda
   fuente externa usa una tool aislada, con riesgo y límites documentados.
5. **Crecer sin romper**: cada evolución debe preservar contratos, mantener
   documentación alineada y permitir rollback mediante cambios pequeños.