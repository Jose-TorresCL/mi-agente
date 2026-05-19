# ADR-006 — Experience Index: feedback loop de calidad entre sesiones

**Estado:** ✅ Aceptado  
**Fecha:** 2026-05  
**Autores:** Jose Torres + Asistente IA local

---

## Contexto

El agente acumula conocimiento sobre el proyecto a través del RAG (documentos)
y de la memoria declarativa (perfil, tareas, hechos). Pero ninguno de esos
mecanismos captura lo que *pasó* en sesiones anteriores:

- ¿Qué temas se discutieron la última vez?
- ¿Fue esa sesión productiva o terminó sin avances?
- ¿Qué contexto necesito recuperar para continuar donde lo dejé?

Además, no había forma de mejorar la calidad del agente en el tiempo:
cada sesión era independiente, sin señal de qué funcionó bien y qué no.

## Decisión

Se implementó un **experience index** como Capa 5 de la arquitectura de memoria,
con un **feedback loop de calidad** al final de cada sesión.

### Estructura del episodio

Cada sesión genera un documento episódico con esta estructura:

```python
@dataclass
class Episode:
    session_id: str        # timestamp ISO "2026-05-19T12:37"
    summary: str           # resumen generado por el LLM
    turns: int             # número de turnos de la sesión
    dominant_lane: str     # carril más usado en la sesión
    tasks_completed: int   # tareas completadas en la sesión
    exitoso: bool          # señal de calidad del usuario (s/n)
    timestamp: str         # ISO 8601
```

### Flujo de indexación

```
Fin de sesión
    ↓
[1] LLM genera resumen del historial de turnos
    ↓
[2] episode_store.index_episode(episode)
    → embed(summary) con nomic-embed-text
    → guardar en Chroma colección "experience_index"
    ↓
[3] episode_store.close_session(session_id, lane, tasks)
    → actualiza metadatos del episodio en Chroma
    ↓
[4] usuario responde ¿fue productiva esta sesión? (s/n)
    ↓
[5] episode_store.mark_episode(session_id, exitoso=True/False)
    → actualiza campo exitoso en el documento de Chroma
```

### Recuperación episódica

Cuando el router detecta el carril `memory` con intent de episodio
("¿qué aprendí la sesión anterior?", "¿en qué quedamos?"), se ejecuta:

```python
episodes = episode_store.search(query, k=3)
# Devuelve los 3 episodios más similares semánticamente
# con sus metadatos: turns, lane, exitoso, timestamp
```

### Boost de relevancia por éxito

Los episodios marcados como exitosos (`exitoso=True`) reciben un boost
+0.15 en su score de relevancia al recuperarse:

```python
for ep in results:
    if ep.metadata.get("exitoso"):
        ep.score += 0.15
results.sort(key=lambda x: x.score, reverse=True)
```

Esto hace que el agente tienda a recuperar y referirse a sesiones productivas
en lugar de sesiones fallidas.

### Colección separada del RAG

El experience_index vive en la colección `"experience_index"` de Chroma,
**separada** de la colección RAG principal. Esto garantiza que:

- La reindexación de documentos (`python indexacion.py`) no borra los episodios.
- Los episodios no contaminan los resultados de búsqueda RAG.
- El experience_index puede crecer indefinidamente sin afectar el rendimiento RAG.

## Alternativas consideradas

| Alternativa | Pros | Contras |
|-------------|------|---------|
| Solo guardar episodios en memory.json (texto) | Simple | No permite búsqueda semántica entre sesiones |
| Episodios en la misma colección RAG | Un solo vectorstore | Contamina resultados RAG con contenido episódico |
| Sin señal de calidad | Sin fricción para el usuario | No hay base para mejorar o filtrar episodios |
| Señal automática por métricas (tareas completadas) | Sin intervención del usuario | No captura valor subjetivo de la sesión |
| **Experience index separado + señal s/n** ✅ | Semántico, separado, con calidad explícita | Requiere colección Chroma adicional y gestión de metadatos |

## Consecuencias

**Positivas:**
- El agente puede responder "¿qué aprendí la sesión anterior?" con contenido real
  recuperado semánticamente, no solo el último texto guardado.
- La señal `exitoso` crea un feedback loop: sesiones productivas tienen más
  probabilidad de ser referenciadas en futuras sesiones.
- La separación de colecciones garantiza que `python indexacion.py`
  nunca borre el historial de episodios.
- El log `[episode_store]` permite trazabilidad completa del ciclo de vida
  de cada episodio.

**Trade-offs:**
- Si el LLM tarda demasiado en generar el resumen al cerrar (timeout),
  el episodio se guarda sin resumen (fallback a texto vacío) — esto ya ocurrió
  en la sesión de 2026-05-19T12:39.
- La señal s/n es binaria. Una escala 1-5 daría más resolución pero añade
  fricción al usuario al salir.
- El boost +0.15 es fijo y no se ha calibrado con datos reales todavía.

### Deuda técnica aceptada

- No hay límite de episodios por sesión en Chroma. A largo plazo,
  si hay cientos de episodios, el tiempo de búsqueda podría aumentar.
  Solución futura: retención rolling de los últimos N episodios.
- El boost +0.15 debería calibrarse observando cuántos episodios exitosos
  vs. fallidos existen después de 30+ sesiones reales.

## Archivos clave

- `app/episode_store.py` — gestión del experience_index
- `app/schemas.py` — `Episode` dataclass
- `app/intelligence.py` — integración en el carril `exit`
- `storage/chroma/` — colección `experience_index`
