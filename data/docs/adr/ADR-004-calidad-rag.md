# ADR-004 — Calidad RAG: caché semántica, fidelity check y exclusiones

**Estado:** ✅ Aceptado  
**Fecha:** 2026-05  
**Autores:** Jose Torres + Asistente IA local

---

## Contexto

El carril RAG del agente recupera chunks de documentos con Chroma y genera
una respuesta con Ollama. Se identificaron tres problemas de calidad distintos
que requieren soluciones distintas:

1. **Latencia por repetición**: el mismo usuario repite preguntas similares
   en la sesión — "¿en qué vamos?" / "¿en qué estamos?" / "¿cuál es el estado?"
   Cada llamada tardaba 3-15s sin necesidad.

2. **Respuestas alucinadas o infieles**: el LLM a veces responde con información
   que no está en los chunks recuperados, especialmente cuando los chunks son
   cortos o poco relevantes.

3. **Ruido en el índice**: algunos documentos del proyecto no tienen valor
   informativo real para el asistente (introducciones genéricas, notas de
   instalación obsoletas), pero contaminan los resultados RAG.

---

## Decisión

Se implementaron **tres mecanismos complementarios** de calidad RAG:

### 1. Caché semántica (anti-latencia)

- Cada pregunta se convierte a embedding con `nomic-embed-text`.
- Se compara contra respuestas ya cacheadas usando **similitud coseno ≥ 0.85**.
- Si supera el umbral, devuelve la respuesta cacheada sin llamar al LLM.
- **TTL de 24 horas** — el estado del proyecto cambia día a día.
- Storage: diccionario en RAM (sesión actual).

| Parámetro | Valor | Razonamiento |
|---|---|---|
| Umbral | 0.85 | Más alto que el intent index (0.70) porque aquí se reutiliza una respuesta completa, no solo se clasifica un carril |
| TTL | 24h | Evita respuestas desactualizadas sobre tareas o foco actual |
| Storage | RAM | Simple, sin dependencias extra. Candidato a persistir en SQLite si se necesita entre sesiones |

### 2. Fidelity check (anti-alucinación)

Antes de devolver cualquier respuesta RAG al usuario, se aplican 3 reglas:

```python
def fidelity_check(response: str, chunks: list[str]) -> bool:
    # Regla 1: si no hay chunks recuperados, rechazar
    if not chunks:
        return False
    # Regla 2: si algún chunk está vacío o es muy corto (<20 chars), ignorarlo
    valid_chunks = [c for c in chunks if len(c.strip()) >= 20]
    if not valid_chunks:
        return False
    # Regla 3: si la respuesta es muy corta (<30 chars), probablemente es un fallo
    if len(response.strip()) < 30:
        return False
    return True
```

Si el check falla, el agente responde con un mensaje de fallback transparente
en lugar de una alucinación silenciosa.

### 3. Lista de exclusión (anti-ruido)

Algunos documentos se excluyen del índice RAG por su bajo valor informativo.
La exclusión se declara en la configuración del indexador:

```python
EXCLUDED_DOCS = [
    "hardware-modelos.md",      # información de hardware, no arquitectura
    "chroma-introduccion.md",   # tutorial genérico, no específico del proyecto
    "ollama-api.md",            # referencia de API externa, no decisiones propias
    "estado_proyecto.md",       # snapshot temporal, siempre desactualizado
]
```

Los documentos excluidos aparecen en el log de indexación como `[indexing] EXCLUIDO`
para trazabilidad.

---

## Alternativas consideradas

| Alternativa | Pros | Contras |
|-------------|------|---------|
| Caché exacta por string | Sin dependencia de embeddings | Hit rate cercano a cero en uso real |
| Caché persistente entre sesiones | Más hits | Embeddings deben serializarse; complejidad extra |
| Sin caché | Máxima frescura | Latencia inaceptable en preguntas repetidas |
| Fidelity check por NLI | Más preciso | Requiere modelo adicional no disponible local |
| Excluir docs manualmente al indexar | Control total | Fácil olvidar reindexar tras agregar exclusiones |

---

## Consecuencias

**Positivas:**
- Preguntas similares ya vistas en la sesión se responden en <100ms.
- El fidelity check elimina alucinaciones silenciosas: el usuario recibe
  una respuesta honesta de "no encontré información" en lugar de inventada.
- La lista de exclusión mantiene el índice limpio sin necesidad de revisar
  manualmente los 251 chunks actuales.

**Trade-offs:**
- La caché en RAM se pierde al reiniciar el agente.
- El fidelity check puede rechazar respuestas válidas si el LLM es conciso.
  El umbral de 30 chars es conservador y podría ajustarse.
- Agregar un documento a la lista de exclusión requiere reindexar manualmente.

---

## Archivos relevantes

- `app/semantic_cache.py` — caché semántica
- `app/rag_pipeline.py` — fidelity check integrado
- `app/indexing_core.py` — lista de exclusión y log `[indexing] EXCLUIDO`
- `app/intelligence.py` — punto de integración de los tres mecanismos
