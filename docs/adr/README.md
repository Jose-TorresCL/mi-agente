# Architecture Decision Records (ADR)

Este directorio documenta las decisiones de arquitectura importantes del proyecto.

Un ADR es un registro corto que explica **qué decidimos**, **por qué lo decidimos** y **qué alternativas descartamos**. Sirve para que en el futuro (o cualquier colaborador) entienda el razonamiento sin tener que leer todo el código.

## Índice

| # | Título | Estado |
|---|---|---|
| [ADR-001](ADR-001-router-hibrido.md) | Router híbrido de 3 capas | ✅ Aceptado |
| [ADR-002](ADR-002-separacion-memory-manager.md) | Separación R1 — acceso a memoria vía memory_manager | ✅ Aceptado |
| [ADR-003](ADR-003-fidelity-check.md) | Fidelity check con umbral 0.55 | ✅ Aceptado |
| [ADR-004](ADR-004-cache-semantica.md) | Caché semántica con nomic-embed-text | ✅ Aceptado |

## Cómo agregar un ADR nuevo

1. Copia la plantilla de cualquier ADR existente.
2. Nómbralo `ADR-00N-titulo-corto.md`.
3. Rellena las secciones: Contexto, Decisión, Consecuencias, Alternativas descartadas.
4. Agrégalo al índice de este README.
