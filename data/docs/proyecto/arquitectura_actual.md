# Arquitectura actual

## Propósito

Este archivo describe cómo está armado hoy el asistente local Lautaro,
qué rol cumple cada componente y cómo se relacionan las tres capas del
sistema: Conversación → Inteligencia → Memoria.

Última actualización: 10/05/2026 — Fase 5 (refactor modular completo).

---

## Modelo y herramientas base

| Componente | Rol |
|---|---|
| **Ollama** | Ejecuta modelos de lenguaje localmente |
| **llama3.2** | Modelo base para generación de respuestas |
| **nomic-embed-text** | Embeddings para RAG, caché semántica y clasificación de intenciones |
| **Chroma** | Base vectorial para RAG (`storage/chroma/`) e índice de intenciones (`storage/intent_index/`) |
| **LangChain** | Orquestación de RAG y flujo general |
| **JSON en `storage/`** | Persistencia de memoria estructurada |

---

## Tres capas del sistema

El sistema está organizado en tres capas con dirección de dependencia
unidireccional: Conversación → Inteligencia → Memoria.

```
Conversación
  chat.py
  app/chat_ui.py
  app/chat_core.py        ← orquestador principal
        ↓
Inteligencia
  app/router.py           ← 3 capas: keywords → embeddings → LLM
  app/rag_engine.py       ← retrieval semántico con caché y fidelity check
  app/tool_registry.py    ← despacho centralizado de tools
  app/tools.py            ← 6 tools operativas
  app/tool_helpers.py     ← utilidades de extracción de argumentos
        ↓
Memoria
  app/memory_store.py     ← lectura/escritura segura de JSON
  app/memory_context.py   ← ensamblador de contexto para prompts
  app/schemas.py          ← contratos TypedDict para datos estructurados
  app/semantic_cache.py   ← caché semántica de respuestas RAG
```

**Principio clave**: la memoria no conoce al router ni a la UI.
El router no escribe JSON directamente. La conversación no decide
qué carril usar.

---

## Archivos principales

| Archivo | Capa | Rol |
|---|---|---|
| `chat.py` | Conversación | Punto de entrada |
| `app/chat_ui.py` | Conversación | Interfaz de consola y presentación |
| `app/chat_core.py` | Conversación | Orquestador: recibe input, llama inteligencia, devuelve respuesta |
| `app/config.py` | Transversal | Constantes globales y configuración centralizada |
| `app/logger.py` | Transversal | Logging estructurado por módulo |
| `app/router.py` | Inteligencia | Router híbrido 3 capas |
| `app/rag_engine.py` | Inteligencia | Motor RAG con caché y fidelity check |
| `app/tool_registry.py` | Inteligencia | Registro y despacho de tools |
| `app/tools.py` | Inteligencia | Implementación de las 6 tools operativas |
| `app/tool_helpers.py` | Inteligencia | Extracción de argumentos de herramientas |
| `app/prompts.py` | Inteligencia | Plantillas de sistema y reglas de comportamiento |
| `app/memory_store.py` | Memoria | Lectura y escritura segura de JSON |
| `app/memory_context.py` | Memoria | Ensamblador de contexto para prompts |
| `app/schemas.py` | Memoria | TypedDict: WorkState, Task, Episode, Fact |
| `app/semantic_cache.py` | Memoria | Caché semántica de respuestas RAG (umbral 0.88) |
| `app/fidelity_check.py` | Inteligencia | Verifica que la respuesta RAG tenga soporte real |
| `app/session_state.py` | Conversación | Vista resumida del estado actual (`!estado`) |
| `indexacion.py` | Herramienta | Indexa documentos en Chroma |
| `build_intent_index.py` | Herramienta | Construye el índice de intenciones (96 ejemplos) |

---

## Flujo del sistema — Fase 5

```
Usuario
  ↓
chat.py  →  chat_ui.py  →  chat_core.py
                                ↓
                           router.py
                          /     |      \
              Capa 1: kw  Capa 2: emb   Capa 3: LLM
               (0ms)       (~50ms)        (~3-8s)
                                ↓
              ┌─────────┬──────────────┬─────────────┐
              │  rag    │   memory     │   tools     │
              │Chroma   │work_state    │save_fact    │
              │+caché   │project_facts │create_task  │
              │+fidelity│tasks/profile │read_file    │
              └─────────┴──────────────┴─────────────┘
                                ↓
                          Ollama (llama3.2)
                                ↓
                            Respuesta
```

---

## Router híbrido — 8 carriles

| Carril | Qué hace | Cómo se activa |
|---|---|---|
| `rag` | Recuperación semántica sobre documentos del proyecto | Preguntas documentales, conceptuales, "¿qué hace...?" |
| `memory` | Consulta tareas, perfil, hechos y estado de trabajo | Keywords de estado/foco/tareas pendientes |
| `tool_list_files` | Lista archivos del proyecto | "listar archivos", "qué archivos hay" |
| `tool_read_file` | Lee contenido de un archivo | Ruta detectada en la pregunta |
| `tool_save_fact` | Guarda un hecho en `project_facts.json` | "anota que", "guarda como hecho" |
| `tool_create_task` | Crea una tarea en `tasks.json` | "crea una tarea", "nueva tarea" |
| `tool_complete_task` | Marca una tarea como completada | "marca como completada", patrón `T-\d+` |
| `tool_update_work_state` | Actualiza `work_state.json` | "actualiza el foco", "ahora estoy en" |

---

## Memoria estructurada — 5 capas

| Archivo | Tipo de memoria | Se actualiza con |
|---|---|---|
| `storage/profile.json` | Semántica / perfil | Manualmente o tool futura |
| `storage/work_state.json` | Operacional / working | `tool_update_work_state` |
| `storage/project_facts.json` | Semántica / hechos estables | `tool_save_fact` |
| `storage/tasks.json` | Operacional / tareas | `tool_create_task`, `tool_complete_task` |
| `storage/episodic_memory.json` | Episódica / sesiones | `save_episode()` al salir |

---

## Logging del router

```
[router:kw]  'pregunta...' → rag          ← keywords (0ms)
[router:emb] similitud=0.93 lane=rag      ← embeddings (~50ms)
[router:llm] 'pregunta...' → memory       ← LLM fallback (~3-8s)
```

---

## Límites actuales de diseño

No conviene agregar todavía:
- multiagente complejo
- planner autónomo
- tools de alto riesgo (shell arbitraria)
- memoria indiscriminada (historial completo como contexto)

La prioridad es mantener una arquitectura local, pequeña, segura
y con fronteras limpias entre capas.

---

## Base documental del RAG

Documentos que el agente consulta como conocimiento del proyecto:

| Archivo | Contenido |
|---|---|
| `data/docs/proyecto/arquitectura_actual.md` | Este documento |
| `data/docs/proyecto/estado_proyecto.md` | Fases, objetivos y estado actual |
| `data/docs/proyecto/decisiones_arquitectura.md` | ADRs: registro de decisiones de diseño |
| `data/docs/proyecto/roadmap.md` | Próximos pasos y prioridades |
| `data/docs/referencia/memoria_agentes_resumen.md` | Teoría de memoria en agentes |
