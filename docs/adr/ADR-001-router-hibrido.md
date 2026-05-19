# ADR-001 — Router híbrido de 3 capas

**Fecha:** 2026-04  
**Estado:** ✅ Aceptado  
**Autor:** Jose Torres

---

## Contexto

El asistente necesita clasificar la intención del usuario en cada turno para
despachar la consulta al carril correcto (RAG, memoria, tools, salida).

Las opciones eran:
- Usar solo el LLM para clasificar → lento (~3-8s por consulta)
- Usar solo keywords exactas → rápido pero rígido
- Usar solo embeddings → ~50ms pero requiere infraestructura previa

## Decisión

Se adoptó un **router de 3 capas en cascada**, con costo creciente:

```
Capa 1: Keywords   → 0ms    (regex/contains sobre lista fija)
Capa 2: Embeddings → ~50ms  (similitud coseno en Chroma / intent_index)
Capa 3: LLM        → 3-8s   (último recurso, frases desconocidas)
```

Cada capa retorna `None` si no tiene confianza suficiente,
pasando el control a la siguiente. Solo la Capa 3 siempre responde.

**Umbral Capa 2:** similitud coseno ≥ 0.70 (convertido de distancia Chroma: `sim = 1 - dist/2`).

### Carriles reconocidos

El router clasifica cada turno en uno de los siguientes carriles:

| Carril | Tipo | Descripción |
|---|---|---|
| `exit` | TERMINAL | Despedida / salida de la sesión |
| `memory` | Consulta | Perfil, tareas, foco, episodios pasados |
| `rag` | Consulta | Preguntas sobre documentos del proyecto |
| `tool_list_files` | Tool | Lista archivos del proyecto |
| `tool_read_file` | Tool | Lee un archivo específico |
| `tool_save_fact` | Tool | Guarda un hecho en memoria declarativa |
| `tool_create_task` | Tool | Crea una tarea |
| `tool_complete_task` | Tool | Marca tarea como completada |
| `unsupported` | Fallback | Petición fuera del alcance actual |

La guardia de escritura de la Capa 2 bloquea carriles de escritura (`tool_*`) si la
pregunta tiene forma interrogativa, evitando ejecuciones accidentales.

## Alternativas consideradas

| Alternativa | Pros | Contras |
|-------------|------|---------|
| Solo LLM | Flexible, sin mantenimiento de listas | Lento en cada turno |
| Solo keywords | Instantáneo | No escala, muy frágil |
| Embeddings + LLM | Buen balance | Requiere construir índice previo |
| **Híbrido 3 capas** ✅ | Rápido en el caso frecuente, robusto en el infrecuente | Complejidad mayor |

## Consecuencias

**Positivas:**
- El 90%+ de las consultas se resuelven en Capa 1 (0ms).
- El log diferenciado `[router:kw]`, `[router:emb]`, `[router:llm]`
  permite monitorear la distribución de carga real.
- Agregar nuevas intenciones solo requiere añadir keywords o ejemplos al índice.
- Los 9 carriles están cubiertos por `test_routing_matrix.py` con 30 casos.

**Trade-offs:**
- Capa 2 requiere ejecutar `build_intent_index.py` antes del primer uso.
- Si el índice no existe, Capa 2 se salta silenciosamente → degradación controlada.
- Las listas de keywords deben mantenerse a medida que crecen los carriles.

## Archivos clave

- `app/router.py` — implementación de las 3 capas
- `build_intent_index.py` — genera `storage/intent_index/`
- `data/intent_examples.json` — ejemplos etiquetados por carril
- `tests/test_routing_matrix.py` — matriz de 30 casos de prueba
