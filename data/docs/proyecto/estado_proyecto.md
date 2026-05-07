# Estado del proyecto

## Objetivo general

Construir un asistente local con Ollama, LangChain y Chroma para responder preguntas usando recuperación de contexto desde documentos del proyecto, evolucionando hacia un agente útil con memoria estructurada, tools básicas y recuperación selectiva.

## Fase actual: Fase 4 — Reflexión post-acción y estabilización

**Fecha de actualización**: 07/05/2026

**Objetivo de Fase 4**:

- Consolidar todo lo construido en Fases 1–3B antes de agregar nuevas capas.
- Limpiar deuda técnica menor (tareas fantasma, documentación desactualizada).
- Evaluar el comportamiento real del router con frases de la sesión.
- Preparar el terreno para Fase 5: inyección automática de contexto al arrancar.

## Qué ya está firme (07/05/2026)

- **Fase 1 completada**: indexación funcional, RAG básico estable, modularización inicial.
- **Fase 2 completada**: memoria por capas, tools básicas, router simple, escritura segura.
- **Fase 3A completada**: router híbrido con 8 carriles y LLM fallback.
- **Fase 3B completada**: clasificador de embeddings con `nomic-embed-text` + `intent_index` en Chroma. LLM fallback reducido a ~0% en sesiones normales.
- **Fase 4 en curso**: cache semántica RAG, verificación de fidelidad, memoria episódica, fixes de alucinación y documentación.

### Componentes nuevos — Fase 4

| Módulo | Descripción |
|--------|-------------|
| `app/semantic_cache.py` | Caché semántica para RAG. Umbral coseno 0.88. MAX 200 entradas FIFO. Hit ~50ms. |
| `app/fidelity_check.py` | Verifica que la respuesta RAG tenga soporte real en los chunks. Si similitud < 0.55 → mensaje de evidencia insuficiente. |
| `memory_store.py` (episódica) | `save_episode()` guarda resumen de sesión al salir. `load_last_episode()` inyecta contexto al arrancar. |
| Fix `tool_save_fact` | Formato `key=value` actualiza clave existente en lugar de crear `hecho_timestamp`. |
| Fix prompts anti-alucinación | Regla explícita: no inventar IDs de tareas. No citar contenido de memoria estructurada como parte visible de la respuesta. |
| Fix router Capa 1 | `tareas` y `mis tareas` como keywords directas en `MEMORY_TASKS_KEYWORDS`. `!estatus` como alias de `!estado`. |
| Fix palabras de salida | Ampliado `_EXIT_WORDS`: `hasta luego`, `hasta pronto`, `chau`, `nos vemos`, `me voy`, `bye bye`. |
| Suite de tests restaurada | `tests/` con verificación funcional de carriles y comportamiento esperado. |

### Memoria estructurada — 4 capas operativas

| Archivo | Contenido | Se actualiza con |
|---------|-----------|------------------|
| `storage/profile.json` | Preferencias y estilo de trabajo | Manualmente o tool futura |
| `storage/work_state.json` | Foco actual, última sesión, next step | `tool_update_work_state` |
| `storage/project_facts.json` | Hechos estables del proyecto | `tool_save_fact` |
| `storage/tasks.json` | Tareas pendientes y completadas | `tool_create_task`, `tool_complete_task` |
| `storage/episodic_memory.json` | Resúmenes de sesión con fecha y turno count | `save_episode()` al salir |

### Tools operativas — 8 carriles

| Carril | Estado |
|--------|--------|
| `tool_list_files` | ✅ Operativo |
| `tool_read_file` | ✅ Operativo |
| `tool_save_fact` | ✅ Operativo (formato key=value) |
| `tool_create_task` | ✅ Operativo |
| `tool_complete_task` | ✅ Operativo |
| `tool_update_work_state` | ✅ Operativo |
| `memory` | ✅ Operativo |
| `rag` | ✅ Operativo + caché semántica + fidelity check |

### Router híbrido (Fase 3B — completo)

- **Capa 1 — keywords**: clasifica la mayoría de frases cotidianas en 0ms.
- **Capa 2 — embeddings**: `nomic-embed-text` + `intent_index` en Chroma (~50ms). 96 ejemplos indexados.
- **Capa 3 — LLM fallback**: solo para frases muy nuevas o ambiguas. Timeout 30s.
- **Logging**: `[router:kw]` / `[router:emb]` / `[router:llm]` por consulta.
- **Estadísticas en vivo**: `!estado` muestra conteo por capa en la sesión actual.

## Problemas resueltos acumulados

| Problema | Estado |
|----------|--------|
| Modularización de archivos grandes | ✅ |
| Falta de memoria persistente | ✅ (4 capas JSON) |
| Router solo por reglas simples | ✅ (router híbrido 3 capas) |
| Tasks solo crecían, nunca se cerraban | ✅ (`tool_complete_task`) |
| Work state solo editable a mano | ✅ (`tool_update_work_state`) |
| Timeout de Ollama en cold start | ✅ (30s) |
| LLM fallback lento (3–8s) | ✅ (embeddings ~50ms en Fase 3B) |
| `ConversationBufferWindowMemory` deprecada | ✅ migrada en Fase 4 |
| Archivos `.bak` visibles en listado | ✅ filtrados |
| Frases de sugerencia de tareas mal clasificadas | ✅ corregido en router y ejemplos |
| LLM inventaba IDs de tareas ficticias | ✅ regla anti-alucinación en prompts |
| Memoria estructurada citada en respuesta visible | ✅ regla explícita en QA_SYSTEM_PROMPT |
| `tool_save_fact` creaba claves duplicadas | ✅ formato key=value actualiza clave existente |
| RAG respondía sin soporte documental real | ✅ fidelity_check con umbral 0.55 |
| Respuestas RAG repetidas con costo LLM | ✅ caché semántica umbral 0.88 |
| Contexto de sesión anterior perdido al arrancar | ✅ memoria episódica inyectada al inicio |
| Palabras de salida con typos no reconocidas | ✅ `_EXIT_WORDS` ampliado |

## Problemas pendientes

- Sin evaluación mínima sistematizada (batería de 9 preguntas fija por sesión).
- Sin extracción de múltiples tareas desde texto largo en una instrucción.
- Recuperación selectiva entre capas RAG + memoria aún básica.
- Tareas creadas accidentalmente por frases que no eran instrucciones reales ("ya hice X").
- Memory devuelve capa genérica — subrutas finas (`memory_profile`, `memory_workstate`, etc.) aún no gobiernan el flujo del handler en `chat_core.py`.

## Próximos pasos — Fase 5

1. **Inyección automática de contexto al arrancar**: leer `work_state` + tareas pendientes + último episodio e incluirlos en el prompt sin que el usuario pida `!estado`.
2. **Batería de validación fija**: 9 preguntas estándar del informe de diagnóstico, ejecutables con un script.
3. **Subrutas de memory en el handler**: conectar `classify_memory_query()` del router al flujo real de `chat_core.py`.
4. **Corrección de "ya hice X"**: detectar confirmaciones humanas y actualizar estado en vez de crear tareas.
5. **Extracción de múltiples tareas** desde texto largo en una sola instrucción.

## Criterio de respuesta

- **RAG**: preguntas documentales, conceptuales o que pidan sugerencias basadas en los archivos fuente.
- **Memoria**: preferencias, hechos persistentes, tareas EXISTENTES, estado actual.
- **Tools**: acciones concretas sobre archivos o memoria estructurada.
- Si una consulta incluye una ruta explícita → priorizar `tool_read_file`.
- Si no hay evidencia suficiente en ninguna capa → abstenerse claramente.
- No completar respuestas con teoría general si el proyecto no lo respalda.

## Relación entre capas

- **RAG**: conocimiento estable del proyecto recuperado desde documentos Markdown.
- **Memoria estructurada**: estado dinámico y persistente del trabajo (JSON).
- **Memoria episódica**: resúmenes de sesión entre arranques.
- **Caché semántica**: evita re-invocar LLM para preguntas RAG similares.
- **Fidelity check**: evita respuestas sin soporte documental real.
- **Tools**: acciones controladas sobre archivos y memoria.
- **Router híbrido 3 capas**: keywords → embeddings → LLM fallback.

## Hitos completados

| Hito | Fecha |
|------|-------|
| Fase 1: RAG básico + indexación | Antes del 05/05/2026 |
| Fase 2A–2D: memoria, tools, router simple | 05/05/2026 |
| Fase 2E–2F: tool_complete_task, tool_update_work_state | 06/05/2026 |
| Fase 3A: router híbrido keywords + LLM fallback | 06/05/2026 |
| Fase 3B: clasificador embeddings + intent_index (96 vectores) | 06/05/2026 |
| Fase 4A: migración memoria corta, fixes router | 06/05/2026 |
| Fase 4B: caché semántica RAG (semantic_cache.py) | 06/05/2026 |
| Fase 4C: fidelity_check.py + umbral 0.55 | 06/05/2026 |
| Fase 4D: memoria episódica (save/load episode) | 06/05/2026 |
| Fase 4E: fixes anti-alucinación prompts + router | 06/05/2026 |
| Fase 4F: fix tool_save_fact key=value | 06/05/2026 |
| Fase 4G: ampliación _EXIT_WORDS + suite tests | 07/05/2026 |
