# Arquitectura actual

## Propósito

Este archivo describe cómo está armado hoy el asistente local Lautaro,
qué rol cumple cada componente y cómo se relacionan las tres capas del
sistema: Conversación → Inteligencia → Memoria.

Última actualización: 24/05/2026 — Sprint 4 completo: 306/306 tests, normalización router.

---

## Modelo y herramientas base

| Componente | Rol |
|---|---|
| **Ollama** | Ejecuta modelos de lenguaje localmente |
| **llama3.2** | Modelo base para generación de respuestas |
| **nomic-embed-text** | Embeddings para RAG, caché semántica, clasificación de intenciones y experience index |
| **Chroma** | Base vectorial para RAG (`storage/chroma/`), intent index (`storage/intent_index/`) y experience index (`storage/experience_index/`) |
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
  app/intelligence.py     ← orquestador de decisión por carriles
  app/rag_engine.py       ← retrieval semántico con caché y fidelity check
  app/fidelity_check.py   ← verificación de soporte documental (numérica + semántica)
  app/tool_registry.py    ← despacho centralizado de tools
  app/tools.py            ← 6 tools operativas
  app/tool_helpers.py     ← utilidades de extracción de argumentos
  app/metrics.py          ← logger de métricas por turno (metrics.jsonl)
        ↓
Memoria
  app/memory_manager.py   ← guardián único de lectura/escritura (anotado con MemoryType)
  app/memory_store.py     ← lectura/escritura segura de JSON
  app/memory_context.py   ← ensamblador de contexto para prompts
  app/episode_store.py    ← experience_index en Chroma + search_episodes + experience_lookup
  app/schemas.py          ← TypedDict + MemoryType enum (WORKING, SEMANTIC, EPISODIC, PROCEDURAL)
  app/semantic_cache.py   ← caché semántica de respuestas RAG (solo carril rag)
```

**Principio clave**: la memoria no conoce al router ni a la UI.
El router no escribe JSON directamente. La conversación no decide
qué carril usar. El carril `memory` es TERMINAL — no pasa por caché.

---

## Archivos principales

| Archivo | Capa | Rol |
|---|---|---|
| `chat.py` | Conversación | Punto de entrada |
| `app/chat_ui.py` | Conversación | Interfaz de consola y presentación |
| `app/chat_core.py` | Conversación | Orquestador: recibe input, llama inteligencia, devuelve respuesta |
| `app/config.py` | Transversal | Constantes globales y configuración centralizada |
| `app/logger.py` | Transversal | Logging estructurado por módulo |
| `app/router.py` | Inteligencia | Router híbrido 3 capas + classify_memory_query |
| `app/intelligence.py` | Inteligencia | Orquestador de decisión: recibe carril, devuelve respuesta |
| `app/rag_engine.py` | Inteligencia | Motor RAG con caché y fidelity check |
| `app/fidelity_check.py` | Inteligencia | Verifica soporte documental (numérica + semántica + casos borde) |
| `app/tool_registry.py` | Inteligencia | Registro y despacho de tools |
| `app/tools.py` | Inteligencia | Implementación de las 6 tools operativas |
| `app/tool_helpers.py` | Inteligencia | Extracción de argumentos de herramientas |
| `app/prompts.py` | Inteligencia | Plantillas de sistema y reglas de comportamiento |
| `app/metrics.py` | Inteligencia | Logger de métricas por turno → `storage/metrics.jsonl` |
| `app/memory_manager.py` | Memoria | Guardián único de lectura/escritura, anotado con MemoryType |
| `app/memory_store.py` | Memoria | Lectura y escritura segura de JSON |
| `app/memory_context.py` | Memoria | Ensamblador de contexto para prompts |
| `app/episode_store.py` | Memoria | experience_index, search_episodes, experience_lookup, señal de calidad |
| `app/schemas.py` | Memoria | TypedDict + MemoryType enum |
| `app/semantic_cache.py` | Memoria | Caché semántica de respuestas RAG (umbral 0.88, solo carril rag) |
| `app/session_state.py` | Conversación | Vista resumida del estado actual (`!estado`) |
| `indexacion.py` | Herramienta | Indexa documentos en Chroma |
| `build_intent_index.py` | Herramienta | Construye el índice de intenciones (96 ejemplos) |

---

## Flujo del sistema — Fase 6+

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
                          intelligence.py
              ┌──────────┬──────────────┬─────────────┬──────────┐
              │  rag     │   memory     │  episode    │  tools   │
              │Chroma    │work_state    │search_      │save_fact │
              │+caché    │project_facts │episodes()   │create_   │
              │+fidelity │tasks/profile │Chroma       │task ...  │
              │+exp.inj. │TERMINAL      │             │          │
              └──────────┴──────────────┴─────────────┴──────────┘
                                ↓
                          Ollama (llama3.2)
                                ↓
                            Respuesta
                                ↓
                          metrics.py → metrics.jsonl
```

---

## Router híbrido — 9 carriles

| Carril | Qué hace | Cómo se activa |
|---|---|---|
| `rag` | Recuperación semántica sobre documentos del proyecto + experience injection | Preguntas documentales, conceptuales |
| `memory` | Consulta tareas, perfil, hechos y estado de trabajo (TERMINAL, no pasa por caché) | Keywords de estado/foco/tareas pendientes |
| `episode` | Búsqueda semántica en experience_index de episodios pasados | "¿en qué quedamos?", "sesión anterior" |
| `tool_list_files` | Lista archivos del proyecto | "listar archivos", "qué archivos hay" |
| `tool_read_file` | Lee contenido de un archivo | Ruta detectada en la pregunta |
| `tool_save_fact` | Guarda un hecho en `project_facts.json` | "anota que", "guarda como hecho" |
| `tool_create_task` | Crea una tarea en `tasks.json` | "crea una tarea", "nueva tarea" |
| `tool_complete_task` | Marca una tarea como completada | "marca como completada", patrón `T-\d+` |
| `tool_update_work_state` | Actualiza `work_state.json` | "actualiza el foco", "ahora estoy en" |
| `unsupported` | Respuesta directa sin LLM | Consultas fuera del alcance |

---

## Memoria estructurada — 5 capas + Experience Index

| Archivo | Tipo de memoria | MemoryType | Se actualiza con |
|---|---|---|---|
| `storage/profile.json` | Semántica / perfil | SEMANTIC | Manualmente o tool futura |
| `storage/work_state.json` | Operacional / working | WORKING | `tool_update_work_state` |
| `storage/project_facts.json` | Semántica / hechos estables | SEMANTIC | `tool_save_fact` |
| `storage/tasks.json` | Operacional / tareas | WORKING | `tool_create_task`, `tool_complete_task` |
| `storage/episodic_memory.json` | Episódica / sesiones JSON | EPISODIC | `save_episode()` al salir |
| `storage/experience_index/` | Episódica / Chroma vectorial | EPISODIC | `indexacion.py` post-sesión |

---

## Cobertura de tests (24/05/2026)

| Suite | Tests | Estado |
|---|---|---|
| `test_architecture.py` | Invariantes de imports entre capas | ✅ |
| `test_memory_route.py` | Carril memory TERMINAL, no toca caché | ✅ |
| `test_memory_layer.py` | get_context_for() devuelve solo la capa pedida | ✅ |
| General | 306/306 tests verde, 39% cobertura | ✅ |

---

## Invariantes arquitecturales protegidos por tests

| Invariante | Test que lo protege |
|---|---|
| `chat_ui.py` no importa `memory_store` | `test_architecture.py` |
| `router.py` no importa `rag_engine` | `test_architecture.py` |
| `memory_manager.py` no importa `chat_ui` | `test_architecture.py` |
| Carril `memory` no consulta caché semántico | `test_memory_route.py` |
| `get_context_for()` devuelve solo la capa pedida | `test_memory_layer.py` |

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
| `data/docs/referencia/paper-slm-first-resumen.md` | Paper SLM-First aplicado al proyecto |
| `data/docs/referencia/paper-moa-resumen.md` | Paper MoA — patrón de auto-refinamiento |
