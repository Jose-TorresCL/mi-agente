# Fase 6 — Tareas detalladas

> Última actualización: 19/05/2026  
> **✅ FASE COMPLETA** — todas las subtareas implementadas y con tests.

---

## Resumen ejecutivo para el agente

Fase 6 cerró los últimos bordes arquitecturales del sistema:
el caché semántico no intercepta la memoria, la recuperación
de contexto es selectiva por tipo de pregunta, el fidelity_check
rechaza casos borde conocidos, y los tests protegen que las
capas no se mezclen entre sí.

---

## 6A — Fix estructural del caché semántico ✅

**Estado**: IMPLEMENTADO en `intelligence.py`

El carril `memory` es TERMINAL en `process_turn()` — devuelve directamente
sin pasar por `_decide_rag()` ni por `cache_lookup()`. El caché semántico
solo se consulta dentro de `_decide_rag()`, que el carril `memory` nunca toca.

**Criterio de done**: ✅
- Carril `memory` no llama a `cache_lookup` en ningún punto.
- Test: `test_memory_route.py` — pregunta de tipo `memory` devuelve
  valor real de `work_state.json`, nunca una entrada cacheada.
- El caché no crece cuando el carril elegido es `memory`.

---

## 6B — Recuperación selectiva real por tipo de memoria ✅

**Estado**: IMPLEMENTADO en `memory_manager.py` y usado en `intelligence.py`

`get_context_for(intent_type: str)` recibe el tipo de intención y devuelve
solo la capa de memoria relevante. `_decide_memory()` usa esta función.

**Mapa de intenciones implementado**:

| Intención del router | Contexto a recuperar |
|---|---|
| `work_state`, `tasks`, `focus` | `get_working_context()` |
| `project_info`, `architecture`, `rag` | `get_semantic_context()` |
| `episode`, `last_session` | `get_episodic_context()` |
| `identity`, `greeting` | contexto mínimo (solo profile) |

**Criterio de done**: ✅
- Test: `test_memory_layer.py` — `get_context_for('work_state')` devuelve
  objeto con tareas y foco, pero NO resumen episódico.

---

## 6C — fidelity_check endurecido ✅

**Estado**: IMPLEMENTADO en `fidelity_check.py`

Tres reglas activas:
1. `not source_docs` → bloqueo directo (`return False, 0.0`)
2. `chunks_texts` vacío → bloqueo directo
3. Respuesta corta (< 7 palabras) SIN chunks → bloqueada (Fix 6C explícito en código)

Los 3 WARNs que mencionaba la especificación original están resueltos.

**Criterio de done**: ✅
- Test: `test_fidelity_warn1.py` cubre los 3 casos.
- `fidelity_check(docs=[], answer="cualquier cosa")` → `passed=False`.

---

## 6D — Tests de arquitectura ✅

**Estado**: IMPLEMENTADO en `tests/test_architecture.py`

Tests que verifican que las capas no se importan entre sí usando
análisis AST (sin ejecutar el código ni levantar Ollama).

**Tests implementados**:
- `test_chat_ui_no_importa_memory_store()`
- `test_router_no_importa_rag_engine()`
- `test_memory_manager_no_importa_chat_ui()`
- Tests adicionales de separación de capas

**Criterio de done**: ✅
- `pytest tests/test_architecture.py` pasa en verde.

---

## Señal de Fase 6 completa — validación

Pregúntale al agente estas 3 cosas y verifica:

1. `"¿En qué fase estamos?"` → responde Fase 7 (no Fase 6, no desde caché).
2. `"¿Qué tareas hay abiertas?"` → contexto solo de working memory, sin episodios.
3. `"¿Qué es fidelity_check?"` → RAG con evidencia documental, sin WARNs en log.
