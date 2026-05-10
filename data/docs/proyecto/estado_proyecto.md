# Estado del proyecto

## Objetivo general

Construir un asistente local con Ollama, LangChain y Chroma para
responder preguntas usando recuperación de contexto desde documentos
del proyecto, evolucionando hacia un agente con memoria estructurada
por capas, tools controladas y recuperación selectiva de contexto.

---

## Fase actual: Fase 5 — Refactor modular y consolidación arquitectural

**Fecha de actualización**: 10/05/2026

**Objetivo de Fase 5**:
Consolidar la arquitectura en 3 capas limpias (Conversación →
Inteligencia → Memoria), cerrar las fugas de acoplamiento que
quedaron de Fase 4 y preparar el terreno para recuperación
selectiva de contexto.

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

---

## Estado técnico actual (10/05/2026)

### Lo que está firme

- Modularización completa en `app/` con separación por capas
- `config.py` como fuente única de constantes globales
- `rag_engine.py` como módulo independiente con caché semántica y fidelity check
- `tool_registry.py` como despachador centralizado de tools
- `memory_context.py` como ensamblador de contexto para prompts
- Router híbrido 3 capas operativo (keywords → embeddings → LLM fallback)
- 8 carriles de ejecución estables
- 67 tests pasando en la suite de tests
- Inyección automática de contexto al arrancar (work_state + tareas + episodio)
- Deduplicación de `project_facts` (sin claves repetidas)
- Memoria episódica: `save_episode()` al salir, `load_last_episode()` al arrancar

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

### Problemas pendientes

- Sin `memory_manager.py` como guardián formal de la capa de memoria
- Tools aún escriben directo a JSON sin pasar por interfaz única
- Sin batería de evaluación sistematizada (9 preguntas fijas)
- Recuperación selectiva entre RAG y memoria aún básica
- Sin distinción formal entre los 4 tipos de memoria en el código

---

## Próximos pasos — Fase 5 continuación

1. **`memory_manager.py`** — guardián de la capa de memoria. Punto único
   de lectura y escritura, con reglas coherentes. Cierra la fuga principal
   de acoplamiento entre capas.

2. **ADRs actualizados** — registrar en `decisiones_arquitectura.md` cada
   decisión de diseño ya tomada y las razones.

3. **Tests por capa aislada** — un test que cambie `work_state` sin tocar
   `chat_ui.py` verifica que las capas están bien separadas.

4. **Recuperación selectiva de contexto** — elegir qué tipo de memoria
   (working / semántica / episódica) es relevante para cada pregunta.

5. **Batería de validación fija** — 9 preguntas estándar ejecutables
   con un script.

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
- **Caché semántica**: evita re-invocar LLM para preguntas similares
- **Fidelity check**: evita respuestas sin soporte documental real
- **Tools**: acciones controladas sobre archivos y memoria
- **Router 3 capas**: keywords → embeddings → LLM fallback
