# ADR-002 — Arquitectura de memoria en capas y tipos formales

**Fecha original:** 2026-04 (Fase 2 — 4 capas JSON)  
**Última actualización:** 19/05/2026 (Fase 8D — MemoryType enum + experience_index)  
**Estado:** ✅ IMPLEMENTADO  
**Autor:** Jose Torres + Lautaro  
**ADRs relacionados:** ADR-003 (memory_manager), ADR-006 (experience_index)

> **Nota de versionado:** Este ADR se expandió para incorporar la capa 5
> (experience_index vectorial) y el enum `MemoryType` formal, añadidos en
> Fases 8A y 8D. Las decisiones originales de Fase 2 no cambiaron.

---

## Contexto

Un asistente IA local necesita diferentes tipos de recuerdo con horizontes
temporales y costos de acceso distintos.

Usar un único archivo plano o solo el historial de conversación produce:
- Contextos demasiado largos (exceden ventana del LLM)
- Pérdida de información entre sesiones
- Sin distinción entre datos volátiles y datos permanentes
- Sin forma de recuperar experiencias pasadas por similitud semántica

---

## Decisión 1 — Arquitectura de 5 capas de memoria (Fase 2 + Fase 8A)

Se adoptó una arquitectura de capas de memoria inspirada en la cognición
humana y en el paper [MemGPT (2023)](https://arxiv.org/abs/2310.08560).

```
┌─────────────────────────────────────────────────────┐
│  CAPA 1 — Working Memory (RAM)                        │
│  Scope: turno actual                                 │
│  Storage: variable en RAM (chat_history list)        │
│  MemoryType: WORKING                                 │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  CAPA 2 — Operational Memory (JSON)                  │
│  Scope: sesión y estado persistente                  │
│  Storage: work_state.json, tasks.json                │
│  MemoryType: WORKING                                 │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  CAPA 3 — Semantic Memory (JSON)                     │
│  Scope: permanente entre sesiones                    │
│  Storage: profile.json, project_facts.json           │
│  MemoryType: SEMANTIC                                │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  CAPA 4 — Episodic Memory (JSON)                     │
│  Scope: histórico de sesiones pasadas                │
│  Storage: episodic_memory.json (resúmenes)           │
│  MemoryType: EPISODIC                                │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  CAPA 5 — Experience Index (Chroma vectorial) [8A]   │
│  Scope: episodios indexados por similitud semántica  │
│  Storage: storage/experience_index/ (Chroma)         │
│  MemoryType: EPISODIC                                │
└─────────────────────────────────────────────────────┘
```

---

## Decisión 2 — MemoryType enum formal (Fase 8D)

**Problema**: las funciones de `memory_manager.py` no declaraban explícitamente
qué tipo de memoria manejaban, lo que permitía mezclas accidentales.

**Solución**: `schemas.py` define `MemoryType(str, Enum)` con 4 valores:

```python
class MemoryType(str, Enum):
    WORKING    = "working"     # RAM + work_state + tasks
    SEMANTIC   = "semantic"    # profile + project_facts
    EPISODIC   = "episodic"    # episodic_memory + experience_index
    PROCEDURAL = "procedural"  # reservado para reglas futuras
```

Todas las funciones públicas de `memory_manager.py` tienen anotaciones
explícitas de tipo con `MemoryType`, documentando la arquitectura directamente
en el código.

**Verificación**:
```powershell
grep MemoryType app/memory_manager.py  # debe devolver 15+ líneas
```

---

## Alternativas consideradas

| Alternativa | Pros | Contras |
|---|---|---|
| Solo historial plano | Simple | Olvida entre sesiones, contexto enorme |
| Base de datos SQL | Robusto | Overkill hasta ~500 episodios |
| Solo RAG | Buen recall semántico | No recuerda datos operacionales |
| **5 capas + MemoryType** ✅ | Cada tipo de dato en su lugar natural | Mayor complejidad inicial |

---

## Consecuencias

- El LLM recibe solo el contexto relevante para cada turno.
- `MemoryType` hace explícita la arquitectura directamente en el código.
- La capa 5 (Chroma) permite recuperación semántica de episodios sin fine-tuning.
- Migrar a SQLite es opt-in cuando episodios superen ~500 entradas.

## Archivos clave

- `app/schemas.py` — `MemoryType` enum
- `app/memory_manager.py` — guardiana con anotaciones MemoryType
- `app/episode_store.py` — capa 4 (JSON) + capa 5 (Chroma)
- `storage/experience_index/` — índice vectorial de episodios
