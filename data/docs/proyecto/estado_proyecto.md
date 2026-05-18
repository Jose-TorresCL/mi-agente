# Estado del proyecto

## Objetivo general

Construir un asistente local con Ollama, LangChain y Chroma para
responder preguntas usando recuperación de contexto desde documentos
del proyecto, evolucionando hacia un agente con memoria estructurada
por capas, tools controladas y recuperación selectiva de contexto.

---

## Fase actual: Fase 6 — Memory Manager y recuperación selectiva

**Fecha de actualización**: 17/05/2026

**Objetivo de Fase 6**:
Cerrar la última fuga arquitectural (tools escribiendo JSON directo)
mediante `memory_manager.py` como guardián único de la capa de memoria,
e implementar recuperación selectiva de contexto según tipo de pregunta.

---

## Hitos completados

| Hito | Fecha |
|---|---|
| Fase 1: RAG básico + indexación | Antes del 05/05/2026 |
| Fase 2: memoria, tools, router simple | 05/05/2026 |
| Fase 3A: router híbrido keywords + LLM | 06/05/2026 |
| Fase 3B: clasificador embeddings + intent_index | 06/05/2026 |
| Fase 4A–G: caché, fidelity check, episodios, fixes | 06–07/05/2026 |
| Fase 5A: refactor modular completo (`config.py`, `rag_engine.py`, `tool_registry.py`, `tool_helpers.py`, `memory_context.py`) | 08/05/2026 |
| Fase 5B: suite de 67 tests pasando | 08/05/2026 |
| Fase 5C: deduplicación de `project_facts` + inyección automática de contexto | 08–09/05/2026 |
| Fase 5D: `memory_manager.py` implementado como guardián de capa memoria | 10–16/05/2026 |
| Fase 5E: batería de evaluación fija (9 preguntas) operativa | 16/05/2026 |
| Fase 5F: mejoras calidad RAG — nuevos papers indexados (SLM-First, MoA) | 17/05/2026 |
| Fase 5G: exclusión de docs de baja calidad del índice (ollama-api, hardware, chroma-intro) | 17/05/2026 |

---

## Estado técnico actual (17/05/2026)

### Lo que está firme

- Modularización completa en `app/` con separación por capas
- `config.py` como fuente única de constantes globales
- `rag_engine.py` como módulo independiente con caché semántica y fidelity check
- `tool_registry.py` como despachador centralizado de tools
- `memory_context.py` como ensamblador de contexto para prompts
- `memory_manager.py` como guardián único de lectura/escritura de memoria
- Router híbrido 3 capas operativo (keywords → embeddings → LLM fallback)
- 8 carriles de ejecución estables
- 67+ tests pasando en la suite de tests
- Inyección automática de contexto al arrancar (work_state + tareas + episodio)
- Deduplicación de `project_facts` (sin claves repetidas)
- Memoria episódica: `save_episode()` al salir, `load_last_episode()` al arrancar
- Batería de evaluación fija: 9 preguntas estándar ejecutables con script
- Índice RAG depurado: 3 archivos de baja calidad excluidos

### Problemas resueltos acumulados

| Problema | Estado |
|---|---|
| Modularización de archivos grandes | ✅ |
| Falta de memoria persistente | ✅ |
| Router solo por reglas simples | ✅ |
| LLM fallback lento | ✅ embeddings ~50ms |
| `ConversationBufferWindowMemory` deprecada | ✅ |
| LLM inventaba IDs de tareas | ✅ regla anti-alucinación |
| `tool_save_fact` creaba claves duplicadas | ✅ formato key=value |
| RAG respondía sin soporte documental | ✅ fidelity_check |
| Respuestas RAG repetidas con costo LLM | ✅ caché semántica |
| Contexto de sesión anterior perdido | ✅ memoria episódica |
| `config.py` inexistente | ✅ centralizado |
| Tools sin punto central de despacho | ✅ tool_registry.py |
| RAG mezclado con chat_core | ✅ rag_engine.py separado |
| Tools escribían JSON directo sin guardián | ✅ memory_manager.py |
| Sin batería de evaluación fija | ✅ 9 preguntas estándar |
| Índice con docs obsoletos/genéricos | ✅ 3 archivos excluidos |
| Caché semántico con entradas corruptas | ✅ limpieza manual + fix estructural pendiente |

### Problemas pendientes

- Caché semántico puede ser interceptado antes del carril `memory` (fix estructural en curso)
- Recuperación selectiva entre tipos de memoria aún básica (working / semántica / episódica)
- Sin distinción formal ejecutada en código entre los 4 tipos de memoria
- Tests por capa aislada aún pendientes (integrados sí, por capa no)

---

## Próximos pasos — Fase 6

1. **Fix estructural del caché** — el caché semántico no debe interceptar
   el carril `memory`. Solo aplica en carril `rag`.

2. **Recuperación selectiva de contexto** — elegir qué tipo de memoria
   (working / semántica / episódica) es relevante para cada pregunta.

3. **Tests por capa aislada** — un test que cambie `work_state` sin tocar
   `chat_ui.py` verifica que las capas están bien separadas.

4. **Distinción formal de 4 tipos de memoria en código** — working, semántica,
   episódica, procedimental con interfaces separadas.

---

## Criterio de respuesta

- **RAG**: preguntas documentales, conceptuales, "¿qué hace...?",
  "¿cómo funciona...?", "¿qué es...?"
- **Memoria**: preferencias, hechos persistentes, tareas existentes,
  estado actual de trabajo
- **Tools**: acciones concretas sobre archivos o memoria estructurada
- Si no hay evidencia suficiente → abstenerse claramente

---

## Relación entre componentes

- **RAG**: conocimiento estable recuperado desde documentos Markdown
- **Memoria estructurada**: estado dinámico y persistente (JSON)
- **Memoria episódica**: resúmenes de sesión entre arranques
- **Caché semántica**: evita re-invocar LLM para preguntas similares (solo carril RAG)
- **Fidelity check**: evita respuestas sin soporte documental real
- **Tools**: acciones controladas sobre archivos y memoria
- **Router 3 capas**: keywords → embeddings → LLM fallback
- **Memory Manager**: guardián único de lectura/escritura de memoria estructurada
