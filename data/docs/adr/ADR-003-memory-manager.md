# ADR-003 — `memory_manager` como guardián único de la memoria

**Fecha:** 2026-05  
**Estado:** ✅ Aceptado  
**Autor:** Jose Torres

---

## Contexto

Antes de este módulo, tanto `tools.py` como `chat_core.py` importaban
directamente `memory_store` y leían/escribían `storage/memory.json` de
forma independiente.

Eso generaba:
- Acoplamiento fuerte entre lógica de negocio e infraestructura de storage
- Riesgo de inconsistencias si el formato del JSON cambiaba
- Dificultad para testear sin tocar archivos reales
- Violación del principio de responsabilidad única (SRP)

## Decisión

Se creó `app/memory_manager.py` como **fachada única** de acceso a la
capa de memoria declarativa, con soporte para recuperación selectiva
mediante `MemoryType`.

### Interfaz pública del módulo

```python
# Recuperación selectiva por tipo (interfaz preferida)
get_context_for(types: list[MemoryType]) → str

# Lectura por tipo específico
get_profile()         → dict
get_project_facts()   → dict
get_tasks()           → dict
get_work_state()      → dict
get_last_episode()    → dict | None

# Contextos precompuestos (atajos comunes)
get_full_context()    → str   # todos los tipos
get_working_context() → str   # WORK_STATE + TASKS
get_semantic_context()→ str   # PROFILE + FACTS
get_episodic_context()→ str   # EPISODE

# Escritura
save_fact(key, value)           → dict
update_state(**kwargs)          → dict
create_task(title, priority)    → dict
complete_task(task_id)          → dict
record_episode(summary, turns)  → dict
```

### Regla de dependencias

```
chat_core.py  ──→  memory_manager.py  ──→  memory_store.py  ──→  memory.json
tools.py      ──→  memory_manager.py
intelligence.py → memory_manager.py

# NUNCA:
chat_core.py   ──✗──  memory_store.py   (importación directa prohibida)
tools.py       ──✗──  memory_store.py
intelligence.py ──✗── memory_store.py
```

### Anotaciones de tipo en tools

Cada herramienta en `tools.py` anota qué tipo de memoria lee o escribe:

```python
# Ejemplo: la tool de perfil solo necesita PROFILE
def get_profile_tool() -> str:
    # MemoryType.PROFILE
    return memory_manager.get_context_for([MemoryType.PROFILE])
```

Esto hace explícita la dependencia de memoria de cada herramienta
sin necesidad de leer el código interno.

## Alternativas consideradas

| Alternativa | Pros | Contras |
|-------------|------|---------|
| Acceso directo desde cada módulo (anterior) | Sin burocracia | Acoplamiento alto, difícil de testear |
| ORM con SQLite | Tipado fuerte | Overkill, requiere migración de datos |
| **Fachada `memory_manager`** ✅ | Un solo punto de control, testeable | Un archivo más en el proyecto |

## Consecuencias

**Positivas:**
- Cambiar el formato de `memory.json` o migrar a SQLite solo afecta a `memory_manager.py`.
- Los tests de integración (`test_memory_layer.py`) validan la regla de dependencias automáticamente.
- `get_context_for([MemoryType.WORK_STATE, MemoryType.TASKS])` permite al LLM recibir
  solo lo que necesita para cada carril, reduciendo tokens innecesarios.
- `chat_core.py` y `tools.py` son más simples y legibles.

**Trade-offs:**
- Cualquier nueva función de memoria debe agregarse a `memory_manager.py` primero.
- Requiere disciplina del desarrollador para respetar la regla (los tests la enforzan).

## Archivos clave

- `app/memory_manager.py` — el módulo
- `app/schemas.py` — `MemoryType` enum
- `tests/test_memory_layer.py` — tests que validan las reglas de dependencia
