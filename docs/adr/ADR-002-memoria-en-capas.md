# ADR-002 — Arquitectura de memoria en 4 capas

**Fecha:** 2026-04  
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

Se adoptó una **arquitectura de 4 capas de memoria**, inspirada en la
cognición humana y en el paper [MemGPT (2023)](https://arxiv.org/abs/2310.08560):

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
│  Storage: storage/chroma_db/ (vectores Chroma)      │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  CAPA 4 — Memoria declarativa (Long-Term)           │
│  Scope: permanente, estructurada                    │
│  Contenido: perfil, tareas, hechos, work_state,     │
│             episodios                               │
│  Storage: storage/memory.json (secciones separadas) │
└─────────────────────────────────────────────────────┘
```

## Alternativas consideradas

| Alternativa | Pros | Contras |
|-------------|------|---------|
| Solo historial plano | Simple | Olvida entre sesiones, contexto enorme |
| Base de datos SQL | Robusto | Overkill para proyecto local |
| Solo RAG | Buen recall semántico | No recuerda datos operacionales (tareas, foco) |
| **4 capas** ✅ | Cada tipo de dato en su lugar natural | Mayor complejidad inicial |

## Consecuencias

**Positivas:**
- El LLM recibe solo el contexto relevante para cada turno.
- La memoria declarativa persiste indefinidamente sin depender del historial.
- Cada capa se puede actualizar, limpiar o migrar de forma independiente.

**Trade-offs:**
- Requiere disciplina para no mezclar responsabilidades entre capas.
- El archivo `storage/memory.json` crece con el tiempo → requiere
  política de limpieza (ej: máximo N episodios).

## Documento relacionado

Ver [`docs/arquitectura-memoria.md`](../arquitectura-memoria.md) para el mapa completo con ejemplos de datos.

## Archivos clave

- `storage/memory.json` — capas 2 y 4
- `storage/chroma_db/` — capa 3
- `app/memory_manager.py` — acceso unificado a todas las capas
