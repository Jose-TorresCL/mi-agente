# Arquitectura actual

## Propósito

Este archivo describe cómo está armado hoy el asistente local, qué rol cumple cada componente y cómo se relacionan RAG, memoria estructurada y tools dentro del flujo del sistema.

## Componentes principales

- **Ollama**: ejecuta localmente el modelo de lenguaje.
- **llama3.2**: modelo principal para generar respuestas.
- **nomic-embed-text**: genera embeddings para indexación RAG, recuperación semántica y clasificación de intenciones.
- **Chroma**: guarda la base vectorial del proyecto (RAG) y el índice de intenciones del router (Fase 3B).
- **LangChain**: orquesta chat, recuperación y flujo general. Memoria corta migrada a lista nativa de mensajes.
- **JSON persistente en `storage/`**: almacena memoria estructurada y estado del proyecto.

## Archivos principales del sistema

| Archivo | Rol |
|---------|-----|
| `indexacion.py` | Carga documentos, los divide en chunks y construye Chroma |
| `build_intent_index.py` | Construye el índice de intenciones en `storage/intent_index` |
| `chat.py` | Punto de entrada principal del asistente |
| `app/chat_core.py` | Lógica principal del chat y coordinación del flujo |
| `app/chat_ui.py` | Interfaz de consola y presentación |
| `app/indexing_core.py` | Lógica reutilizable de indexación |
| `app/router.py` | Router híbrido 3 capas: keywords → embeddings → LLM fallback |
| `app/tools.py` | Tools de lectura/escritura segura y utilidades asociadas |
| `app/memory_store.py` | Lectura y escritura segura de memoria estructurada |
| `app/session_state.py` | Vista resumida del estado actual del proyecto |
| `app/prompts.py` | Instrucciones y plantillas que guían el comportamiento |
| `storage/chroma/` | Base vectorial persistida para RAG |
| `storage/intent_index/` | Índice de intenciones para clasificación por embeddings (96 vectores) |
| `storage/memory.json` | Historial de conversación reciente |
| `storage/profile.json` | Perfil y preferencias del usuario |
| `storage/project_facts.json` | Hechos estables del proyecto |
| `storage/tasks.json` | Tareas y pendientes |
| `storage/work_state.json` | Estado actual de trabajo |

## Base documental actual

Documentos fuente en Markdown que el agente consulta como conocimiento del proyecto:

- `estado_proyecto.md`: fases, objetivos, estado actual y próximos pasos.
- `arquitectura_actual.md`: componentes técnicos y flujo del sistema.
- `memoria_agentes_resumen.md`: conceptos de memoria aplicados al proyecto.

## Flujo actual del sistema (Fase 4)

```text
Usuario
  ↓
chat.py
  ↓
app/chat_ui.py
  ↓
app/chat_core.py
  ↓
app/router.py  ← Router HÍBRIDO en tres capas
  │
  ├─ Capa 1: keywords (0ms, sin modelo)
  │    └─ Si encuentra keyword conocida → carril directo
  │
  ├─ Capa 2: embeddings (nomic-embed-text + intent_index, ~50ms)
  │    └─ Busca frase más similar en los 96 ejemplos indexados
  │    └─ Si similitud >= 0.70 → carril directo
  │
  └─ Capa 3: LLM fallback (solo si similitud < 0.70)
       └─ llama3.2 clasifica la intención → carril (~3-8s)
  ↓
┌─────────────────┬─────────────────────┬────────────────────────────────────┐
│ RAG             │ Memoria estructurada│ Tools                              │
│ (Chroma/docs)   │ (JSON en storage/)  │ list, read, save_fact,             │
│                 │                     │ create_task, complete_task,        │
│                 │                     │ update_work_state                  │
└─────────────────┴─────────────────────┴────────────────────────────────────┘
  ↓
Ollama (llama3.2)
  ↓
Respuesta
```

## Tools operativas — Fase 4

El asistente tiene 6 tools activas que ejecutan acciones concretas sobre el proyecto.
Cada tool tiene su propio carril en el router y actúa sobre un archivo JSON de memoria.

| Tool | Estado | Acción | Archivo afectado |
|------|--------|--------|------------------|
| `tool_list_files` | ✅ operativa | Lista todos los archivos del proyecto (sin `.bak`) | solo lectura |
| `tool_read_file` | ✅ operativa | Lee el contenido de un archivo específico | solo lectura |
| `tool_save_fact` | ✅ operativa | Guarda un hecho estable del proyecto | `project_facts.json` |
| `tool_create_task` | ✅ operativa | Crea una tarea nueva | `tasks.json` |
| `tool_complete_task` | ✅ operativa | Marca una tarea como completada | `tasks.json` |
| `tool_update_work_state` | ✅ operativa | Actualiza el foco, fase o siguiente paso | `work_state.json` |

Además de las 6 tools, el router tiene dos carriles de consulta:

- **`memory`**: consulta tareas existentes, perfil, hechos y estado de trabajo.
- **`rag`**: recuperación semántica para preguntas documentales, conceptuales o de sugerencia.

## Router híbrido — carriles disponibles

| Carril | Qué hace | Cómo se activa |
|--------|----------|----------------|
| `tool_list_files` | Lista archivos del proyecto | Keywords: "listar archivos", "qué archivos hay" |
| `tool_read_file` | Lee contenido de un archivo | Ruta detectada en la pregunta |
| `tool_save_fact` | Guarda un hecho en `project_facts.json` | Keywords: "guarda como hecho", "anota que" |
| `tool_create_task` | Crea una tarea en `tasks.json` | Keywords: "crea una tarea", "nueva tarea" |
| `tool_complete_task` | Marca una tarea como completada | Keywords: "marca como completada", patrón `T-\d+` |
| `tool_update_work_state` | Actualiza `work_state.json` | Keywords: "actualiza el foco", "ahora estoy en" |
| `memory` | Consulta tareas existentes, perfil o estado | Keywords específicas de tareas pendientes, foco actual |
| `rag` | Recuperación semántica o sugerencias | Preguntas documentales, conceptuales o "qué podríamos hacer" |

## Logging del router

```text
[router:kw]  'pregunta...' → tool_create_task   ← resuelta por keywords (0ms)
[router:emb] similitud=0.93 lane_candidato=rag   ← resuelta por embeddings (~50ms)
[router:llm] 'pregunta...' → memory             ← resuelta por LLM fallback (~3-8s)
```

## Diferencia entre arquitectura y base documental

| Arquitectura | Base documental |
|--------------|-----------------|
| Componentes, scripts, módulos, almacenamiento y flujo técnico | Textos que el agente consulta como conocimiento del proyecto |
| `app/memory_store.py`, `app/router.py`, `storage/tasks.json` | `estado_proyecto.md`, `arquitectura_actual.md`, `memoria_agentes_resumen.md` |
| Explica cómo funciona internamente el sistema | Explica qué sabe el agente sobre el proyecto |

## Estado técnico — Fase 4 (06/05/2026)

**Implementado**:

- Modularización completa del proyecto en `app/`.
- RAG funcional con Chroma y filtro por `doc_type`.
- Memoria estructurada en 4 capas: perfil, estado de trabajo, hechos, tareas.
- Router híbrido en tres capas: keywords → embeddings → LLM fallback.
- 8 carriles de ejecución: 6 tools + memory + rag.
- Clasificador de embeddings con `nomic-embed-text`: 96 ejemplos, umbral 0.70.
- Memoria corta migrada: sin dependencia de `ConversationBufferWindowMemory`.
- Archivos `.bak` filtrados del listado de archivos.
- Distinción correcta entre tareas existentes (memory) y sugerencias de tareas (rag).
- Logging diferenciado `[router:kw]` / `[router:emb]` / `[router:llm]`.
- Estadísticas de sesión en vivo con `!estado`.

**Pendiente (Fase 5)**:

- Inyección automática de contexto al arrancar (work_state + tareas en el prompt inicial).
- Evaluación mínima semanal: 3 casos de prueba fijos.
- Extracción de múltiples tareas desde texto largo en una sola instrucción.
- Memoria episódica básica: resúmenes de sesión en `storage/episodes/`.

## Límites actuales de diseño

En esta etapa todavía **no** conviene agregar:

- multiagente complejo,
- planner sofisticado,
- tools de alto riesgo como shell arbitraria,
- automatizaciones pesadas,
- ni memoria indiscriminada basada en reenviar siempre todo el historial.

La prioridad sigue siendo mantener una arquitectura local, pequeña, segura y fácil de mantener.
