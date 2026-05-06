# Estado del proyecto

## Objetivo general

Construir un asistente local con Ollama, LangChain y Chroma para responder preguntas usando recuperación de contexto desde documentos del proyecto, evolucionando hacia un agente útil con memoria estructurada, tools básicas y recuperación selectiva.

## Fase actual: Fase 3A — Router híbrido

**Fecha de actualización**: 06/05/2026

**Objetivo de Fase 3A**:

- Reemplazar el router de reglas puras por un router híbrido en dos capas.
- Capa 1: keywords (instantáneo, sin LLM).
- Capa 2: LLM fallback solo para frases ambiguas o con vocabulario nuevo.
- Preparar la base de ejemplos reales para el clasificador de embeddings (Fase 3B).

## Qué ya está firme (06/05/2026)

- **Fase 1 completada**: indexación funcional, RAG básico estable y modularización inicial.
- **Fase 2 completada**: memoria por capas, tools básicas, router simple, escritura segura.
- **Fase 3A en producción**: router híbrido con 8 carriles y LLM fallback.

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

### Router híbrido (Fase 3A)

- **Capa 1 — keywords**: clasifica la mayoría de frases cotidianas en 0ms.
- **Capa 2 — LLM fallback**: activa solo para frases ambiguas. Timeout 30s para cold start de Ollama.
- **Logging**: `[router:kw]` vs `[router:llm]` para observar qué frases necesitan el fallback.

## Problemas resueltos en Fase 2 y 3A

- Modularización de archivos grandes: ✅ resuelto.
- Falta de memoria persistente: ✅ resuelto (4 capas JSON).
- Documentación desactualizada: ✅ actualizada hoy.
- Falta de tools de escritura segura: ✅ resuelto.
- Router solo por reglas simples: ✅ reemplazado por router híbrido.
- Tasks solo crecían, nunca se cerraban: ✅ resuelto con `tool_complete_task`.
- Work state solo editable a mano: ✅ resuelto con `tool_update_work_state`.
- Timeout de Ollama en cold start: ✅ corregido a 30s.

## Problemas pendientes

- LLM fallback del router tarda 3-8s en cold start y frases ambiguas frecuentes.
- `ConversationBufferWindowMemory` deprecada en LangChain 0.3.1 — aún en uso.
- Sin evaluación mínima sistematizada (3 casos de prueba por semana).
- Sin extracción de múltiples tareas desde texto largo en una instrucción.
- Recuperación selectiva entre capas RAG + memoria aún básica.

## Próximos pasos — Fase 3B

1. Construir índice de intenciones con Chroma: ~10 frases de ejemplo por carril.
2. Clasificar por similitud de embeddings en lugar de LLM fallback (~50ms).
3. Reemplazar `_route_by_llm()` por `_route_by_embeddings()` en `router.py`.
4. Medir precisión del clasificador de embeddings con los ejemplos reales observados.
5. Agregar evaluación mínima semanal: 3 casos de prueba fijos.

## Criterio de respuesta

- **RAG**: usar cuando la pregunta sea documental o basada en archivos del proyecto.
- **Memoria**: usar para preferencias, hechos persistentes, tareas, estado actual.
- **Tools**: usar para acciones concretas sobre archivos o memoria estructurada.
- Si una consulta incluye una ruta explícita, priorizar `tool_read_file`.
- Si no hay evidencia suficiente en ninguna capa, abstenerse claramente.
- No completar respuestas con teoría general si el proyecto no lo respalda.

## Relación entre RAG, memoria y tools

- **RAG**: conocimiento estable del proyecto recuperado desde documentos Markdown.
- **Memoria estructurada**: estado dinámico y persistente del trabajo (JSON).
- **Tools**: acciones controladas sobre archivos y memoria.
- **Router híbrido**: decide qué capa usar según la intención; keywords primero, LLM solo si es necesario.
- **Objetivo Fase 3B**: reemplazar LLM fallback por clasificador de embeddings para latencia mínima.

## Hitos completados

| Hito | Fecha |
|------|-------|
| Fase 1: RAG básico + indexación | Antes de 05/05/2026 |
| Fase 2A-2D: memoria, tools, router simple | 05/05/2026 |
| Fase 2E-2F: tool_complete_task, tool_update_work_state | 06/05/2026 |
| Fase 3A: router híbrido keywords + LLM fallback | 06/05/2026 |
