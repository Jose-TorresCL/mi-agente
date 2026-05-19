# ADR-005 — Modos de agente, tool calls y decisiones de código

> Estado: **IMPLEMENTADO** — 19/05/2026  
> Contexto: Fase 6–8 completadas. Experience Index operativo.

## Contexto

Durante el desarrollo de las Fases 6, 7 y 8 surgieron decisiones
arquitecturales sobre tres temas interrelacionados:
1. Cómo separar los modos de operación del agente (RAG vs memoria vs tools)
2. Cómo estructurar el ciclo de vida de los tool calls para que sean seguros
3. Cómo codificar decisiones de diseño que afectan el comportamiento a largo plazo

## Decisiones tomadas

### 1. Carril `memory` como TERMINAL (Fix 6A)

**Decisión**: el carril `memory` en `intelligence.py` es la última parada —
no cae al carril RAG ni consulta el caché semántico.

**Motivación**: el caché semántico puede servir respuestas de hace días
para preguntas de estado actual. El estado del proyecto cambia con cada sesión.

**Implementación**:
```python
# intelligence.py — process_turn()
if route == "memory":
    answer = _decide_memory(user_input)
    return answer, []  # TERMINAL — nunca llega a _decide_rag()
```

**Consecuencia**: si `_decide_memory()` no reconoce el tipo de consulta,
devuelve `_MEMORY_NOT_FOUND_MSG` explícito en vez de caer silenciosamente a RAG.

---

### 2. Recuperación selectiva de contexto por tipo (Fix 6B)

**Decisión**: `memory_manager.get_context_for(intent_type)` elige qué capa
de memoria inyectar según la intención clasificada por el router.

**Motivación**: inyectar contexto completo siempre aumenta tokens y puede
confundir al LLM con información irrelevante para la pregunta actual.

**Mapa de intenciones → capas**:

| Intención | Capa de memoria |
|---|---|
| `work_state`, `tasks`, `focus` | `WORKING` |
| `project_info`, `architecture`, `rag` | `SEMANTIC` |
| `episode`, `last_session` | `EPISODIC` |
| `identity`, `greeting` | mínimo (solo profile) |

---

### 3. Experience Index — experiencias como documentos (Fase 8)

**Decisión**: los episodios de sesión se indexan en un Chroma separado
(`storage/experience_index/`) con el mismo modelo de embeddings.

**Motivación**: permite recuperar experiencias relevantes por similitud
semántica sin fine-tuning ni memoria explícita — solo RAG sobre episodios.

**Flujo implementado**:
```
Fin de sesión → save_episode() + pregunta s/n exitosa
                         ↓
             indexacion.py --only-episodes (o indexacion.py completo)
                         ↓
          experience_index en Chroma
                         ↓
Nueva pregunta en carril RAG → experience_lookup(score >= 0.80)
                         ↓
   Episodio relevante prepend al context_text del prompt
```

**Boost de calidad**: episodios con `exitoso=True` reciben `score + 0.15`
en `search_episodes()`. Episodios fallidos se filtran si hay alternativos
con score >= 0.65.

---

### 4. MemoryType enum formal (Fase 8D)

**Decisión**: `schemas.py` define `MemoryType(str, Enum)` con 4 valores:
`WORKING`, `SEMANTIC`, `EPISODIC`, `PROCEDURAL`.

**Motivación**: hacer explícito el tipo de memoria de cada función pública
de `memory_manager.py` evita mezclas accidentales y documenta la arquitectura
directamente en el código.

**Criterio de verificación**:
```powershell
grep MemoryType app/memory_manager.py  # debe devolver 15+ líneas
```

---

### 5. Métricas por turno (Fase 7A)

**Decisión**: `metrics.py` registra en `storage/metrics.jsonl` cada turno
con: ruta, tiempo de retrieval, tiempo LLM, estimación de tokens y flag cached.

**Motivación**: sin métricas no se puede decidir si un cambio vale la pena.
El formato JSONL permite análisis con pandas o scripts simples.

**Garantía**: `record_turn()` nunca lanza excepciones — errores van a WARNING.

---

## Consecuencias conocidas

- Los carriles `memory` y `episode` nunca llenan el caché semántico.
- El caché semántico solo sirve respuestas del carril `rag`.
- La inyección de experiencias previas (`experience_injected=True`) desactiva
  el caché para esa respuesta específica — evita respuestas obsoletas.
- `test_architecture.py` actúa como guardia permanente de las fronteras entre capas.

## Alternativas descartadas

| Alternativa | Razón del descarte |
|---|---|
| Caché global antes de separar carriles | Envenena respuestas de estado dinámico |
| Contexto completo siempre | Más tokens, más ruido, sin beneficio claro |
| Fine-tuning para experiencias | Inviable en hardware local sin GPU |
| SQLite desde el principio | Overhead prematuro — JSON es suficiente hasta ~500 episodios |
