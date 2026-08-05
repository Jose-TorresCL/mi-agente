# Mapa de Arquitectura de Memoria — mi-agente

> Última actualización: 19/05/2026 — Fases 6, 7A y 8 completas.

Este documento describe las **5 capas de memoria** del asistente,
con ejemplos reales de datos en cada capa.

> Decisión arquitectural de referencia: [ADR-002](adr/ADR-002-memoria-en-capas.md)

---

## Visión general

```
                   ┌──────────────────────────────────┐
                   │         CONSULTA DEL USUARIO      │
                   └─────────────┬────────────────────┘
                                 │
              ┌─────────────────▼─────────────────┐
              │      intelligence.py / router          │
              │   get_context_for(intent_type)         │
              └──┬────────┬────────┬────────┬────────┘
                 │          │          │          │
           ┌────▼──┐  ┌────▼──┐  ┌────▼──┐  ┌────▼──┐
           │WORKING │  │SEMANT. │  │EPISOD. │  │EPISOD. │
           │Capa 1-2│  │Capa 3  │  │Capa 4  │  │Capa 5  │
           │  JSON  │  │  JSON  │  │  JSON  │  │ Chroma │
           └────────┘  └────────┘  └────────┘  └────────┘
```

Todas las capas son accedidas únicamente a través de `memory_manager.py`.
Ninguna capa superior importa `memory_store.py` directamente.

---

## MemoryType enum (schemas.py)

Cada capa tiene un tipo formal definido en `app/schemas.py`:

```python
class MemoryType(str, Enum):
    WORKING    = "working"     # RAM + work_state + tasks
    SEMANTIC   = "semantic"    # profile + project_facts
    EPISODIC   = "episodic"    # episodic_memory.json + experience_index
    PROCEDURAL = "procedural"  # reservado para reglas futuras
```

---

## Capa 1 — Memoria de Trabajo en RAM (WORKING)

**¿Qué es?** La información activa en el turno actual.  
**Duración:** Un solo intercambio usuario → asistente.  
**Dónde vive:** Variable Python en RAM (`chat_history: list`).  
**Quién la maneja:** `chat_core.py`

```python
[
    HumanMessage(content="¿qué hace el módulo router.py?"),
    AIMessage(content="El router clasifica la intención del usuario..."),
    HumanMessage(content="¿y cuántas capas tiene?"),  # ← turno actual
]
```

**Límite:** `MAX_TURNS * 2` mensajes (configurable en `app/config.py`).

---

## Capa 2 — Memoria Operacional (WORKING)

**¿Qué es?** Estado dinámico del proyecto: foco, tareas, siguiente paso.  
**Duración:** Persistente entre sesiones.  
**Dónde vive:** `storage/work_state.json` + `storage/tasks.json`  
**Quién la maneja:** `tool_update_work_state`, `tool_create_task`, `tool_complete_task`

```json
// work_state.json
{
  "current_focus": "Fase 7 — Observabilidad",
  "last_completed": "Fase 8D — MemoryType enum",
  "next_step": "show_metrics.py (Fase 7B)",
  "current_blockers": []
}

// tasks.json (extracto)
{
  "tasks": [
    {"id": "T-042", "title": "show_metrics.py", "priority": "alta", "status": "pending"}
  ]
}
```

---

## Capa 3 — Memoria Semántica (SEMANTIC)

**¿Qué es?** Perfil del usuario y hechos estables del proyecto.  
**Duración:** Permanente.  
**Dónde vive:** `storage/profile.json` + `storage/project_facts.json`  
**Quién la maneja:** `tool_save_fact`, actualización manual

```json
// profile.json
{
  "user_name": "Jose",
  "user_level": "junior",
  "project_type": "asistente IA local",
  "preferred_style": ["didáctico", "paso a paso"]
}

// project_facts.json
{
  "modelo_base": "llama3.2",
  "fase_actual": "Fase 7 — Observabilidad",
  "stack": "Python, LangChain, Chroma, Ollama",
  "tests_pasando": "67+"
}
```

---

## Capa 4 — Memoria Episódica JSON (EPISODIC)

**¿Qué es?** Resúmenes de sesiones pasadas en texto plano.  
**Duración:** Permanente, se acumula entre sesiones.  
**Dónde vive:** `storage/episodic_memory.json`  
**Quién la maneja:** `memory_manager.record_episode()` al cerrar sesión

```json
{
  "episodes": [
    {
      "timestamp": "2026-05-19T11:00:00",
      "turns": 24,
      "exitoso": true,
      "summary": "Se implementó experience_index en Chroma.\nSe añadió boost +0.15 para episodios exitosos.\nSiguiente: show_metrics.py"
    }
  ]
}
```

**Generación:** Al cerrar sesión (`salir`/`exit`), el LLM resume
automáticamente los últimos turnos. Se pregunta s/n si la sesión fue exitosa.

---

## Capa 5 — Experience Index Chroma (EPISODIC)

**¿Qué es?** Los episodios de la Capa 4 indexados como vectores para
recuperación semántica. Permite encontrar episodios relevantes por *tema*,
no solo el más reciente.  
**Duración:** Permanente, se reconstruye con `indexacion.py`.  
**Dónde vive:** `storage/experience_index/` (Chroma)  
**Quién la maneja:** `episode_store.experience_lookup()`

```python
# En carril RAG, antes de construir el prompt:
experience = experience_lookup(user_input, score_threshold=0.80)
if experience:
    context_text = f"[Experiencia previa relevante]\n{experience}\n\n" + context_text
```

Episodios con `exitoso=True` reciben boost `+0.15` en el score.

---

## Los 3 índices Chroma del proyecto

```
storage/
  chroma/              ← documentos del proyecto (269 chunks, estático)
  intent_index/        ← 96 ejemplos de intención para el router
  experience_index/    ← episodios de sesión (dinámico, crece con cada sesión)
```

---

## Cómo fluye el contexto en cada carril

```
Carril rag:
  get_context_for("rag")
      └── get_semantic_context()  ← profile + project_facts
      + chunks de Chroma (MMR, k=5)
      + experience_lookup() si score ≥ 0.80

Carril memory (TERMINAL):
  get_context_for("work_state")
      └── get_working_context()   ← work_state + tasks
      # NO pasa por caché semántico

Carril episode:
  search_episodes(query)
      └── experience_index Chroma  ← búsqueda semántica
      + boost si exitoso=True
```

---

## Resumen de archivos de storage

| Archivo | Capa | MemoryType | Quién escribe |
|---|---|---|---|
| RAM (`chat_history`) | 1 | WORKING | `chat_core.py` |
| `storage/work_state.json` | 2 | WORKING | `tool_update_work_state` |
| `storage/tasks.json` | 2 | WORKING | `tool_create_task`, `tool_complete_task` |
| `storage/profile.json` | 3 | SEMANTIC | Manual / tool futura |
| `storage/project_facts.json` | 3 | SEMANTIC | `tool_save_fact` |
| `storage/episodic_memory.json` | 4 | EPISODIC | `record_episode()` al salir |
| `storage/experience_index/` | 5 | EPISODIC | `indexacion.py` post-sesión |
| `storage/metrics.jsonl` | — | — | `metrics.py` por turno |

---

## Evolución futura

| Mejora | Cuándo considerarla |
|---|---|
| Migrar JSON a SQLite | Cuando episodios superen ~500 entradas |
| Separar chroma por proyectos | Cuando haya múltiples proyectos activos |
| TTL en hechos del proyecto | Cuando algunos hechos queden obsoletos |
| Planner con memoria procedural | Fase 9+ — requiere base estable |
