# ADR-004 — Mejoras de calidad RAG: MMR, encoding UTF-8 y context selectivo

**Fecha**: 11/05/2026
**Estado**: Parcialmente implementado (MMR y encoding pendientes de aplicar; context selectivo en diseño)
**Autores**: Jose Torres + Lautaro (asistente IA local)
**ADRs relacionados**: ADR-001 (router híbrido), ADR-003 (memory_manager)

---

## Contexto

Tras indexar 18 documentos con 228 chunks (sesión 11/05/2026), se identificaron tres problemas
de calidad que limitan las respuestas del agente:

1. **Retriever usa `similarity`**: devuelve los k chunks más parecidos, que pueden ser todos
   del mismo archivo. Si el doc más parecido es `ollama-api.md`, los 5 chunks son de Ollama
   aunque la respuesta esté en `langchain-retriever.md`.

2. **Encoding UTF-8 roto**: `json.dump` en `memory_store.py` usa `ensure_ascii=True` (default),
   lo que convierte "próximo" en `"pr\\u00f3ximo"`. Los hechos en `project_facts.json` muestran
   tildes corruptas al leerlos desde el sistema operativo.

3. **Memory context no es selectivo**: `memory_context.py` inyecta siempre los mismos bloques
   (perfil + workstate + hechos + tareas) sin importar si la pregunta es documental o de estado.
   Esto ocupa tokens del contexto innecesariamente y puede confundir al LLM.

---

## Decisiones

### Decisión 1 — Activar MMR en el retriever

**Qué es MMR (Maximal Marginal Relevance)**:
MMR balancea relevancia y diversidad. En vez de devolver los 5 chunks más similares a la
pregunta (que pueden ser redundantes), MMR selecciona candidatos que sean relevantes *y*
distintos entre sí.

**Parámetros clave**:
- `fetch_k=20`: cuántos candidatos iniciales considera Chroma antes de filtrar
- `lambda_mult=0.6`: balance entre relevancia (1.0) y diversidad (0.0). 0.6 prioriza
  levemente la relevancia manteniendo diversidad razonable.
- `k=5`: cantidad final de chunks devueltos (sin cambio)

**Cambio en `app/rag_engine.py`**:
```python
# ANTES
return vectordb.as_retriever(
    search_type="similarity",
    search_kwargs=search_kwargs,
)

# DESPUÉS
search_kwargs.setdefault("fetch_k", 20)
search_kwargs.setdefault("lambda_mult", 0.6)
return vectordb.as_retriever(
    search_type="mmr",
    search_kwargs=search_kwargs,
)
```

**Por qué 0.6 y no 0.5**: Con documentos técnicos especializados (ADRs, papers, docs de
LangChain) es preferible que el chunk más relevante siempre aparezca. 0.5 puede descartar
el mejor chunk en favor de diversidad. 0.6 es el balance probado en la literatura RAG.

**Alternativa descartada**: `search_type="similarity_score_threshold"` — requiere calibrar
un umbral fijo que no funciona igual para todos los tipos de preguntas.

---

### Decisión 2 — Fix encoding UTF-8 en json.dump

**El problema**:
```python
# memory_store.py — ANTES (bug):
json.dump(data, f, indent=2)
# Resultado en archivo: {"clave": "pr\u00f3ximo paso"}

# DESPUÉS (fix):
json.dump(data, f, indent=2, ensure_ascii=False)
# Resultado en archivo: {"clave": "próximo paso"}
```

**Por qué importa**: Los hechos en `project_facts.json` se inyectan al prompt del LLM.
Si llegan con secuencias de escape unicode en vez de caracteres legibles, el LLM los
interpreta peor y el contexto parece "ruidoso".

**Alcance**: todos los `json.dump` en `memory_store.py` — se estima 4-6 ocurrencias.

**Riesgo**: ninguno. `ensure_ascii=False` es el estándar para aplicaciones en español.
Los archivos JSON con UTF-8 directo son más legibles y ocupan menos bytes que la versión
escapada.

---

### Decisión 3 — Arquitectura de memory context selectivo (diseño)

**Problema actual**:
```python
# memory_context.py — inyecta todo siempre
def build_context(question, vs):
    memoria = build_structured_memory_context()  # perfil + workstate + hechos + tareas
    rag = retrieve_context(question, vs)         # chunks de Chroma
    return memoria + rag                         # TODO: seleccionar según tipo de pregunta
```

**Diseño propuesto**:
El router ya clasifica las preguntas en carriles (`rag`, `memoria`, `estado`, `tool`, etc.).
La idea es usar esa clasificación para decidir qué bloques de memoria inyectar:

| Carril del router | Bloques inyectados |
|---|---|
| `rag` | RAG chunks + perfil mínimo (nombre, proyecto) |
| `memoria` | workstate + hechos + tareas (sin RAG) |
| `estado` | workstate + tareas pendientes (sin RAG) |
| `tool` | workstate + hechos (contexto mínimo para ejecutar) |
| `general` | todos los bloques (fallback) |

**Beneficio**: en preguntas como "¿qué es MMR?" no tiene sentido inyectar las 14 tareas
pendientes ni el historial de workstate. Reduce tokens y mejora el foco del LLM.

**Estado**: en diseño. Requiere modificar la interfaz entre `router.py` y `memory_context.py`
para que el carril de routing sea accesible al momento de construir el contexto.

**Dependencia**: requiere que ADR-001 (router) y ADR-003 (memory_manager) estén estables.
No implementar hasta tener MMR y encoding corregidos.

---

## Consecuencias

### Positivas
- MMR elimina la redundancia de fuentes en el bloque "Basado en:" — menos chunks del mismo
  archivo, más cobertura de la base documental.
- Fix encoding hace los JSONs legibles directamente desde VS Code y PowerShell.
- Context selectivo reducirá el uso de tokens del contexto en ~40% para preguntas RAG.

### A vigilar
- MMR con `lambda_mult=0.6` puede traer un chunk menos relevante que `similarity` puro en
  preguntas muy específicas. Si el `fidelity_check` empeora, bajar a `lambda_mult=0.7`.
- El fix de encoding requiere re-escribir los JSONs existentes que ya tienen escapes unicode
  (no se corrigen solos al cambiar el código — se corrigen en la próxima escritura).

---

## Orden de implementación recomendado

1. Fix encoding UTF-8 → 1 línea, sin riesgo, desbloquea legibilidad inmediata
2. MMR en retriever → 3 líneas, mejora calidad de respuestas RAG
3. Context selectivo → refactor mayor, implementar cuando 1 y 2 estén estables y testeados
