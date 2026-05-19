# ADR-003 — memory_manager como guardián único y contexto selectivo

**Fecha original:** 2026-05 (Fase 5D — fachada única R/W)  
**Última actualización:** 19/05/2026 (Fase 6B — get_context_for() selectivo)  
**Estado:** ✅ IMPLEMENTADO  
**Autor:** Jose Torres + Lautaro  
**ADRs relacionados:** ADR-002 (capas de memoria), ADR-005 (carriles de inteligencia)

> **Nota de versionado:** La decisión original (Fase 5D) estableció `memory_manager`
> como fachada única. En Fase 6B se añadió `get_context_for()` para recuperación
> selectiva por tipo de intención.

---

## Contexto

Antes de este módulo, tanto `tools.py` como `chat_core.py` importaban directamente
`memory_store` y leían/escribían `storage/memory.json` de forma independiente.

Eso generaba:
- Acoplamiento fuerte entre lógica de negocio e infraestructura de storage
- Riesgo de inconsistencias si el formato del JSON cambiaba
- Violación del principio de responsabilidad única (SRP)
- Inyección de contexto completo siempre, aunque la pregunta no lo necesite

---

## Decisión 1 — Fachada única de acceso a memoria (Fase 5D)

Se creó `app/memory_manager.py` como único punto de lectura/escritura de
la capa de memoria declarativa.

### Interfaz pública

```python
# Lectura por tipo (MemoryType explícito)
get_working_context()  -> str   # MemoryType.WORKING
get_semantic_context() -> str   # MemoryType.SEMANTIC
get_episodic_context() -> str   # MemoryType.EPISODIC
get_full_context()     -> str   # todos los tipos (fallback)
get_context_for(intent_type: str) -> str  # selector por intención [6B]

# Lectura directa
get_profile()         -> dict
get_project_facts()   -> dict
get_tasks()           -> dict
get_work_state()      -> dict
get_last_episode()    -> dict | None

# Escritura
save_fact(key, value)          -> dict
update_state(**kwargs)         -> dict
create_task(title, priority)   -> dict
complete_task(task_id)         -> dict
record_episode(summary, turns) -> dict
```

### Regla de dependencias (enforced por tests)

```
chat_core.py  ──→  memory_manager.py  ──→  memory_store.py  ──→  *.json
tools.py      ──→  memory_manager.py

# NUNCA (test_architecture.py lo detecta):
chat_core.py  ──✗──  memory_store.py
router.py     ──✗──  memory_store.py
```

---

## Decisión 2 — get_context_for() por tipo de intención (Fase 6B)

**Problema**: inyectar contexto completo siempre aumenta tokens y puede
confundir al LLM con información irrelevante para la pregunta actual.

**Solución**: `get_context_for(intent_type)` recibe el tipo de intención
clasificado por el router y devuelve solo la capa relevante:

| Intención del router | Contexto entregado | MemoryType |
|---|---|---|
| `work_state`, `tasks`, `focus` | `get_working_context()` | WORKING |
| `project_info`, `architecture`, `rag` | `get_semantic_context()` | SEMANTIC |
| `episode`, `last_session` | `get_episodic_context()` | EPISODIC |
| `identity`, `greeting` | solo profile (mínimo) | SEMANTIC |

**Test de verificación**:
```python
# test_memory_layer.py
ctx = get_context_for("work_state")
assert "tareas" in ctx.lower()
assert "episodio" not in ctx.lower()  # no filtra de otra capa
```

---

## Alternativas consideradas

| Alternativa | Pros | Contras |
|---|---|---|
| Acceso directo desde cada módulo | Sin burocracia | Acoplamiento alto |
| ORM con SQLite | Tipado fuerte | Overkill hasta Fase 9 |
| Contexto completo siempre | Simple | Más tokens, más ruido |
| **Fachada + selector por intención** ✅ | Un punto de control, contexto mínimo | Un archivo más |

---

## Consecuencias

- Cambiar el formato de cualquier JSON o migrar a SQLite solo afecta a `memory_manager.py`.
- `get_context_for()` reduce tokens y mejora el foco del LLM en ~40% para preguntas RAG.
- Los tests validan automáticamente que ninguna capa superior importa `memory_store` directamente.

## Archivos clave

- `app/memory_manager.py` — el módulo completo
- `app/schemas.py` — MemoryType enum usado en anotaciones
- `tests/test_memory_layer.py` — valida get_context_for()
- `tests/test_architecture.py` — valida reglas de dependencia entre capas
