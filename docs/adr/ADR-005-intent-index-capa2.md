# ADR-005 — Intent index con embeddings (Capa 2 del router)

**Estado:** Aceptado  
**Fecha:** 2026-05  
**Autores:** Jose Torres + Asistente IA local

---

## Contexto

El router híbrido clasifica cada pregunta del usuario en un carril de ejecución
(`memory`, `rag`, `tool_create_task`, etc.). La Capa 1 usa keywords exactas y
es instantánea, pero tiene cobertura limitada: solo reconoce frases que están
literalmente en las listas de `router.py`.

Antes de la Capa 2, cualquier frase que no hacía match exacto de keyword caía
directamente a la Capa 3 (LLM), con una latencia de 3-8 segundos. Ejemplos
reales que tardaban 25s por ir al LLM:

- "¿qué hago hoy?" → debería ir a `memory` en <1s
- "¿quién soy yo?" → debería ir a `memory` en <1s
- "¿cómo funciona Chroma?" → debería ir a `rag` en <1s

---

## Decisión

Agregar una **Capa 2 basada en embeddings** entre keywords y LLM:

1. Se mantiene un índice vectorial (`storage/intent_index`) construido a partir
   de `data/intent_examples.json` — frases de ejemplo etiquetadas por carril.
2. Cada nueva pregunta se embebe con `nomic-embed-text` y se busca el ejemplo
   más cercano por similitud coseno usando **Chroma** como vectorstore.
3. Si la similitud supera el umbral **0.70** y el carril encontrado es válido,
   se usa ese carril directamente sin llamar al LLM.
4. Si la similitud es menor a 0.70, se pasa a la Capa 3 (LLM).
5. El índice se reconstruye ejecutando `python build_intent_index.py` cada vez
   que se agregan ejemplos al JSON.

### Valores clave y por qué

| Parámetro | Valor | Razonamiento |
|---|---|---|
| Umbral similitud | 0.70 | Más bajo que la caché semántica (0.85) porque el objetivo es clasificar carriles, no recuperar respuestas exactas. Un 0.70 permite variaciones naturales del lenguaje sin falsos positivos graves. |
| Vectorstore | Chroma | Ya es la dependencia del sistema RAG. Sin dependencia extra. Persiste en disco. |
| Modelo de embedding | nomic-embed-text | Mismo que la caché semántica. Un solo modelo para todo el sistema. |
| Formato de ejemplos | JSON (`data/intent_examples.json`) | Editable sin tocar código. Cualquier ajuste de cobertura se hace agregando líneas al JSON y re-ejecutando el build. |
| Singleton `_intent_db` | Sí | Chroma tarda ~200ms en inicializar. El singleton evita recrearlo en cada consulta. |

### Guardia para carriles de escritura

Si la pregunta tiene forma de interrogación (`¿...?`) y el carril candidato
es un carril de escritura (`tool_create_task`, `tool_save_fact`, etc.), la
Capa 2 bloquea el resultado y pasa a la Capa 3. Esto evita que una pregunta
como "¿qué tareas podríamos crear?" ejecute una herramienta de escritura por
alta similitud con un ejemplo de `tool_create_task`.

---

## Alternativas consideradas

### A. Solo keywords (sin Capa 2)
- **Descartada:** Requiere anticipar todas las variaciones posibles en el código.
  No escala — cada nueva frase natural obliga a editar `router.py`.
  El LLM tarda 3-8s en clasificar frases simples.

### B. Ir directo al LLM para todo lo que no hace match de keyword
- **Descartada:** Latencia inaceptable para preguntas frecuentes como
  "¿qué hago hoy?". El LLM es el recurso más caro del sistema.

### C. Clasificador entrenado (sklearn, transformers)
- **Postergada:** Requiere dataset etiquetado grande y proceso de entrenamiento.
  Con ~100 ejemplos en el JSON la cobertura ya es suficiente para la etapa actual.
  Candidato para cuando el sistema tenga más usuarios o más carriles.

### D. Embeddings con otro vectorstore (FAISS, Qdrant)
- **Descartada en esta etapa:** Chroma ya está como dependencia del RAG.
  Añadir otro vectorstore duplica la complejidad de instalación sin beneficio
  claro a esta escala.

---

## Consecuencias

### Positivas
- Frases naturales no previstas en keywords se resuelven en ~50ms (Capa 2)
  en vez de 3-8s (Capa 3 LLM).
- Agregar cobertura no requiere tocar código — solo editar el JSON y
  re-ejecutar `build_intent_index.py`.
- El logging diferenciado (`[router:kw]`, `[router:emb]`, `[router:llm]`)
  permite medir qué capa resuelve cada consulta y detectar brechas.

### Negativas / riesgos
- Requiere que `nomic-embed-text` esté disponible en Ollama. Si el modelo
  no está descargado, la Capa 2 se salta silenciosamente (falla segura).
- El índice puede quedar desactualizado si se agregan ejemplos al JSON
  sin re-ejecutar el build. No hay detección automática de esto.
- Con pocos ejemplos (<10 por carril) la similitud puede ser baja y la
  Capa 2 pasa todo al LLM, anulando el beneficio.

### Deuda técnica aceptada
- No hay rebuild automático del índice al detectar cambios en el JSON.
  Requiere intervención manual. Aceptable en esta etapa.
- Los tests unitarios cubren la Capa 1 (keywords). La Capa 2 solo se
  puede testear con Ollama corriendo — no hay tests automáticos para ella todavía.

---

## Archivos relevantes

- `data/intent_examples.json` — ejemplos etiquetados por carril
- `build_intent_index.py` — construye el índice vectorial en `storage/intent_index`
- `app/router.py` — `_route_by_embeddings()` implementa la Capa 2
- `tests/test_router.py` — tests unitarios de Capa 1 (keywords)
