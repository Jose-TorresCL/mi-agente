# Arquitectura actual

## Propósito

Este archivo describe cómo está armado hoy el asistente local Lautaro,
qué rol cumple cada componente y cómo se relacionan las tres capas del
sistema: Conversación → Inteligencia → Memoria.

Última actualización: 03/08/2026 — consolidación de tools (R6-A parcial), endurecimiento de `tool_registry.py`, `ToolResult` como contrato común y mejora de `tool_complete_task` para completar por ID u ordinales. [file:131][file:132]

---

## Modelo y herramientas base

| Componente | Rol |
|---|---|
| **Ollama** | Ejecuta modelos de lenguaje localmente. [file:131] |
| **llama3.2** | Modelo base histórico para generación de respuestas del asistente. [file:131][file:133] |
| **nomic-embed-text** | Embeddings para RAG, caché semántica, clasificación de intenciones y `experience_index`. [file:131] |
| **Chroma** | Base vectorial para RAG (`storage/chroma/`), intent index (`storage/intent_index/`) y experience index (`storage/experience_index/`). [file:131] |
| **LangChain** | Orquestación del flujo general y del retrieval. [file:131] |
| **JSON en `storage/`** | Persistencia de memoria estructurada local. [file:131] |
| **python-telegram-bot** | Interfaz Telegram (`app/telegram_interface.py`). [file:131] |

---

## Tres capas del sistema

El sistema está organizado en tres capas con dirección de dependencia
unidireccional: Conversación → Inteligencia → Memoria. [file:131][file:132]

```text
Conversación
  chat.py
  app/chat_ui.py
  app/chat_core.py          ← orquestador principal (CLI y Telegram)
  app/telegram_interface.py ← interfaz Telegram (comparte chat_core)
  app/session_state.py      ← vista resumida del estado (!estado)
        ↓
Inteligencia
  app/router.py             ← 3 capas: keywords → embeddings → LLM
  app/intelligence.py       ← orquestador de decisión por carriles
  app/rag_engine.py         ← retrieval semántico con caché y fidelity check
  app/fidelity_check.py     ← verificación de soporte documental (numérica + semántica)
  app/tool_registry.py      ← despacho centralizado de tools + clasificación de riesgo
  app/tools.py              ← tools operativas con retorno ToolResult
  app/tool_helpers.py       ← utilidades de extracción de argumentos y parseo
  app/intent_index.py       ← clasificador por embeddings (96 ejemplos en Chroma)
  app/metrics.py            ← logger de métricas por turno (metrics.jsonl)
  app/prompts.py            ← plantillas de sistema y reglas de comportamiento
  app/formatters.py         ← formateadores de salida por tipo de carril
        ↓
Memoria
  app/memory_manager.py     ← guardián único de lectura/escritura (anotado con MemoryType)
  app/memory_store.py       ← lectura/escritura segura de JSON
  app/memory_context.py     ← ensamblador de contexto para prompts
  app/episode_store.py      ← experience_index en Chroma + search_episodes + experience_lookup
  app/schemas.py            ← TypedDict + MemoryType enum + ToolResult + RiskLevel
  app/semantic_cache.py     ← caché semántica de respuestas RAG (solo carril rag)
```

**Principio clave**: la memoria no conoce al router ni a la UI.
El router no escribe JSON directamente. La conversación no decide
qué carril usar. El carril `memory` es TERMINAL — no pasa por caché. [file:131][file:132]

---

## Archivos principales

| Archivo | Capa | Rol |
|---|---|---|
| `chat.py` | Conversación | Punto de entrada CLI. [file:131] |
| `app/chat_ui.py` | Conversación | Interfaz de consola y presentación. [file:131] |
| `app/chat_core.py` | Conversación | Orquestador: recibe input, llama inteligencia y devuelve respuesta. [file:131] |
| `app/telegram_interface.py` | Conversación | Punto de entrada Telegram (reutiliza `chat_core`). [file:131] |
| `app/session_state.py` | Conversación | Vista resumida del estado actual (`!estado`). [file:131] |
| `app/config.py` | Transversal | Constantes globales y configuración centralizada. [file:131] |
| `app/logger.py` | Transversal | Logging estructurado por módulo. [file:131] |
| `app/router.py` | Inteligencia | Router híbrido 3 capas + clasificación inicial del tipo de consulta. [file:131] |
| `app/intelligence.py` | Inteligencia | Orquestador de decisión: recibe carril, compone contexto y devuelve respuesta. [file:131] |
| `app/rag_engine.py` | Inteligencia | Motor RAG con caché semántico, MMR y `fidelity_check`. [file:131][file:132] |
| `app/fidelity_check.py` | Inteligencia | Verifica soporte documental (numérica + semántica + casos borde). [file:131] |
| `app/tool_registry.py` | Inteligencia | Registro y despacho de tools, clasificación de riesgo (`READ`, `WRITE`, `SYSTEM`), handlers que interpretan `user_input` crudo y wrapper de compatibilidad `dispatch_tool_str()`. [file:131] |
| `app/tools.py` | Inteligencia | Implementación de tools operativas; las tools públicas retornan `ToolResult` como contrato común (R6-A parcial). [file:131] |
| `app/tool_helpers.py` | Inteligencia | Extracción de argumentos, validaciones pequeñas y helpers reutilizables de parseo. [file:131] |
| `app/intent_index.py` | Inteligencia | Clasificación por embeddings en Chroma (96 ejemplos). [file:131] |
| `app/prompts.py` | Inteligencia | Plantillas de sistema y reglas de comportamiento. [file:131] |
| `app/formatters.py` | Inteligencia | Formateadores de salida por tipo de carril. [file:131] |
| `app/metrics.py` | Inteligencia | Logger de métricas por turno → `storage/metrics.jsonl`. [file:131][file:133] |
| `app/memory_manager.py` | Memoria | Guardián único de lectura/escritura, anotado con `MemoryType`. [file:131][file:132] |
| `app/memory_store.py` | Memoria | Lectura y escritura segura de JSON. [file:131] |
| `app/memory_context.py` | Memoria | Ensamblador de contexto para prompts. [file:131] |
| `app/episode_store.py` | Memoria | `experience_index`, `search_episodes`, `experience_lookup`, señal de calidad y feedback episódico. [file:131][file:133] |
| `app/schemas.py` | Memoria | `TypedDict`, `MemoryType`, `ToolResult` y `RiskLevel`. [file:131] |
| `app/semantic_cache.py` | Memoria | Caché semántica de respuestas RAG (umbral 0.88, solo carril `rag`). [file:131] |
| `indexacion.py` | Herramienta | Indexa documentos en Chroma. [file:131] |
| `build_intent_index.py` | Herramienta | Construye el índice de intenciones (96 ejemplos). [file:131] |

---

## Flujo del sistema — Fase 6+

```text
Usuario (CLI o Telegram)
  ↓
chat.py / telegram_interface.py  →  chat_core.py
                                          ↓
                                     router.py
                                    /     |      \
                        Capa 1: kw  Capa 2: emb   Capa 3: LLM
                         (0ms)       (~50ms)        (~3-8s)
                                          ↓
                                    intelligence.py
              ┌──────────┬──────────────┬───────────┬───────────────┬─────────┐
              │  rag     │   memory     │  episode  │     tools     │  exit   │
              │Chroma    │work_state    │search_    │save_fact      │__EXIT__ │
              │+caché    │project_facts │episodes() │create_task    │         │
              │+fidelity │tasks/profile │Chroma     │complete_task  │         │
              │+exp.inj. │TERMINAL      │           │update_state   │         │
              └──────────┴──────────────┴───────────┴───────────────┴─────────┘
                                          ↓
                                    Ollama (modelo local)
                                          ↓
                                      Respuesta
                                          ↓
                                    metrics.py → metrics.jsonl
```

---

## Router híbrido — carriles actuales

| Carril | Qué hace | Cómo se activa |
|---|---|---|
| `rag` | Recuperación semántica sobre documentos del proyecto + experience injection. [file:131][file:133] | Preguntas documentales, conceptuales o de arquitectura. [file:131] |
| `memory` | Consulta tareas, perfil, hechos y estado de trabajo; es TERMINAL y no pasa por caché. [file:131][file:133] | Keywords de estado, foco, tareas, perfil y trabajo actual. [file:131] |
| `episode` | Búsqueda semántica en `experience_index` de episodios pasados. [file:131][file:133] | “¿En qué quedamos?”, “sesión anterior”, “qué hicimos la última vez”. [file:131] |
| `tool_list_files` | Lista archivos del proyecto. [file:131][file:133] | “listar archivos”, “qué archivos hay”. [file:131] |
| `tool_read_file` | Lee el contenido de un archivo del proyecto. [file:131][file:133] | Ruta detectada o petición explícita de leer archivo. [file:131] |
| `tool_save_fact` | Guarda un hecho en `project_facts.json`. [file:131] | “anota que”, “guarda como hecho”. [file:131] |
| `tool_create_task` | Crea una tarea en `tasks.json`. [file:131] | “crea una tarea”, “nueva tarea”, “agrega tarea”. [file:131] |
| `tool_complete_task` | Marca una tarea como completada. [file:131] | Por ID (`T-...`) o por ordinal sobre tareas pendientes (“primera”, “segunda”, “tercera”, “cuarta”, “quinta”, “última”, “penúltima”). [file:131] |
| `tool_update_work_state` | Actualiza `work_state.json`. [file:131] | “actualiza el foco”, “ahora estoy en”, “siguiente paso”. [file:131] |
| `tool_set_session_goal` | Guarda el objetivo concreto de la sesión actual en `work_state.json`. [file:131] | “mi objetivo hoy es…”, “meta de hoy…”. [file:131] |
| `tool_analizar_mercado` | Integra consulta externa al bot de trading; es una tool de riesgo `SYSTEM`. [file:131] | Consultas sobre mercado, precio, BTC, ETH o señales. [file:131] |
| `exit` | Cierra la sesión. [file:131] | “salir”, “exit”, “adiós”, “chao”, “nos vemos”. [file:131] |
| `unsupported` | Respuesta directa sin LLM para consultas fuera de alcance. [file:131] | Cuando la consulta no pertenece al dominio útil del asistente. [file:131] |

---

## Tools y contratos

Las tools operativas viven en `app/tools.py` y su despacho centralizado
vive en `app/tool_registry.py`. La regla actual es:

- `app/tools.py` ejecuta la acción real sobre memoria o sistema. [file:131]
- `app/tool_registry.py` interpreta el `user_input` crudo y decide cómo invocar cada tool. [file:131]
- El acceso a memoria pasa por `memory_manager`, no por `memory_store` directamente. [file:131][file:132]
- La interfaz estructurada de retorno es `ToolResult`. [file:131]

### Contrato R6-A parcial

```text
dispatch_tool(carril, user_input) -> ToolResult | None
dispatch_tool_str(carril, user_input) -> str | None
```

Esto permite:

- compatibilidad con callers antiguos que esperan `str`, [file:131]
- tests y métricas sobre resultados estructurados (`ok`, `message`, `data`, `error_code`, `tool_name`, `side_effect`), [file:131]
- endurecimiento gradual sin romper la API pública ya usada en otras partes del sistema. [file:132]

### Clasificación de riesgo

| Nivel | Significado |
|---|---|
| `READ` | Solo lectura, sin efectos secundarios persistentes. [file:131] |
| `WRITE` | Escritura en `storage/` interno del agente. [file:131] |
| `SYSTEM` | Acceso a recursos externos o subprocess; requiere confirmación/habilitación explícita. [file:131] |

`dispatch_tool()` bloquea automáticamente tools con `risk=SYSTEM` si no hay
soporte explícito de confirmación humana. [file:131]

---

## Memoria estructurada — 5 capas + Experience Index

| Archivo | Tipo de memoria | MemoryType | Se actualiza con |
|---|---|---|---|
| `storage/profile.json` | Semántica / perfil | `SEMANTIC` | Manualmente o tool futura. [file:131] |
| `storage/work_state.json` | Operacional / working | `WORKING` | `tool_update_work_state`, `tool_set_session_goal`. [file:131] |
| `storage/project_facts.json` | Semántica / hechos estables | `SEMANTIC` | `tool_save_fact`. [file:131] |
| `storage/tasks.json` | Operacional / tareas | `WORKING` | `tool_create_task`, `tool_complete_task`. [file:131] |
| `storage/episodic_memory.json` | Episódica / sesiones JSON | `EPISODIC` | `save_episode()` al salir. [file:131] |
| `storage/experience_index/` | Episódica / Chroma vectorial | `EPISODIC` | indexación de episodios y `experience_lookup`. [file:131][file:133] |

### Nota práctica

La memoria episódica no solo guarda qué pasó, sino también una señal de
calidad o productividad de la sesión. Esa idea coincide con el uso de
memoria episódica en agentes: recuperar experiencias previas útiles y
darles más peso cuando funcionaron bien. [web:191][web:198]

---

## Experience Index y feedback episódico

El sistema ya usa una memoria episódica doble:

1. un registro JSON de sesiones,
2. un índice vectorial en Chroma para recuperar experiencias similares. [file:131][file:133]

Además, al cerrar sesión, Lautaro puede registrar si la sesión fue
productiva (`s/n`) y usar esa señal como parte del feedback loop del
episodio. Eso fortalece el uso posterior de experiencias exitosas. [file:133][web:198]

---

## Cobertura de tests conocida

| Suite | Qué protege | Estado conocido |
|---|---|---|
| `test_architecture.py` | Invariantes de imports entre capas. [file:131] | ✅ |
| `test_memory_route.py` | Carril `memory` TERMINAL, sin caché semántico. [file:131] | ✅ |
| `test_memory_layer.py` | `get_context_for()` devuelve solo la capa pedida. [file:131] | ✅ |
| General | Base de tests verde reportada en la auditoría del 24/05/2026. [file:131] | ✅ |

> Nota: este documento conserva la última cifra global reportada en la auditoría previa; si cambió el número total de tests, actualizar aquí junto con el último run real. [file:131]

---

## Invariantes arquitecturales protegidos por tests

| Invariante | Test que lo protege |
|---|---|
| `chat_ui.py` no importa `memory_store` | `test_architecture.py` [file:131] |
| `router.py` no importa `rag_engine` | `test_architecture.py` [file:131] |
| `memory_manager.py` no importa `chat_ui` | `test_architecture.py` [file:131] |
| Carril `memory` no consulta caché semántico | `test_memory_route.py` [file:131] |
| `get_context_for()` devuelve solo la capa pedida | `test_memory_layer.py` [file:131] |

---

## Logging del router

```text
[router:kw]  'pregunta...' → rag          ← keywords (0ms)
[router:emb] similitud=0.93 lane=rag      ← embeddings (~50ms)
[router:llm] 'pregunta...' → memory       ← LLM fallback (~3-8s)
```

En la práctica, el objetivo sigue siendo que las consultas simples y
operativas caigan por keyword o embeddings antes de necesitar LLM. Eso
reduce latencia y hace el comportamiento más predecible. [file:131][file:133]

---

## Límites actuales de diseño

No conviene agregar todavía:

- multiagente complejo, [file:131][file:133]
- planner autónomo, [file:131]
- tools de alto riesgo sin confirmación humana, [file:131]
- memoria indiscriminada basada en historial completo como contexto. [file:131][web:191]

La prioridad sigue siendo mantener una arquitectura local, pequeña,
segura y con fronteras limpias entre capas. [file:131][file:133]

---

## Estado práctico actual — 03/08/2026

El proyecto ya superó la fase de prototipo y hoy está en una etapa de
**consolidación**: router, memoria, tools seguras, estado de trabajo y
documentación alineada con el código. [file:133][file:131]

Los avances más visibles en esta etapa son:

- `tool_registry.py` endurecido con clasificación de riesgo y wrappers de compatibilidad. [file:131]
- `tools.py` migrado a `ToolResult` como contrato común parcial. [file:131]
- `tool_complete_task` mejorado para aceptar ID y ordinales sobre tareas pendientes. [file:131]
- feedback episódico activo al cerrar sesión. [file:133][web:198]

---

## Bugs conocidos y pendientes de hardening (actualizado 03/08/2026)

| Bug | Descripción | Carril afectado | Prioridad |
|---|---|---|---|
| B-01 | “cerrar sesión” puede no activar correctamente carril `exit` y responder identidad. [file:131] | `exit` / `identity` | Alta |
| B-02 | “Qué es Chroma” puede activar identidad en vez de RAG documental. [file:131] | `rag` / `identity` | Alta |
| B-03 | Algunas definiciones técnicas siguen saliendo genéricas en vez de apoyarse bien en docs propios. [file:131] | `rag` | Media |
| B-04 | `ProfileData` en `schemas.py` usa claves distintas a `profile.json` (`name/level/project` vs `user_name/user_level/project_type`). [file:131] | contratos | Media |
| B-05 | `tool_complete_task` ya resuelve ordinales frecuentes, pero todavía puede ampliarse para cubrir índice numérico directo o título exacto. [file:131] | `tool_complete_task` | Media |

---

## Base documental del RAG — inventario práctico

Documentos que el agente consulta como conocimiento del proyecto.
Los marcados como 🔴 deben excluirse del índice antes de re-indexar. [file:131]

### Documentos del proyecto

| Archivo | Contenido | Estado |
|---|---|---|
| `data/docs/proyecto/arquitectura_actual.md` | Este documento. [file:131] | ✅ |
| `data/docs/proyecto/decisiones_arquitectura.md` | Resumen de ADRs. [file:132] | ✅ |
| `data/docs/proyecto/plan-robustecimiento.md` | Plan R1–R7 con estado actual. [file:131] | ✅ |
| `data/docs/proyecto/fase6-tareas.md` | Histórico Fase 6. [file:131] | 🟡 Solo si sigue siendo útil como histórico |

### Documentos de referencia

| Archivo | Contenido | Estado |
|---|---|---|
| `data/docs/referencia/memoria_agentes_resumen.md` | Teoría de memoria en agentes. [file:131] | ✅ |
| `data/docs/referencia/paper-slm-first-resumen.md` | Paper SLM-First. [file:131] | ✅ |
| `data/docs/referencia/paper-moa-resumen.md` | Paper MoA. [file:131] | ✅ |
| `data/docs/referencia/paper-memgpt-resumen.md` | MemGPT — actualizado Fase 8. [file:131] | ✅ |
| `data/docs/referencia/paper-lightmem-resumen.md` | LightMem — muy relevante para R4. [file:131] | ✅ Verificar indexación |
| `data/docs/referencia/langchain-embeddings.md` | Embeddings con `nomic-embed-text`. [file:131] | ✅ |
| `data/docs/referencia/langchain-retriever.md` | Retriever MMR y threshold. [file:131] | ✅ |
| `data/docs/referencia/langchain-rag-concepto.md` | RAG conceptual. [file:131] | ✅ |
| `data/docs/referencia/langchain-text-splitters.md` | Chunking y splitters. [file:131] | ✅ Verificar |
| `data/docs/referencia/chroma-uso-proyecto.md` | Chroma curado para el proyecto. [file:131] | ✅ |
| `data/docs/arquitectura-memoria.md` | Las 5 capas de memoria con datos reales. [file:131] | ✅ |

### ADRs

| Archivo | Contenido | Estado |
|---|---|---|
| `data/docs/adr/ADR-001-router-hibrido.md` | Decisión del router 3 capas. [file:131][file:132] | ✅ Confirmar indexación |
| `data/docs/adr/ADR-002-memoria-en-capas.md` | Decisión de arquitectura de memoria. [file:131][file:132] | ✅ Confirmar indexación |
| `data/docs/adr/ADR-003-memory-manager.md` | Guardián único de memoria. [file:131][file:132] | ✅ Confirmar indexación |
| `data/docs/adr/ADR-004-mejoras-rag-calidad.md` | Mejoras RAG: MMR, fidelity. [file:131][file:132] | ✅ |
| `data/docs/adr/ADR-005-modos-agente-tool-codigo.md` | Modos de agente y tools. [file:131][file:132] | ✅ |
| `data/docs/adr/ADR-006-experience-index.md` | Experience index en Chroma. [file:131][file:132] | ✅ |

### Documentos a excluir del índice

| Archivo | Razón | Acción |
|---|---|---|
| `data/docs/referencia/chroma-introduccion.md` | 🔴 Scraping de navegación web. [file:131] | Excluir de `indexacion.py` |
| `data/docs/referencia/chroma-queries.md` | 🔴 Scraping web con contenido mezclado. [file:131] | Excluir de `indexacion.py` |
| `data/docs/referencia/ollama-api.md` | 🔴 56KB sin curar, domina el índice. [file:131] | Excluir o reemplazar con resumen |
| `data/docs/proyecto/estado_proyecto.md` | Documento vivo, se lee por tool. [file:131] | Excluido (correcto) |
| `data/docs/proyecto/roadmap.md` | Documento vivo, planificación futura. [file:131] | Excluido (correcto) |