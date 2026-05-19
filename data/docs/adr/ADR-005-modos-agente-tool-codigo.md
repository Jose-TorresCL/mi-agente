# ADR-005 — Carriles de decisión y arquitectura de inteligencia

**Fecha original:** 07/05/2026 (Fase 5A — intelligence.py separado)  
**Última actualización:** 19/05/2026 (Fase 6 — carril TERMINAL, 9 carriles, tests)  
**Estado:** ✅ IMPLEMENTADO  
**Autor:** Jose Torres + Lautaro  
**ADRs relacionados:** ADR-001 (router), ADR-003 (memory_manager), ADR-006 (experience_index)

> **Nota de versionado:** Este ADR se reenfocaró en Opción-B (19/05/2026).
> Las decisiones sobre experience_index y MemoryType enum se movieron a
> ADR-006 y ADR-002 respectivamente, donde tienen mejor contexto.

---

## Contexto

Tras la modularización de Fase 5A, el sistema tenía un `chat_core.py`
que acumulaba demasiadas responsabilidades: routing, ejecución, memoria,
tools y generación de respuesta en un solo lugar.

Los problemas principales:
- El caché semántico interceptaba consultas de estado actual (memoria dinámica)
- No había separación entre “decisión de qué hacer” y “cómo hacerlo”
- Sin tests que protegiesen que las capas no se mezclasen entre sí

---

## Decisión 1 — intelligence.py como orquestador de carriles (Fase 5A)

Se extrajo `app/intelligence.py` como módulo que recibe el carril
clasificado por el router y devuelve la respuesta ejecutando la lógica
correspondiente.

```
chat_core.py
    ↓ recibe input
router.py
    ↓ clasifica carril
intelligence.py
    ├── rag         → rag_engine.py
    ├── memory      → memory_manager.py (TERMINAL)
    ├── episode     → episode_store.py
    ├── tool_*      → tool_registry.py
    └── unsupported → respuesta directa sin LLM
```

---

## Decisión 2 — Carril memory como TERMINAL (Fix 6A)

**Problema**: el caché semántico servía respuestas de días atrás para
preguntas de estado actual. El estado del proyecto cambia cada sesión.

**Solución**: el carril `memory` en `process_turn()` retorna directamente
sin pasar por `_decide_rag()` ni por `cache_lookup()`:

```python
# intelligence.py — process_turn()
if route == "memory":
    answer = _decide_memory(user_input)
    return answer, []  # TERMINAL — nunca llega a _decide_rag()
```

**Consecuencia**: si `_decide_memory()` no reconoce la consulta,
devuelve `_MEMORY_NOT_FOUND_MSG` explícito en vez de caer a RAG.

---

## Decisión 3 — 9 carriles estables (Fase 5A + Fase 6)

| Carril | Qué hace | Característica |
|---|---|---|
| `rag` | Retrieval semántico + caché + fidelity + experience_inj. | Pasa por caché |
| `memory` | Consulta JSON de estado (TERMINAL) | No pasa por caché |
| `episode` | Búsqueda semántica en experience_index | No pasa por caché |
| `tool_list_files` | Lista archivos del proyecto | Directo |
| `tool_read_file` | Lee contenido de un archivo | Directo |
| `tool_save_fact` | Guarda hecho en project_facts.json | Escribe memoria |
| `tool_create_task` | Crea tarea en tasks.json | Escribe memoria |
| `tool_complete_task` | Marca tarea completada | Escribe memoria |
| `tool_update_work_state` | Actualiza work_state.json | Escribe memoria |
| `unsupported` | Respuesta directa sin LLM | Sin cargas |

---

## Decisión 4 — Tests de arquitectura (Fase 6D)

**Solución**: `tests/test_architecture.py` usa análisis AST (sin ejecutar
código ni levantar Ollama) para verificar que las capas no se importan
entre sí.

**Invariantes protegidos**:
- `chat_ui.py` no importa `memory_store`
- `router.py` no importa `rag_engine`
- `memory_manager.py` no importa `chat_ui`

---

## Decisión 5 — Métricas por turno (Fase 7A)

`metrics.py` registra en `storage/metrics.jsonl` cada turno con:
ruta, tiempo de retrieval, tiempo LLM, tokens estimados y flag `cached`.

`record_turn()` nunca lanza excepciones — errores van a WARNING.
Formato JSONL para análisis con pandas o scripts simples.

---

## Consecuencias

- Los carriles `memory` y `episode` nunca llenan el caché semántico.
- `test_architecture.py` actúa como guardia permanente de fronteras entre capas.
- `unsupported` evita invocar el LLM para consultas fuera de alcance.

## Archivos clave

- `app/intelligence.py` — orquestador de carriles
- `app/tool_registry.py` — despacho centralizado de tools
- `app/metrics.py` — logger de métricas por turno
- `tests/test_architecture.py` — invariantes de capas
- `tests/test_memory_route.py` — carril memory TERMINAL
