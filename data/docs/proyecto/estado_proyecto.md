# Estado del proyecto

## Objetivo general

Construir un asistente local con Ollama, LangChain y Chroma para responder preguntas usando recuperación de contexto desde documentos del proyecto, evolucionando hacia agente útil con memoria estructurada y tools básicas.

## Fase actual: Fase 2 - Memoria estructurada y herramientas básicas

**Objetivo de fase 2**:

- Implementar memoria por capas (conversación, perfil, hechos, tareas, estado de trabajo).
- Conectar memoria al flujo del chat.
- Agregar tools básicas de lectura y escritura segura.
- Crear router simple para decidir entre RAG, memoria o tool.

## Estado actual (05/05/2026)

**Qué ya está firme**:

- **Fase 1 completada**: indexación funcional, RAG básico estable, modularización inicial (`chat.py` e `indexacion.py` ya separados en módulos).
- **Memoria estructurada base implementada**:
  - `storage/memory.json`: conversación reciente.
  - `storage/profile.json`: preferencias de trabajo.
  - `storage/project_facts.json`: hechos estables del proyecto.
  - `storage/tasks.json`: pendientes y acciones.
  - `storage/work_state.json`: estado actual de trabajo.
- **Módulos creados**: `app/memory_store.py`, `app/session_state.py`, `app/prompts.py`.
- **Base documental actualizada** para fase 2.

**Próximos pasos inmediatos**:

1. Conectar memoria estructurada al flujo de `chat_core.py`.
2. Crear 4 tools básicas (leer archivo, listar archivos, guardar hecho, crear tarea).
3. Implementar router simple (RAG vs memoria vs tool).
4. Probar casos reales de uso diario.

## Qué ya está firme

- RAG básico funcional con Chroma y documentos fuente actualizados.
- Diferencia clara entre arquitectura (componentes técnicos) y base documental (conocimiento del proyecto).
- Modularización inicial completada y versionada en GitHub.
- Memoria estructurada con acceso Python validado.

## Problemas detectados (ya resueltos o en proceso)

- Modularización de archivos grandes: resuelto.
- Falta de memoria persistente más allá de historial conversacional: memoria estructurada implementada.
- Documentación desactualizada: documentos base actualizados.

## Problemas pendientes

- RAG todavía puede mejorar grounding en preguntas cruzadas.
- No hay integración real entre RAG y memoria estructurada.
- Falta router para decidir qué usar según la consulta.

## Criterio para avanzar de fase 2

Se puede avanzar a fase 3 (agente con planificación y proactividad) cuando:

- El agente use simultáneamente RAG y memoria estructurada.
- Las 4 tools básicas funcionen de forma segura y útil.
- El router simple decida correctamente entre RAG, memoria o tool.
- El agente mantenga estado de trabajo entre sesiones.

## Criterio de respuesta

- **RAG**: usar solo cuando la pregunta sea documental (“qué dice X”, “según los documentos”).
- **Memoria**: usar para hechos persistentes, tareas, preferencias, estado actual.
- **Tools**: usar para acciones concretas (“guarda esto”, “agrega tarea”).
- Si no hay evidencia suficiente en ninguna capa, abstenerse claramente.

## Relación entre RAG, memoria y tools

- **RAG**: conocimiento estable del proyecto (arquitectura, objetivos, fases).
- **Memoria estructurada**: estado dinámico (tareas, hechos nuevos, preferencias).
- **Tools**: acciones concretas sobre el proyecto.
- **Router**: decide qué capa usar según intención de la consulta.

## Próximos commits esperados

1. "2B: memoria estructurada base implementada y probada"
2. "2C: tools básicas y conexión memoria al chat"
3. "2D: router simple funcional"
4. "2E: estado de trabajo integrado"