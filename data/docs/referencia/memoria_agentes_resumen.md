# Memoria en mi-agente (Fase 2 - 05/05/2026)

## Idea general

La memoria permite al asistente usar contexto previo y hechos persistentes de forma más útil que solo historial conversacional.

En este proyecto, la memoria no reemplaza al RAG: lo complementa con datos persistentes y estado operativo.

## Tipos de memoria implementados

| Tipo | Archivo | Contenido | Uso |
|------|---------|-----------|-----|
| **Corto plazo** | `storage/memory.json` | Conversación reciente | Contexto inmediato de sesión |
| **Perfil** | `storage/profile.json` | Preferencias de trabajo del usuario | Cómo prefiere trabajar Lautaro |
| **Hechos del proyecto** | `storage/project_facts.json` | Hechos estables del proyecto | Fase actual, prioridades y decisiones ya tomadas |
| **Estado de trabajo** | `storage/work_state.json` | Estado actual del trabajo | En qué iba, qué sigue, bloqueos |
| **Tareas** | `storage/tasks.json` | Pendientes y acciones | Qué hacer, qué está hecho |

## Módulos de memoria

- **`app/memory_store.py`**: lectura y escritura segura de JSON.
- **`app/session_state.py`**: vista resumida del estado actual.
- **`app/prompts.py`**: instrucciones que guían el uso de memoria.
- **`app/router.py`**: decide cuándo usar memoria, RAG o tools.
- **`app/tools.py`**: lectura segura de archivos del proyecto.

## Diferencia práctica: RAG vs memoria

| RAG (Chroma) | Memoria estructurada |
|--------------|---------------------|
| Conocimiento estable del proyecto (`estado_proyecto.md`, `arquitectura_actual.md`) | Estado dinámico del trabajo (`tasks.json`, `work_state.json`) |
| “Qué dice el proyecto” | “En qué estamos hoy” |
| Recuperación semántica | Acceso directo por clave o por estructura |
| Preguntas documentales | Consultas de estado, perfil o tareas |

## Estado actual de memoria (Fase 2)

**Implementado**:

- Memoria estructurada base en JSON.
- `memory_store.py` funcional para leer, escribir y actualizar.
- Perfil inicial cargado.
- Hechos del proyecto cargados.
- Estado de trabajo inicial cargado.
- Router simple para decidir entre RAG, memoria y tools.
- Tools básicas de lectura segura ya operativas.

**Pendiente**:

- Conectar mejor la memoria al flujo de respuesta del chat.
- Implementar tools de escritura segura para memoria.
- Hacer que `work_state.json` se actualice mejor con el avance real.
- Refinar la selección entre memoria, RAG y tools.
- Reducir dependencia del historial conversacional como fuente principal.

## Qué sería memoria híbrida aquí

En este proyecto, memoria híbrida significa combinar:

- memoria de conversación reciente,
- hechos persistentes del usuario o del proyecto,
- estado operativo del trabajo,
- y recuperación selectiva, en vez de reenviar siempre todo el historial.

## Ejemplos de uso

**Pregunta:** “¿En qué fase estamos?”  
→ Router: memoria de hechos del proyecto → `project_facts.json`

**Pregunta:** “¿Qué sigue ahora?”  
→ Router: estado de trabajo → `work_state.json`

**Pregunta:** “¿Cuál es mi estilo preferido de respuesta?”  
→ Router: perfil → `profile.json`

**Pregunta:** “¿Qué dice `arquitectura_actual.md`?”  
→ Router: RAG → Chroma → documentos fuente

**Pregunta:** “Guarda esto como hecho del proyecto”  
→ Router: tools / escritura segura → `memory_store.py`

## Respuesta correcta vs respuesta grounded

| Correcta | Grounded |
|----------|----------|
| Coincide con la realidad del proyecto | Además está apoyada explícitamente en evidencia |
| “Estamos en fase 2” | “`project_facts.json` indica fase_2” |

## Comportamiento ideal por capa

**RAG**:

- Responder solo con evidencia documental clara.
- Abstenerse si falta contexto.

**Memoria**:

- Usar datos estructurados para hechos, estado y tareas.
- Actualizar vía tools cuando corresponda.

**Tools**:

- Ejecutar acciones concretas sobre archivos o memoria.
- Mantener seguridad y rutas permitidas.

**Router**:

- `"guarda esto"` → tool → `memory_store.update()`
- `"qué sigue"` → memoria → `work_state.json`
- `"qué dice X"` → RAG → Chroma

## Próximos commits de memoria

1. `2B: memoria estructurada base implementada y probada`
2. `2C: tools para memoria (guardar hecho, agregar tarea)`
3. `2D: router RAG/memoria/tool`
4. `2E: estado de trabajo integrado`