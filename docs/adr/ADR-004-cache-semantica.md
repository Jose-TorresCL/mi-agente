# ADR-004: Caché semántica con nomic-embed-text

**Estado:** Aceptado  
**Fecha:** 2026-05-20  
**Archivo principal:** `app/semantic_cache.py`

---

## Contexto

Un LLM local tarda 15–60 segundos en generar una respuesta dependiendo del hardware. Si el usuario hace la misma pregunta dos veces (o una pregunta muy similar), el agente debería responder instantáneamente usando la respuesta anterior — sin volver a llamar al LLM.

Una caché tradicional por texto exacto no sirve: "¿cuáles son mis tareas?" y "dime mis tareas pendientes" deben ser reconocidas como la misma pregunta aunque el texto sea diferente.

---

## Decisión

Implementar una **caché semántica** que usa embeddings para comparar preguntas:

```
pregunta nueva
    → nomic-embed-text → vector
        → comparar con vectores en caché (cosine similarity)
            → si similitud >= CACHE_THRESHOLD → devolver respuesta cacheada
            → si similitud <  CACHE_THRESHOLD → llamar al LLM → guardar en caché
```

**Parámetros clave:**
- Modelo de embeddings: `nomic-embed-text` (ya en el stack, 274MB, corre local).
- Umbral de similitud: `0.92` (alto para evitar falsos positivos — preguntas distintas que se confunden).
- TTL de entradas: configurable en `app/config.py` (por defecto 24h).
- Backend de almacenamiento: in-memory con persistencia opcional en JSON.

---

## Consecuencias

**Positivas:**
- Respuestas repetidas o similares: de 30s → <100ms.
- No requiere modelos adicionales — usa `nomic-embed-text` que ya corre en Ollama.
- Reduce la carga sobre el LLM en sesiones largas con preguntas recurrentes.
- El comando `!estado` muestra hits/misses de la caché en tiempo real.

**Negativas:**
- Un umbral de 0.92 es muy estricto — la caché solo ayuda cuando las preguntas son casi idénticas. Preguntas parecidas pero distintas no se benefician.
- Si el estado del proyecto cambia (nueva tarea, nuevo sprint) pero la caché tiene una respuesta vieja, el usuario recibe información desactualizada hasta que expire el TTL.
- La caché crece en memoria si hay muchas preguntas únicas. En sesiones muy largas puede ser significativo.

---

## Alternativas descartadas

| Alternativa | Por qué se descartó |
|---|---|
| Caché por texto exacto | No maneja sinónimos ni reformulaciones. Muy poca cobertura práctica. |
| Redis como backend | Dependencia externa innecesaria para un proyecto local. |
| Umbral 0.80 | Demasiado permisivo: preguntas distintas comparten respuesta incorrectamente. |
| Sin caché | Cada pregunta paga 15–60s de latencia. Experiencia de usuario inaceptable. |

---

## Notas de implementación

- `CACHE_THRESHOLD = 0.92` en `app/semantic_cache.py`.
- `cache_stats()` devuelve `{hits, misses, entries, ttl_hours}` — usado por `format_estado()` en `router.py`.
- El TTL se configura en `app/config.py` → `CACHE_TTL_HOURS`. Cambiar a `0` desactiva la expiración.
- Tests: `tests/test_lautaro.py::test_cache_semantico`.
