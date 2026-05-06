# Estado del proyecto

## Objetivo general

Construir un asistente local con Ollama, LangChain y Chroma para responder preguntas usando recuperación de contexto desde documentos del proyecto, evolucionando hacia un agente útil con memoria estructurada, tools básicas y recuperación selectiva.

## Fase actual: Fase 4 — Reflexión post-acción y estabilización

**Fecha de actualización**: 06/05/2026

**Objetivo de Fase 4**:

- Consolidar todo lo construido en Fases 1-3B antes de agregar nuevas capas.
- Limpiar deuda técnica menor (tareas fantasma, documentación desactualizada).
- Evaluar el comportamiento real del router con frases de la sesión.
- Preparar el terreno para Fase 5: memoria de sesión inyectada automáticamente.

## Qué ya está firme (06/05/2026)

- **Fase 1 completada**: indexación funcional, RAG básico estable y modularización inicial.
- **Fase 2 completada**: memoria por capas, tools básicas, router simple, escritura segura.
- **Fase 3A completada**: router híbrido con 8 carriles y LLM fallback.
- **Fase 3B completada**: clasificador de embeddings con `nomic-embed-text` + `intent_index` en Chroma. LLM fallback reducido a 0% en sesiones normales.
- **Migración de memoria corta**: `ConversationBufferWindowMemory` reemplazada — warning de deprecación eliminado.
- **Correcciones de clasificación**: router ya distingue correctamente `memory` vs `rag` para frases de sugerencia de tareas.

### Memoria estructurada — 4 capas operativas

| Archivo | Contenido | Se actualiza con |
|---------|-----------|------------------|
| `storage/profile.json` | Preferencias y estilo de trabajo | Manualmente o tool futura |
| `storage/work_state.json` | Foco actual, última sesión, next step | `tool_update_work_state` |
| `storage/project_facts.json` | Hechos estables del proyecto | `tool_save_fact` |
| `storage/tasks.json` | Tareas pendientes y completadas | `tool_create_task`, `tool_complete_task` |

### Tools operativas — 8 carriles

| Carril | Estado |
|--------|--------|
| `tool_list_files` | ✅ Operativo |
| `tool_read_file` | ✅ Operativo |
| `tool_save_fact` | ✅ Operativo |
| `tool_create_task` | ✅ Operativo |
| `tool_complete_task` | ✅ Operativo |
| `tool_update_work_state` | ✅ Operativo |
| `memory` | ✅ Operativo |
| `rag` | ✅ Operativo |

### Router híbrido (Fase 3B — completo)

- **Capa 1 — keywords**: clasifica la mayoría de frases cotidianas en 0ms.
- **Capa 2 — embeddings**: `nomic-embed-text` + `intent_index` en Chroma (~50ms). 96 ejemplos indexados.
- **Capa 3 — LLM fallback**: solo para frases muy nuevas o ambiguas. Timeout 30s.
- **Logging**: `[router:kw]` / `[router:emb]` / `[router:llm]` para observar qué capa resuelve cada frase.
- **Estadísticas en vivo**: `!estado` muestra conteo por capa en la sesión actual.

## Problemas resueltos en Fase 2, 3A, 3B y 4

- Modularización de archivos grandes: ✅ resuelto.
- Falta de memoria persistente: ✅ resuelto (4 capas JSON).
- Router solo por reglas simples: ✅ reemplazado por router híbrido 3 capas.
- Tasks solo crecían, nunca se cerraban: ✅ resuelto con `tool_complete_task`.
- Work state solo editable a mano: ✅ resuelto con `tool_update_work_state`.
- Timeout de Ollama en cold start: ✅ corregido a 30s.
- LLM fallback lento (3-8s): ✅ reemplazado por embeddings (~50ms) en Fase 3B.
- `ConversationBufferWindowMemory` deprecada: ✅ migrada en Fase 4.
- Archivos `.bak` visibles en listado: ✅ filtrados en Fase 4.
- Frases de sugerencia de tareas mal clasificadas: ✅ corregido en router y ejemplos.

## Problemas pendientes

- Sin evaluación mínima sistematizada (3 casos de prueba por semana).
- Sin extracción de múltiples tareas desde texto largo en una instrucción.
- Recuperación selectiva entre capas RAG + memoria aún básica.
- Lautaro no inyecta automáticamente el contexto de sesión al arrancar (requiere `!estado` manual).
- Tareas creadas accidentalmente por frases que no eran instrucciones reales.

## Próximos pasos — Fase 5

1. Inyección automática de contexto al arrancar: leer `work_state` + tareas pendientes e incluirlos en el prompt sin que el usuario pida `!estado`.
2. Evaluación mínima semanal: 3 casos de prueba fijos por sesión.
3. Extracción de múltiples tareas desde texto largo en una sola instrucción.
4. Memoria episódica básica: guardar resúmenes de sesión en `storage/episodes/`.

## Criterio de respuesta

- **RAG**: usar cuando la pregunta sea documental, conceptual o pida sugerencias basadas en los archivos fuente.
- **Memoria**: usar para preferencias, hechos persistentes, tareas EXISTENTES, estado actual.
- **Tools**: usar para acciones concretas sobre archivos o memoria estructurada.
- Si una consulta incluye una ruta explícita, priorizar `tool_read_file`.
- Si no hay evidencia suficiente en ninguna capa, abstenerse claramente.
- No completar respuestas con teoría general si el proyecto no lo respalda.

## Relación entre RAG, memoria y tools

- **RAG**: conocimiento estable del proyecto recuperado desde documentos Markdown.
- **Memoria estructurada**: estado dinámico y persistente del trabajo (JSON).
- **Tools**: acciones controladas sobre archivos y memoria.
- **Router híbrido 3 capas**: keywords → embeddings → LLM fallback.

## Hitos completados

| Hito | Fecha |
|------|-------|
| Fase 1: RAG básico + indexación | Antes de 05/05/2026 |
| Fase 2A-2D: memoria, tools, router simple | 05/05/2026 |
| Fase 2E-2F: tool_complete_task, tool_update_work_state | 06/05/2026 |
| Fase 3A: router híbrido keywords + LLM fallback | 06/05/2026 |
| Fase 3B: clasificador embeddings + intent_index (96 vectores) | 06/05/2026 |
| Fase 4: migración memoria corta, fixes router, docs actualizados | 06/05/2026 |
