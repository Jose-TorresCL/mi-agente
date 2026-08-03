# ADR-001: Router híbrido de 3 capas

**Estado:** Aceptado  
**Fecha:** 2026-05-20  
**Archivo principal:** `app/router.py`

---

## Contexto

Cada mensaje del usuario necesita ser clasificado en un "carril" de ejecución: responder desde memoria, buscar en documentos (RAG), ejecutar una herramienta, o salir. Esta clasificación ocurre en cada turno, por lo que su velocidad y precisión afectan directamente la experiencia.

El problema es que un LLM local (llama3.2) tarda entre 15 y 30 segundos solo para decidir el carril — antes de generar la respuesta real. Eso es inaceptable en un asistente conversacional.

---

## Decisión

Usar un router de **3 capas en cascada**, donde cada capa solo se activa si la anterior no resolvió:

```
Capa 1 — Keywords (0ms)
  Si la pregunta contiene una keyword conocida → carril directo.
  Ejemplo: "mis tareas" → memory/tasks
           "crea una tarea" → tool_create_task

Capa 2 — Embeddings semánticos (~50ms)
  Si Capa 1 no resolvió → buscar en intent_index (Chroma).
  Solo activa si similitud >= EMBED_THRESHOLD (0.82).
  Requiere ejecutar build_intent_index.py una vez.

Capa 3 — Fallback directo (0ms)
  Si Capa 1 y Capa 2 no resuelven → carril 'rag' sin llamada al LLM.
  Eliminado _route_by_llm() que causaba 30s de latencia por turno.
```

---

## Consecuencias

**Positivas:**
- Latencia de clasificación: 0–50ms en vez de 15–30s.
- El LLM solo se usa para generar respuestas, no para clasificar.
- Fácil de extender: agregar keywords a las listas o ejemplos al intent_index.
- Testeable sin Ollama: Capa 1 es lógica pura Python.

**Negativas:**
- Las keywords deben mantenerse manualmente. Si aparece una nueva forma de preguntar algo, hay que agregarla a la lista.
- El intent_index requiere ejecutar `build_intent_index.py` al agregar ejemplos nuevos (no es automático).
- Preguntas muy ambiguas o nuevas van a RAG por defecto, que puede no ser el carril correcto.

---

## Alternativas descartadas

| Alternativa | Por qué se descartó |
|---|---|
| Router LLM puro | 15–30s de latencia solo para clasificar. Inaceptable. |
| Solo keywords | No cubre preguntas con sinónimos o formulaciones nuevas. |
| Solo embeddings | Más lento que keywords; requiere Ollama activo siempre. |
| Clasificador entrenado | Complejidad innecesaria para el tamaño actual del proyecto. |

---

## Notas de implementación

- `SESSION_STATS` registra cuántas consultas resolvió cada capa (`kw`, `emb`, `llm`).
- El comando `!estado` en el chat muestra esas métricas en tiempo real.
- `EMBED_THRESHOLD = 0.82` — si la similitud es menor, se prefiere el fallback sobre una clasificación incorrecta.
