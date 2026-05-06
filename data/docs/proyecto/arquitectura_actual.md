# Arquitectura actual

## Propósito

Este archivo describe cómo está armado hoy el asistente local, qué rol cumple cada componente y cómo se relacionan RAG, memoria estructurada y tools dentro del flujo del sistema.

## Componentes principales

- **Ollama**: ejecuta localmente el modelo de lenguaje.
- **llama3.2**: modelo principal para generar respuestas.
- **nomic-embed-text**: genera embeddings para indexación y recuperación semántica.
- **Chroma**: guarda la base vectorial persistida del proyecto.
- **LangChain**: orquesta chat, recuperación, memoria y flujo general.
- **JSON persistente en `storage/`**: almacena memoria estructurada y estado del proyecto.

## Archivos principales del sistema

| Archivo | Rol |
|---------|-----|
| `indexacion.py` | Entrada para cargar documentos, dividirlos en chunks y construir Chroma |
| `chat.py` | Punto de entrada principal del asistente |
| `app/chat_core.py` | Lógica principal del chat y coordinación del flujo |
| `app/chat_ui.py` | Interfaz de consola y presentación |
| `app/indexing_core.py` | Lógica reutilizable de indexación |
| `app/router.py` | Router híbrido: keywords primero, LLM fallback para frases ambiguas |
| `app/tools.py` | Tools de lectura/escritura segura y utilidades asociadas |
| `app/memory_store.py` | Lectura y escritura segura de memoria estructurada |
| `app/session_state.py` | Vista resumida del estado actual del proyecto |
| `app/prompts.py` | Instrucciones y plantillas que guían el comportamiento |
| `storage/chroma/` | Base vectorial persistida para RAG |
| `storage/memory.json` | Memoria conversacional reciente |
| `storage/profile.json` | Perfil y preferencias del usuario |
| `storage/project_facts.json` | Hechos estables del proyecto |
| `storage/tasks.json` | Tareas y pendientes |
| `storage/work_state.json` | Estado actual de trabajo |

## Base documental actual

Documentos fuente en Markdown que el agente consulta como conocimiento del proyecto:

- `estado_proyecto.md`: fases, objetivos, estado actual y próximos pasos.
- `arquitectura_actual.md`: componentes técnicos y flujo del sistema.
- `memoria_agentes_resumen.md`: conceptos de memoria aplicados al proyecto.

## Flujo actual del sistema (Fase 3A)

```text
Usuario
  ↓
chat.py
  ↓
app/chat_ui.py
  ↓
app/chat_core.py
  ↓
app/router.py  ← Router HÍBRIDO en dos capas
  │
  ├─ Capa 1: keywords (0ms, sin LLM)
  │    └─ Si encuentra keyword conocida → carril directo
  │
  └─ Capa 2: LLM fallback (solo si capa 1 no encontró nada)
       └─ llama3.2 clasifica la intención → carril
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

## Router híbrido — carriles disponibles

| Carril | Qué hace | Cómo se activa |
|--------|----------|----------------|
| `tool_list_files` | Lista archivos del proyecto | Keywords: "listar archivos", "qué archivos hay" |
| `tool_read_file` | Lee contenido de un archivo | Ruta detectada en la pregunta |
| `tool_save_fact` | Guarda un hecho en `project_facts.json` | Keywords: "guarda como hecho", "anota que" |
| `tool_create_task` | Crea una tarea en `tasks.json` | Keywords: "crea una tarea", "nueva tarea" |
| `tool_complete_task` | Marca una tarea como completada | Keywords: "marca como completada", patrón `T-\d+` |
| `tool_update_work_state` | Actualiza `work_state.json` | Keywords: "actualiza el foco", "ahora estoy en" |
| `memory` | Consulta perfil, tareas, hechos o estado | Keywords: "pendientes", "foco actual", "mi perfil" |
| `rag` | Recuperación semántica en Chroma | Preguntas documentales o LLM fallback |

## Logging del router

```text
[router:kw]  'pregunta...' → tool_create_task   ← resuelta por keywords (0ms)
[router:llm] 'pregunta...' → memory             ← resuelta por LLM fallback (~3-8s)
```

## Diferencia entre arquitectura y base documental

| Arquitectura | Base documental |
|--------------|-----------------|
| Componentes, scripts, módulos, almacenamiento y flujo técnico | Textos que el agente consulta como conocimiento del proyecto |
| `app/memory_store.py`, `app/router.py`, `storage/tasks.json` | `estado_proyecto.md`, `arquitectura_actual.md`, `memoria_agentes_resumen.md` |
| Explica cómo funciona internamente el sistema | Explica qué sabe el agente sobre el proyecto |

## Estado técnico — Fase 3A (06/05/2026)

**Implementado**:

- Modularización completa del proyecto en `app/`.
- RAG funcional con Chroma y filtro por `doc_type`.
- Memoria estructurada en 4 capas: perfil, estado de trabajo, hechos, tareas.
- Router híbrido en dos capas: keywords + LLM fallback.
- 8 carriles de ejecución: 6 tools + memory + rag.
- Tools de escritura: `tool_create_task`, `tool_complete_task`, `tool_update_work_state`, `tool_save_fact`.
- Tools de lectura: `tool_list_files`, `tool_read_file`.
- Logging diferenciado `[router:kw]` / `[router:llm]`.

**Pendiente (Fase 3B)**:

- Reemplazar LLM fallback del router por clasificador de embeddings (~50ms vs ~3-8s).
- Construir índice de intenciones en Chroma con ejemplos por carril.
- Actualizar `ConversationBufferWindowMemory` deprecada por alternativa soportada.
- Métricas de evaluación mínimas: 3 casos de prueba semanales.
- Extracción de múltiples tareas desde texto largo en una sola instrucción.

## Límites actuales de diseño

En esta etapa todavía **no** conviene agregar:

- multiagente complejo,
- planner sofisticado,
- tools de alto riesgo como shell arbitraria,
- automatizaciones pesadas,
- ni memoria indiscriminada basada en reenviar siempre todo el historial.

La prioridad sigue siendo mantener una arquitectura local, pequeña, segura y fácil de mantener.
