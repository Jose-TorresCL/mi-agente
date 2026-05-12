# ADR-004 — Caché semántica con similitud coseno y TTL

**Estado:** Aceptado  
**Fecha:** 2026-05  
**Autores:** Jose Torres + Asistente IA local

---

## Contexto

El agente llama a Ollama (LLM local) para responder preguntas de RAG y memoria.
Cada llamada tarda entre 3 y 15 segundos dependiendo del modelo y la longitud
de la respuesta. Durante el desarrollo y uso real se observó que el mismo usuario
repite preguntas muy similares en la misma sesión o entre sesiones distintas:

- "¿en qué vamos?" / "¿en qué estamos?" / "¿cuál es el estado actual?"
- "¿cómo funciona Chroma?" / "explícame Chroma" / "qué es Chroma"

Una caché exacta por string (`if pregunta == pregunta_anterior`) no capturaría
estas variaciones. Se necesitaba algo más flexible.

---

## Decisión

Implementar una **caché semántica** que:

1. Convierte cada pregunta a un embedding con `nomic-embed-text` vía Ollama.
2. Compara el embedding nuevo contra los embeddings de respuestas ya cacheadas
   usando **similitud coseno**.
3. Si la similitud supera el umbral **0.85**, devuelve la respuesta cacheada
   sin llamar al LLM.
4. Si no supera el umbral, llama al LLM normalmente y guarda la respuesta
   en la caché con un **TTL de 24 horas**.
5. Las entradas expiradas se eliminan al inicio de cada sesión.

### Valores clave y por qué

| Parámetro | Valor | Razonamiento |
|---|---|---|
| Umbral de similitud | 0.85 | Por debajo se producen falsos positivos (preguntas distintas que reciben la misma respuesta). Por encima se pierden demasiados hits. Calibrado con pruebas manuales. |
| TTL | 24 horas | El estado del proyecto cambia día a día. Una caché de más de 24h devolvería contexto desactualizado sobre tareas o foco actual. |
| Modelo de embedding | nomic-embed-text | Ya disponible en Ollama local, mismo modelo que usa el intent index — no requiere descargar nada adicional. |
| Almacenamiento | Diccionario en memoria (sesión) | Simple, sin dependencias extra. Si se necesita persistencia entre sesiones, migrar a SQLite o archivo JSON. |

---

## Alternativas consideradas

### A. Caché exacta por string
- **Descartada:** Solo funciona con frases idénticas. En uso real las variaciones
  son constantes y el hit rate sería cercano a cero.

### B. Caché semántica persistente entre sesiones (archivo/SQLite)
- **Postergada:** Añade complejidad de serialización de embeddings y gestión
  de archivos. El beneficio no justifica el costo en esta etapa del proyecto.
  Candidato natural para una versión futura.

### C. Sin caché — llamar siempre al LLM
- **Descartada:** Latencia inaceptable en preguntas repetidas durante desarrollo.
  El ciclo pregunta-respuesta de 10s interrumpe el flujo de trabajo.

---

## Consecuencias

### Positivas
- Respuestas instantáneas en preguntas similares ya vistas en la sesión.
- Reduce la carga sobre Ollama durante sesiones largas de desarrollo.
- El comando `!estado` muestra hits/misses/entradas/TTL para observabilidad.

### Negativas / riesgos
- Si el umbral está muy alto (>0.90), el hit rate baja y la caché no ayuda.
- Si el umbral está muy bajo (<0.80), se pueden devolver respuestas incorrectas
  a preguntas distintas.
- La caché no distingue si el contexto cambió (nueva tarea completada, nuevo foco).
  El TTL de 24h mitiga esto pero no lo elimina.

### Deuda técnica aceptada
- La caché actual vive solo en memoria RAM. Al reiniciar el agente se pierde.
  Si en el futuro se quiere persistencia real, hay que migrar el almacenamiento.

---

## Archivos relevantes

- `app/semantic_cache.py` — implementación de la caché
- `app/intelligence.py` — punto de integración (consulta caché antes de llamar al LLM)
- `app/router.py` — `format_estado()` muestra stats de caché en `!estado`
