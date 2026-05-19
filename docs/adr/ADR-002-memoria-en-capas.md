# ADR-002 — Arquitectura de memoria en capas y tipos formales

**Fecha:** 2026-04 → actualizado 2026-05  
**Estado:** ✅ Aceptado  
**Autor:** Jose Torres

---

## Contexto

Un asistente IA local necesita diferentes tipos de "recuerdo" con horizontes
temporales y costos de acceso distintos.

Usar un único archivo plano o solo el historial de conversación produce:
- Contextos demasiado largos (exceden ventana del LLM)
- Pérdida de información entre sesiones
- Sin distinción entre datos volátiles y datos permanentes

## Decisión

Se adoptó una **arquitectura de 5 capas de memoria**, con tipos formales
definidos mediante `MemoryType` enum en `app/schemas.py`.

```
┌─────────────────────────────────────────────────────┐
│  CAPA 1 — Memoria de trabajo (Working Memory)       │
│  Scope: turno actual                                │
│  Contenido: input del usuario + respuesta en curso  │
│  Storage: variable en RAM (chat_history list)       │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  CAPA 2 — Memoria corta (Short-Term / Episódica)    │
│  Scope: sesión actual (~10 turnos)                  │
│  Contenido: historial de mensajes de la sesión      │
│  Storage: storage/memory.json → clave "messages"    │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  CAPA 3 — Memoria semántica (Semantic / RAG)        │
│  Scope: permanente entre sesiones                   │
│  Contenido: documentos indexados del proyecto       │
│  Storage: storage/chroma/ (vectores Chroma)         │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  CAPA 4 — Memoria declarativa (Long-Term)           │
│  Scope: permanente, estructurada                    │
│  Contenido: perfil, tareas, hechos, work_state,     │
│             episodios de texto                      │
│  Storage: storage/memory.json (secciones separadas) │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  CAPA 5 — Experience Index (Episódica vectorial)    │
│  Scope: permanente, búsqueda semántica              │
│  Contenido: episodios de sesión + señal éxito/fallo │
│  Storage: storage/chroma/ colección experience_index│
└─────────────────────────────────────────────────────┘
```

### MemoryType enum

Cada pieza de contexto que se inyecta al LLM tiene un tipo formal
definido en `app/schemas.py`:

```python
class MemoryType(str, Enum):
    PROFILE    = "profile"     # quién es el usuario
    WORK_STATE = "work_state"  # foco actual y siguiente paso
    TASKS      = "tasks"       # tareas abiertas
    EPISODE    = "episode"     # última sesión episódica
    FACTS      = "facts"       # hechos declarativos guardados
```

Esto permite solicitar contexto selectivo por tipo en vez de volcar todo:

```python
# Antes: contexto completo siempre
ctx = memory_manager.get_full_context()

# Ahora: contexto selectivo por tipo
ctx = memory_manager.get_context_for([MemoryType.WORK_STATE, MemoryType.TASKS])
```

## Alternativas consideradas

| Alternativa | Pros | Contras |
|-------------|------|---------|
| Solo historial plano | Simple | Olvida entre sesiones, contexto enorme |
| Base de datos SQL | Robusto | Overkill para proyecto local |
| Solo RAG | Buen recall semántico | No recuerda datos operacionales (tareas, foco) |
| **5 capas + MemoryType** ✅ | Cada tipo de dato en su lugar natural, recuperación selectiva | Mayor complejidad inicial |

## Consecuencias

**Positivas:**
- El LLM recibe solo el contexto relevante para cada turno (recuperación selectiva).
- La memoria declarativa persiste indefinidamente sin depender del historial.
- Cada capa se puede actualizar, limpiar o migrar de forma independiente.
- El `MemoryType` enum actúa como contrato: si se agrega un tipo nuevo,
  todas las funciones de contexto deben manejarlo explícitamente.

**Trade-offs:**
- Requiere disciplina para no mezclar responsabilidades entre capas.
- El archivo `storage/memory.json` crece con el tiempo → requiere
  política de limpieza (ej: máximo N episodios).
- La Capa 5 (experience_index) vive en Chroma separado del RAG principal,
  lo que requiere gestión de dos colecciones distintas.

## Documento relacionado

Ver [`docs/arquitectura-memoria.md`](../arquitectura-memoria.md) para el mapa completo con ejemplos de datos.

## Archivos clave

- `storage/memory.json` — capas 2 y 4
- `storage/chroma/` — capa 3 (RAG) y capa 5 (experience_index)
- `app/memory_manager.py` — acceso unificado a todas las capas
- `app/schemas.py` — `MemoryType` enum y modelos de datos
- `app/episode_store.py` — gestión de la Capa 5
