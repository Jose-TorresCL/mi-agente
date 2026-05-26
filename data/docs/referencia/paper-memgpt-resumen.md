# Paper Curado — MemGPT: Towards LLMs as Operating Systems

**Autores**: Charles Packer et al. (UC Berkeley, 2023)
**Paper original**: arxiv.org/abs/2310.08560
**Nivel**: Intermedio
**Relevancia para mi-agente**: ALTA — es la referencia principal de arquitectura de memoria por capas para agentes con LLM local.

---

## ¿Qué es MemGPT?

MemGPT es un sistema que resuelve el problema más crítico de los LLMs: el **límite de contexto**. Los LLMs solo pueden "ver" un número fijo de tokens a la vez (ventana de contexto). MemGPT propone una arquitectura inspirada en sistemas operativos donde el LLM actúa como un procesador que gestiona distintos niveles de memoria, igual que una CPU gestiona RAM y disco duro.

**Analogía clave**: Tu laptop tiene 16 GB de RAM pero 500 GB en disco. No puedes cargar todo en RAM a la vez — el OS decide qué sube y qué baja. MemGPT hace lo mismo con el contexto del LLM.

---

## Problema que resuelve

Sin MemGPT:
```
Conversación larga → se llena el contexto → LLM olvida lo que dijo al principio
```

Con MemGPT:
```
Conversación larga → MemGPT decide qué recordar, qué comprimir, qué recuperar
                  → LLM siempre tiene contexto relevante en su ventana
```

---

## Arquitectura de memoria de MemGPT

### Nivel 1 — Memoria In-Context (RAM del LLM)
Es la ventana de contexto activa del modelo. Todo lo que está aquí el LLM lo "ve" directamente.

- **System prompt**: instrucciones del agente, personalidad, reglas.
- **Working context**: información actual relevante (perfil del usuario, estado de la tarea).
- **FIFO queue**: mensajes recientes de conversación (los más nuevos empujan a los viejos).

**Límite**: finito (en llama3.2 ~4096-8192 tokens).

### Nivel 2 — Memoria Externa (Disco del LLM)
Todo lo que no cabe en contexto se guarda aquí. El LLM accede mediante funciones/tools.

- **Archival memory**: almacenamiento de largo plazo, búsqueda vectorial (Chroma). Aquí van documentos, hechos históricos, episodios pasados.
- **Recall memory**: historial de conversaciones comprimidas. Permite buscar "qué dije hace 3 semanas sobre X".

---

## Mecanismo central: Functions/Tools

MemGPT le da al LLM funciones especiales que puede llamar durante la conversación:

```
core_memory_append(name, content)   → agrega a working context (RAM)
core_memory_replace(name, content)  → reemplaza en working context
archival_memory_insert(content)     → guarda en disco (Chroma)
archival_memory_search(query)       → busca en disco y trae a contexto
conversation_search(query)          → busca en historial comprimido
```

El LLM decide **por sí mismo** cuándo llamar estas funciones. Si la conversación se pone larga, el modelo puede decidir:
1. Comprimir mensajes viejos → `archival_memory_insert(resumen)`
2. Borrar del contexto activo
3. Recuperar más tarde con → `archival_memory_search("qué hablamos sobre X")`

---

## Tipos de memoria según MemGPT

| Tipo | Dónde vive | Velocidad | Capacidad | Ejemplo en mi-agente |
|---|---|---|---|---|
| In-context | Ventana del LLM | Instantánea | Limitada (~4K-8K tokens) | System prompt, última pregunta |
| Working context | In-context, gestionado | Instantánea | ~500-1000 tokens | profile.json, workstate.json |
| Archival | Chroma (vectorstore) | Segundos | Ilimitada | docs de referencia, episodios |
| Recall | Base de datos de conversaciones | Segundos | Ilimitada | Historial comprimido de sesiones |

---

## Cómo se aplica a mi-agente — Estado real Fase 8 (mayo 2026)

> ⚠️ Esta sección refleja la arquitectura actual. Las fases anteriores usaban
> nombres distintos (`build_structured_memory_context`, `ConversationBufferWindowMemory`).
> Hoy esos están reemplazados por una arquitectura más madura.

### Lo que está implementado hoy ✅

```
[Working context — Capa 1 RAM]
  chat_core.py mantiene chat_history en memoria durante la sesión
  Límite configurable en app/config.py (MAX_TURNS)

[Working context — Capa 2 Operacional]
  storage/work_state.json  ← foco, tarea actual, bloqueadores
  storage/tasks.json       ← lista de tareas con estado
  Escritura via: tool_update_work_state, tool_create_task, tool_complete_task

[Semantic context — Capa 3]
  storage/profile.json        ← user_name, user_level, project_type
  storage/project_facts.json  ← modelo_base, fase_actual, stack, tests
  Acceso via: memory_context.py → get_semantic_context()

[Archival memory — Capa 4 Episodic JSON]
  storage/episodic_memory.json ← resúmenes de sesiones pasadas
  Escritura via: memory_manager.record_episode() al cerrar sesión
  Lectura via: episode_store.search_episodes()

[Archival memory — Capa 5 Experience Index]
  storage/experience_index/    ← episodios indexados en Chroma
  Búsqueda semántica con boost +0.15 para episodios exitosos
  Acceso via: episode_store.experience_lookup()

[Archival memory — RAG]
  storage/chroma/              ← 269 chunks de documentación del proyecto
  Acceso via: rag_engine.py con MMR (lambda_mult=0.6, fetch_k=20)
  Fidelidad verificada por: fidelity_check.py
```

**Guardián único de toda la memoria**: `memory_manager.py`
**Interfaz de acceso**: `get_context_for(intent_type: MemoryType)`
**Contrato formal**: `MemoryType` enum en `app/schemas.py`

```python
class MemoryType(str, Enum):
    WORKING    = "working"     # RAM + work_state + tasks
    SEMANTIC   = "semantic"    # profile + project_facts
    EPISODIC   = "episodic"    # episodic_memory.json + experience_index
    PROCEDURAL = "procedural"  # reservado para reglas futuras
```

### Lo que falta para llegar a MemGPT completo

| Característica | MemGPT completo | mi-agente Fase 8 |
|---|---|---|
| Working context | Automático (LLM decide) | Estructurado (code determina qué inyectar) |
| Archival storage | Vectorstore con tools | ✅ Chroma con retriever MMR |
| Self-editing de memoria | Sí (LLM escribe su memoria) | Parcial (tools write: save_fact, create_task) |
| Compresión episódica automática | Automática por token count | Manual al cerrar sesión (record_episode) |
| Multi-sesión | Sí | ✅ Funcional (episodic_memory.json + experience_index) |
| Recuperación selectiva por capa | Sí | ✅ get_context_for(intent_type) |

**Conclusión práctica**: La arquitectura de capas ya está implementada. Lo que falta es la
**compresión automática** (hoy es manual al salir) y el **self-editing completo** (hoy
el LLM puede guardar hechos pero no reescribir su working context libremente).

---

## Resultados del paper

- MemGPT superó significativamente a GPT-4 estándar en tareas que requieren memoria larga.
- En conversaciones de 10+ turnos sobre información vista al inicio, MemGPT recuperó correctamente el 94% de los hechos vs 12% del baseline.
- La arquitectura funciona con cualquier LLM que soporte function calling.

---

## Error común al leer este paper

**Confusión**: Creer que necesitas implementar MemGPT completo para tener un agente con buena memoria.

**Realidad**: Los principios son los valiosos — capas de memoria, recuperación selectiva, working context separado de archival. Puedes implementar el 80% del valor con un 20% de la complejidad usando JSON + Chroma. Mi-agente ya lo demuestra.

---

## Buenas prácticas derivadas del paper

- Nunca inyectar toda la memoria al contexto — solo lo relevante para la pregunta actual.
- Separar claramente memoria de trabajo (mutable, pequeña) de memoria archival (grande, buscable).
- El historial de conversación debe comprimirse, no crecer infinito.
- El agente debe poder actualizar su propia memoria, no solo leerla.
- La gestión de memoria debe tener un **guardián único** — en mi-agente es `memory_manager.py`.
