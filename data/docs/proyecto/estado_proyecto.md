# Estado del proyecto

> ⚠️ **Documento vivo** — se desactualiza con cada sesión.
> Última actualización: 13/08/2026. No usar como referencia de arquitectura estable;
> para eso consultar `arquitectura_actual.md` y los ADRs.
---

## Objetivo general

Construir un asistente local con Ollama, LangChain y Chroma para
responder preguntas usando recuperación de contexto desde documentos
del proyecto, evolucionando hacia un agente con memoria estructurada
por capas, tools controladas y recuperación selectiva de contexto.

---

## Fase actual: Fase 7 — Observabilidad y evaluación continua

**Fecha de actualización**: 13/08/2026

**Objetivo de Fase 7**:
Tener números que digan si el sistema mejora o empeora con cada cambio.
Sin métricas no se puede decidir si un cambio vale la pena.

---

## Hitos completados

| Hito | Fecha |
|---|---|
| Fase 1: RAG básico + indexación | Antes del 05/05/2026 |
| Fase 2: memoria, tools, router simple | 05/05/2026 |
| Fase 3A: router híbrido keywords + LLM | 06/05/2026 |
| Fase 3B: clasificador embeddings + intent_index | 06/05/2026 |
| Fase 4A–G: caché, fidelity check, episodios, fixes | 06–07/05/2026 |
| Fase 5A: refactor modular completo | 08/05/2026 |
| Fase 5B: suite de 67+ tests pasando | 08/05/2026 |
| Fase 5C: deduplicación project_facts + inyección automática | 08–09/05/2026 |
| Fase 5D: memory_manager.py como guardián de capa memoria | 10–16/05/2026 |
| Fase 5E: batería de evaluación fija (9 preguntas) operativa | 16/05/2026 |
| Fase 5F: papers indexados (SLM-First, MoA) | 17/05/2026 |
| Fase 5G: exclusión docs baja calidad del índice | 17/05/2026 |
| Fase 6A: fix estructural caché — carril memory TERMINAL | 19/05/2026 |
| Fase 6B: get_context_for() — recuperación selectiva real | 19/05/2026 |
| Fase 6C: fidelity_check endurecido (docs vacíos, respuesta corta) | 19/05/2026 |
| Fase 6D: tests de arquitectura (imports prohibidos entre capas) | 19/05/2026 |
| Fase 7A: logger de métricas por turno → `storage/metrics.jsonl` | 19/05/2026 |
| Fase 7B: `show_metrics.py` — tablero de métricas en consola + tests (`tests/test_show_metrics.py`) | 13/08/2026 |
| Fase 8A: experience_index en Chroma (índice separado de episodios) | 19/05/2026 |
| Fase 8B: experience_lookup en carril episode + búsqueda semántica en carril episode | 19/05/2026 |
| Fase 8C: señal de calidad (exitoso s/n) + boost +0.15 en `search_episodes` | 19/05/2026 |
| Fase 8D: MemoryType enum en `schemas.py` + anotaciones en `memory_manager` | 19/05/2026 |
| Sprint 4 — Robustecimiento y cobertura: 306/306 tests verde, normalización router, tests adversariales | 19–24/05/2026 |
| R6-A parcial: tools retornan `ToolResult`, `tool_registry` clasifica riesgo (READ/WRITE/SYSTEM), `tool_complete_task` soporta ID y ordinales | 03/08/2026 |

---

## Estado técnico actual (03/08/2026)

### Lo que está firme

- Modularización completa en `app/` con separación por capas.
- `config.py` como fuente única de constantes globales.
- `intelligence.py` como orquestador de decisión por carriles (rag, memory, episode, tools, exit, unsupported).
- `rag_engine.py` como módulo independiente con caché semántica y `fidelity_check`.
- `tool_registry.py` como despachador centralizado de tools, con clasificación de riesgo (`RiskLevel.READ`, `WRITE`, `SYSTEM`).
- `tools.py` como implementación de tools operativas, todas con contrato `ToolResult` (R6-A parcial).
- `memory_context.py` como ensamblador de contexto para prompts.
- `memory_manager.py` como guardián único de lectura/escritura de memoria estructurada.
- `episode_store.py` con `experience_index` en Chroma separado y señal de calidad por episodio.
- `metrics.py` — logger de métricas por turno en `storage/metrics.jsonl`.
- `schemas.py` con `MemoryType` enum (WORKING, SEMANTIC, EPISODIC, PROCEDURAL), `ToolResult` y `RiskLevel`.
- Router híbrido 3 capas operativo (keywords → embeddings → LLM fallback).
- Carriles de ejecución estables (rag, memory, episode, `tool_*`, exit, unsupported).
- **306/306 tests pasando** reportados en Sprint 4 (39% cobertura).
- Caché semántica solo activa en carril `rag` — carril `memory` es TERMINAL.
- Recuperación selectiva: `get_context_for(intent_type)` elige capa de memoria por intención.
- `fidelity_check`: bloquea respuestas sin docs, respuestas cortas sin evidencia y revisa soporte numérico literal.
- Experience Index operativo: episodios indexados en Chroma, búsqueda semántica por score y boost de episodios exitosos.
- Señal de calidad al cerrar sesión (`exitoso s/n`) guardada en episodios y reflejada en `experience_index`.
- Normalización de texto en router (Sprint 4) — preguntas con tildes/mayúsculas/variantes resueltas en capa 1.
- `tool_complete_task` mejora UX: completa tareas por ID (`T-...`) o por ordinal sobre pendientes (primera, segunda, tercera, cuarta, quinta, última, penúltima).
- `tool_analizar_mercado` integrada como tool de riesgo `SYSTEM` para consultar bot de trading vía subprocess, bloqueada por defecto en `dispatch_tool`.

### Problemas resueltos acumulados

| Problema | Estado |
|---|---|
| Modularización de archivos grandes | ✅ |
| Falta de memoria persistente | ✅ |
| Router solo por reglas simples | ✅ |
| LLM fallback lento | ✅ embeddings ~50ms |
| `ConversationBufferWindowMemory` deprecada | ✅ |
| LLM inventaba IDs de tareas | ✅ regla anti-alucinación + uso de `tasks.json` real |
| `tool_save_fact` creaba claves duplicadas | ✅ formato `key=value` y manejo de contenido vacío |
| RAG respondía sin soporte documental | ✅ `fidelity_check` |
| Respuestas RAG repetidas con costo LLM | ✅ caché semántica |
| Contexto de sesión anterior perdido | ✅ memoria episódica |
| `config.py` inexistente | ✅ centralizado |
| Tools sin punto central de despacho | ✅ `tool_registry.py` |
| RAG mezclado con `chat_core` | ✅ `rag_engine.py` separado |
| Tools escribían JSON directo sin guardián | ✅ `memory_manager.py` |
| Sin batería de evaluación fija | ✅ 9 preguntas estándar |
| Índice con docs obsoletos/genéricos | ✅ 3 archivos excluidos |
| Caché semántico interceptaba carril `memory` | ✅ carril `memory` TERMINAL |
| Recuperación de contexto sin discriminar tipo | ✅ `get_context_for()` |
| `fidelity_check` sin reglas para casos borde | ✅ 3 reglas implementadas |
| Sin tests de límites entre capas | ✅ `test_architecture.py` |
| Sin métricas por turno | ✅ `metrics.jsonl` |
| Sin memoria de experiencias pasadas | ✅ `experience_index` en Chroma |
| Sin distinción formal de tipos de memoria | ✅ `MemoryType` enum |
| Router frágil ante tildes/mayúsculas/variantes | ✅ normalización Sprint 4 |
| Cobertura de tests insuficiente | ✅ 306/306, 39% cobertura |
| Tools devolvían `str` sin contrato explícito | ✅ `ToolResult` en `tools.py` (R6-A parcial) |
| Tools sin clasificación de riesgo | ✅ `RiskLevel` y bloqueo de `SYSTEM` en `dispatch_tool()` |
| `tool_complete_task` solo aceptaba ID | ✅ ahora acepta ID y ordinales conocidos |

### Problemas pendientes

- Batería de evaluación RAG ampliada de 9 a 20 preguntas con respuestas esperadas (Fase 7C).
- Caché con aging: entradas > 7 días se recalculan en la siguiente consulta similar (Fase 7D).
- Mejorar `tool_complete_task` para aceptar también “tarea 9” como índice humano y títulos exactos, sin romper la lógica actual.
- Evaluar y documentar mejor el modelo actual (por ejemplo `qwen3:8b` vía Ollama) en los documentos de arquitectura y visión.

---

## Próximos pasos — Fase 7 (en curso)

1. **7C — Batería ampliada**
   Ampliar de 9 a 20 preguntas de evaluación RAG con respuestas esperadas, carril esperable y umbral de score.

2. **7D — Caché con aging**
   Entradas de caché con más de 7 días se marcan como stale y se recalculan en la próxima consulta similar.

3. Consolidar R6-A: añadir tests de contrato de tools (`test_tools.py`) y asegurar que todas las herramientas de escritura registren side-effects claros (`side_effect` en `ToolResult`).

---

## Criterio de respuesta

- **RAG**: preguntas documentales, conceptuales, “¿qué hace…?”, “¿cómo funciona…?”, “¿qué es…?”.
- **Memoria**: preferencias, hechos persistentes, tareas existentes, estado actual de trabajo.
- **Episode**: sesiones pasadas, “¿en qué quedamos?”, “¿qué hicimos antes?”.
- **Tools**: acciones concretas sobre archivos o memoria estructurada (crear tarea, marcar completada, actualizar foco, guardar hechos).
- **SYSTEM tools**: acceso externo (bot de trading), solo tras confirmación/habilitación manual.
- Si no hay evidencia suficiente → abstenerse claramente o pedir más contexto.

---

## Relación entre componentes

- **RAG**: conocimiento estable recuperado desde documentos Markdown.
- **Memoria estructurada**: estado dinámico y persistente (JSON) — perfil, tareas, facts, work_state.
- **Memoria episódica**: resúmenes de sesión y señal de productividad entre arranques.
- **Experience Index**: episodios indexados en Chroma para búsqueda semántica y reutilización de experiencias exitosas.
- **Caché semántica**: evita re-invocar LLM para preguntas similares en carril RAG.
- **Fidelity check**: evita respuestas sin soporte documental real.
- **Tools**: acciones controladas sobre archivos y memoria (tools `READ`/`WRITE`/`SYSTEM`).
- **Router 3 capas**: keywords → embeddings → LLM fallback, con normalización para robustez.
- **Memory Manager**: guardián único de lectura/escritura de memoria estructurada y selección de capas via `get_context_for()`.
- **Metrics**: registro de rendimiento y carriles por turno en `storage/metrics.jsonl`.
