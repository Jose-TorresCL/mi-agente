# Estado del proyecto

## Objetivo general

Construir un asistente local con Ollama, LangChain y Chroma para responder preguntas usando recuperación de contexto desde documentos del proyecto, evolucionando hacia un agente útil con memoria estructurada, tools básicas y recuperación selectiva.

## Fase actual: Fase 2 - Memoria estructurada y herramientas básicas

**Objetivo de fase 2**:

- Implementar memoria por capas: conversación, perfil, hechos, tareas y estado de trabajo.
- Conectar memoria estructurada al flujo del chat.
- Agregar tools básicas de lectura y escritura segura.
- Incorporar un router simple para decidir entre RAG, memoria o tools.
- Preparar la base para recuperación selectiva en vez de depender solo del historial completo.

## Estado actual (05/05/2026)

**Qué ya está firme**:

- **Fase 1 completada**: indexación funcional, RAG básico estable y modularización inicial del proyecto.
- **RAG básico operativo** con Chroma sobre documentos Markdown del proyecto.
- **Memoria estructurada base implementada**:
  - `storage/memory.json`: conversación reciente.
  - `storage/profile.json`: preferencias de trabajo.
  - `storage/project_facts.json`: hechos estables del proyecto.
  - `storage/tasks.json`: pendientes y acciones.
  - `storage/work_state.json`: estado actual de trabajo.
- **Módulos creados**:
  - `app/memory_store.py`
  - `app/session_state.py`
  - `app/prompts.py`
  - `app/router.py`
  - `app/tools.py`
- **Tools básicas de lectura ya operativas**:
  - listar archivos permitidos,
  - leer archivos permitidos,
  - extraer rutas desde lenguaje natural,
  - bloquear rutas externas al proyecto.
- **Router simple ya implementado** para distinguir entre:
  - lectura de archivos,
  - listado de archivos,
  - memoria,
  - RAG.
- **Base documental actualizada** para reflejar la fase 2.

## Qué ya está firme

- RAG básico funcional con Chroma y documentos fuente actualizados.
- Diferencia clara entre arquitectura técnica, memoria estructurada y base documental.
- Modularización inicial completada y usable.
- Memoria estructurada con lectura segura validada.
- Tools de lectura funcionando con restricciones de rutas.
- El sistema ya puede leer archivos de `app/`, `data/docs/` y `storage/`.
- El sistema ya bloquea rutas externas como `C:\Windows\...`.
- El listado de archivos ya excluye carpetas técnicas no útiles para el usuario.
- El router ya resuelve casos básicos de uso diario sin depender solo del retriever.

## Problemas detectados (ya resueltos o en proceso)

- Modularización de archivos grandes: resuelto.
- Falta de memoria persistente más allá del historial conversacional: resuelto en base.
- Documentación desactualizada: resuelto en esta fase.
- Falta de tools de lectura segura: resuelto en versión base.
- Exposición innecesaria de archivos internos de Chroma en el listado: resuelto.
- Router demasiado básico en su primera versión: mejorado.

## Problemas pendientes

- Todavía no hay integración fuerte entre RAG y memoria estructurada dentro del flujo de respuesta.
- Las tools de escritura segura todavía no están implementadas o conectadas por completo.
- El estado de trabajo aún no se actualiza automáticamente a partir de la conversación.
- El router sigue siendo por reglas simples y puede refinarse más.
- La recuperación selectiva todavía es básica y no usa una política clara por capa.
- La memoria conversacional sigue apoyándose en `ConversationBufferWindowMemory`, que ya aparece como deprecada en LangChain.
- Falta probar más casos reales de uso diario para validar estabilidad.

## Próximos pasos inmediatos

1. Dejar firme `router.py` como versión final de 2D.
2. Integrar mejor memoria estructurada en `chat_core.py`.
3. Implementar las tools de escritura segura:
   - guardar hecho,
   - crear tarea.
4. Conectar `work_state.json` al flujo real del asistente.
5. Probar casos reales combinando:
   - lectura documental,
   - memoria,
   - tools.
6. Actualizar la documentación del proyecto para que refleje el estado real del sistema.

## Criterio para avanzar dentro de fase 2

Se considera que la fase 2 está madura cuando:

- el agente distingue correctamente entre consultas documentales, consultas de memoria y acciones concretas;
- las tools básicas de lectura y escritura funcionan de forma segura;
- el router toma decisiones razonables en casos comunes de uso;
- el estado de trabajo persiste entre sesiones;
- y la memoria no reemplaza al RAG, sino que lo complementa con recuperación selectiva.

## Criterio para avanzar a fase 3

Se puede avanzar a fase 3 (agente con planificación y proactividad) cuando:

- el agente use simultáneamente RAG y memoria estructurada con criterio;
- el estado de trabajo se mantenga actualizado entre sesiones;
- las tools básicas sean estables y útiles en el trabajo diario;
- el router ya no falle en casos frecuentes;
- y exista una base mínima de recuperación selectiva por capas.

## Criterio de respuesta

- **RAG**: usar cuando la pregunta sea documental o esté basada en lo que dicen los archivos del proyecto.
- **Memoria**: usar para preferencias, hechos persistentes, tareas, estado actual y datos operativos del trabajo.
- **Tools**: usar para acciones concretas sobre archivos o memoria estructurada.
- Si una consulta incluye una ruta explícita, priorizar la tool de lectura de archivo.
- Si no hay evidencia suficiente en ninguna capa, abstenerse claramente.
- No completar respuestas con teoría general si el proyecto no lo respalda.

## Relación entre RAG, memoria y tools

- **RAG**: conocimiento estable del proyecto recuperado desde documentos.
- **Memoria estructurada**: estado dinámico y persistente del trabajo.
- **Tools**: acciones controladas sobre archivos y memoria.
- **Router**: decide qué capa usar según la intención de la consulta.
- **Objetivo futuro**: pasar de historial completo a recuperación selectiva por capas.

## Próximos commits esperados

1. `2B: memoria estructurada base implementada y probada`
2. `2C: tools básicas y conexión memoria al chat`
3. `2D: router simple funcional`
4. `2E: estado de trabajo integrado`
5. `2F: tools de escritura segura conectadas`