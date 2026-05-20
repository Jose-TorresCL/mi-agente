# Mapa de Arquitectura de Memoria — mi-agente

Este documento describe en detalle las **4 capas de memoria** del asistente,
con ejemplos reales de datos en cada capa.

> Decisión arquitectural de referencia: [ADR-002](adr/ADR-002-memoria-en-capas.md)

---

## Visión general

```
                   ┌──────────────────────────────────┐
                   │         CONSULTA DEL USUARIO      │
                   └─────────────┬────────────────────┘
                                 │
              ┌──────────────────▼──────────────────┐
              │           memory_manager.py          │
              │     (fachada única de acceso)        │
              └──┬──────────┬──────────┬────────────┘
                 │          │          │
         ┌───────▼──┐  ┌────▼────┐  ┌─▼──────────┐
         │  Capa 1  │  │ Capa 2  │  │  Capa 3    │
         │ Working  │  │  Short  │  │ Semántica  │
         │  (RAM)   │  │  Term   │  │ (Chroma)   │
         └──────────┘  └─────────┘  └────────────┘
                              │
                       ┌──────▼──────┐
                       │   Capa 4   │
                       │ Long-Term  │
                       │(memory.json│
                       └────────────┘
```

---

## Capa 1 — Memoria de Trabajo (Working Memory)

**¿Qué es?** La información activa en el turno actual.  
**Duración:** Un solo intercambio usuario → asistente.  
**Dónde vive:** Variable Python en RAM (`chat_history: list`).  
**Quién la maneja:** `chat_core.py`

```python
# Ejemplo de estado de chat_history durante un turno:
[
    HumanMessage(content="¿qué hace el módulo router.py?"),
    AIMessage(content="El router clasifica la intención del usuario..."),
    HumanMessage(content="¿y cuántas capas tiene?"),  # ← turno actual
]
```

**Límite:** `MAX_TURNS * 2` mensajes (configurable en `app/config.py`).

---

## Capa 2 — Memoria Episódica Corta (Short-Term)

**¿Qué es?** Resumen de sesiones anteriores completas.  
**Duración:** Permanente (se acumula entre sesiones).  
**Dónde vive:** `storage/memory.json` → clave `"episodes"`  
**Quién la maneja:** `memory_manager.record_episode()`

```json
{
  "episodes": [
    {
      "timestamp": "2026-05-07T22:31:00",
      "turns": 12,
      "summary": "Se implementó el router híbrido de 3 capas.\nSe decidió usar umbral 0.70 para embeddings.\nPróximo paso: agregar tests de la capa 2."
    }
  ]
}
```

**Generación:** Al cerrar sesión (`salir`/`exit`), el LLM resume
automáticamente los últimos `MAX_TURNS` turnos en 3 líneas.

---

## Capa 3 — Memoria Semántica / RAG

**¿Qué es?** Documentos del proyecto indexados como vectores.  
**Duración:** Permanente.  
**Dónde vive:** `storage/chroma_db/` (base de datos vectorial Chroma)  
**Quién la maneja:** `app/rag_engine.py` + `indexacion.py`

```
storage/
└── chroma_db/
    ├── chroma.sqlite3
    └── <colección de embeddings>
```

**Cómo se usa:**
1. `indexacion.py` trocea los `.md`/`.txt` de `data/` en chunks.
2. Genera embeddings con `nomic-embed-text` vía Ollama.
3. En cada consulta RAG, se recuperan los `TOP_K` chunks más similares.
4. El LLM responde usando esos chunks como contexto.

**Diferencia con Capa 4:** Capa 3 contiene conocimiento *documental*
(cómo funciona algo). Capa 4 contiene datos *operacionales* (qué hice, qué falta).

---

## Capa 4 — Memoria Declarativa Larga (Long-Term)

**¿Qué es?** Datos estructurados que persisten indefinidamente.  
**Duración:** Permanente.  
**Dónde vive:** `storage/memory.json` (múltiples secciones)  
**Quién la maneja:** `app/memory_manager.py` (vía `app/memory_store.py`)

### Estructura de `storage/memory.json`

```json
{
  "profile": {
    "user_name": "Jose",
    "user_level": "junior",
    "project_type": "asistente IA local",
    "preferred_style": ["didáctico", "paso a paso"],
    "preferred_workflow": ["planificar", "implementar", "testear"]
  },

  "project_facts": {
    "modelo base": "llama3.2",
    "fase actual": "Fase 3B — router híbrido",
    "stack": "Python, LangChain, Chroma, Ollama"
  },

  "work_state": {
    "current_focus": "refactorizar memoria en capas",
    "last_completed": "implementar memory_manager",
    "next_step": "actualizar chat_core para usar memory_manager",
    "current_blockers": []
  },

  "tasks": {
    "tasks": [
      {
        "id": "T-001",
        "title": "Agregar ADRs al repositorio",
        "priority": "alta",
        "status": "done"
      }
    ]
  },

  "episodes": [
    {
      "timestamp": "2026-05-07T22:31:00",
      "turns": 12,
      "summary": "Resumen generado por el LLM al cerrar sesión."
    }
  ],

  "messages": [
    {"role": "human", "content": "último mensaje de la sesión anterior"},
    {"role": "ai",    "content": "última respuesta de la sesión anterior"}
  ]
}
```

### Sub-secciones y su propósito

| Sección | Qué guarda | Quién la escribe |
|---------|-----------|------------------|
| `profile` | Preferencias y nivel del usuario | Manual / `save_fact` |
| `project_facts` | Hechos técnicos del proyecto | `tool_save_fact` |
| `work_state` | Foco actual, siguiente paso, bloqueos | `tool_update_work_state` |
| `tasks` | Lista de tareas con estado | `tool_create_task`, `tool_complete_task` |
| `episodes` | Resúmenes de sesiones pasadas | Automático al cerrar |
| `messages` | Historial reciente (ventana) | Automático en cada turno |

---

## Flujo de contexto en cada consulta

```
Consulta RAG:
  memory_manager.get_full_context()
      │
      ├── get_working_context()  → foco + siguiente paso
      ├── get_semantic_context() → perfil + hechos del proyecto  
      └── get_episodic_context() → último episodio de sesión

Ese contexto se inyecta en el system prompt del LLM
como "memoria del asistente" antes de la pregunta.
```

---

## Evolución futura

| Mejora | Cuándo considerarla |
|--------|--------------------|
| Migrar `memory.json` a SQLite | Cuando los datos superen ~1000 entradas |
| Memoria episódica con embeddings | Para recuperar episodios por similitud semántica |
| Separar `chroma_db` por colecciones | Cuando haya múltiples proyectos |
| TTL en hechos del proyecto | Cuando algunos hechos queden obsoletos |

---

## Recuperación Selectiva (memory_context.py)

**¿Qué es?** Un módulo que decide *cuánto* contexto de memoria inyectar
en el prompt según el carril de enrutamiento activo.  
**Dónde vive:** `app/memory_context.py`  
**Quién lo llama:** `intelligence.py` antes de construir el prompt final.

### El problema que resuelve

Sin recuperación selectiva, cada consulta recibía el contexto completo
(perfil + hechos + work_state + tareas + episodio), lo que generaba
prompts innecesariamente largos en consultas simples.

### Cómo funciona

```python
get_selective_context(route: str) -> str
```

| Carril (`route`) | Contexto entregado | Razón |
|---|---|---|
| `memory` | Completo (perfil + hechos + work_state + tareas + episodio) | El LLM necesita todo para responder sobre el estado |
| `rag` | Solo perfil + hechos del proyecto | Evita contaminar el prompt RAG con estado operativo |
| `tool_*` | Vacío (`""`) | Las tools leen directamente de `storage/` |
| Otros carriles | Completo (fallback seguro) | Garantiza que nunca se pierda contexto |

### Comportamiento de `build_memory_context()`

Los campos de `work_state` (foco, siguiente paso, bloqueos) se incluyen
**solo si tienen valor**. Esto evita líneas vacías como `"- Siguiente paso: "`
en el prompt cuando el estado no está definido.

---

## Tipos formales de memoria (MemoryType)

`app/schemas.py` define el enum `MemoryType` que formaliza los tipos
de memoria que el sistema reconoce:

```python
class MemoryType(str, Enum):
    CONVERSATION = "conversation"   # Turno a turno (Capa 1)
    EPISODE      = "episode"        # Resumen de sesión (Capa 2)
    SEMANTIC     = "semantic"       # Documentos vectoriales (Capa 3)
    PROFILE      = "profile"        # Perfil del usuario (Capa 4)
    FACT         = "fact"           # Hecho del proyecto (Capa 4)
    WORK_STATE   = "work_state"     # Estado de trabajo (Capa 4)
    TASK         = "task"           # Tareas (Capa 4)
```

**Para qué sirve:** `memory_manager.py` usa este enum para anotar
cada operación de lectura/escritura, garantizando que nunca se mezclen
tipos de memoria en una misma operación.

> Decisiones de referencia: [ADR-002](adr/ADR-002-memoria-en-capas.md) y
> [ADR-003](adr/ADR-003-memory-manager.md)
