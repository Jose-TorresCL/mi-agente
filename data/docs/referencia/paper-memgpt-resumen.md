
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

| Tipo | Dónde vive | Velocidad | Capacidad | Ejemplo en mi-agente (Fase 8) |
|---|---|---|---|---|
| In-context | Ventana del LLM | Instantánea | Limitada (~4K-8K tokens) | System prompt en `prompts.py`, últimos turnos en `chat_core.py` |
| Working context | In-context, gestionado | Instantánea | ~500-1000 tokens | `work_state.json` + `tasks.json` → `memory_context.py` |
| Archival | Chroma (vectorstore) | Segundos | Ilimitada | `storage/chroma/` (docs), `storage/experience_index/` (episodios) |
| Recall | Base de datos de conversaciones | Segundos | Ilimitada | `storage/episodic_memory.json` (resúmenes de sesión) |

---

## Cómo se aplica a mi-agente (estado actual — Fase 8, 24/05/2026)

> Esta sección refleja la arquitectura real del proyecto hoy.

### Lo que ya está implementado (análogo a MemGPT)

```
[Working context] → work_state.json + tasks.json + project_facts.json + profile.json
                   ensamblados en contexto via memory_context.py
                   accesibles a través de memory_manager.py (guardián único)
                   seleccionados por get_context_for(intent_type)

[Archival memory] → storage/chroma/ (documentación del proyecto, 306+ chunks)
                    recuperado via rag_engine.py con MMR y fidelity_check
                    + experience_index en storage/experience_index/ (episodios vectorizados)
                    consultado via episode_store.experience_lookup()

[Recall memory]   → storage/episodic_memory.json
                    resúmenes de sesiones pasadas guardados al salir
                    buscables via episode_store.search_episodes()
```

### Correspondencia de carriles del router con tipos de memoria MemGPT

| Carril (router.py) | Tipo memoria MemGPT | Qué recupera |
|---|---|---|
| `memory` (TERMINAL) | Working context | work_state, tasks, project_facts, profile |
| `rag` | Archival memory | Documentos del proyecto en Chroma |
| `episode` | Recall memory | Episodios buscables en experience_index |
| `tool_save_fact` | core_memory_append | Escribe en project_facts.json |
| `tool_update_work_state` | core_memory_replace | Actualiza work_state.json |

### Lo que falta para llegar a MemGPT completo

1. **Compresión automática de sesión**: al salir, el LLM ya resume la sesión en `episodic_memory.json` — funciona. Lo que falta es indexar esos episodios automáticamente sin requerir ejecutar `indexacion.py` manualmente.
2. **Self-editing completo**: `tool_save_fact` y `tool_update_work_state` ya permiten escritura selectiva. Falta que el agente pueda también actualizar `profile.json` via tool.
3. **Router de memoria inteligente por composición**: `get_context_for(intent_type)` ya hace selección por capa. La Fase R4 (plan-robustecimiento.md) define la composición explícita para preguntas que mezclan capas.

---

## Diferencia entre MemGPT y lo que tengo ahora (Fase 8)

| Característica | MemGPT completo | mi-agente Fase 8 actual |
|---|---|---|
| Working context | Automático (LLM decide) | Determinista (`get_context_for()` por carril) |
| Archival storage | Vectorstore con tools | Chroma + `rag_engine.py` con MMR y fidelity_check |
| Self-editing | Sí (LLM escribe su memoria) | Parcial (`tool_save_fact`, `tool_update_work_state`, `tool_create_task`) |
| Compresión | Automática durante conversación | Al cerrar sesión (`episode_store.save_episode()`) |
| Multi-sesión | Sí | Sí (`episodic_memory.json` + `experience_index`) |
| Selección de fuente | LLM decide con tools | Router híbrido + `get_context_for()` determinista |

**Conclusión práctica**: La arquitectura actual (Fase 8) es más determinista que MemGPT original, lo cual es una ventaja para hardware limitado: las decisiones de qué recuperar no consumen tokens del LLM principal. Cubre el 85% del valor de MemGPT con una fracción de la complejidad.

---

## Resultados del paper

- MemGPT superó significativamente a GPT-4 estándar en tareas que requieren memoria larga.
- En conversaciones de 10+ turnos sobre información vista al inicio, MemGPT recuperó correctamente el 94% de los hechos vs 12% del baseline.
- La arquitectura funciona con cualquier LLM que soporte function calling.

---

## Error común al leer este paper

**Confusión**: Creer que necesitas implementar MemGPT completo para tener un agente con buena memoria.

**Realidad**: Los principios son los valiosos — capas de memoria, recuperación selectiva, working context separado de archival. Puedes implementar el 80% del valor con un 20% de la complejidad usando JSON + Chroma. Mi-agente Fase 8 ya demuestra esto en práctica.

---

## Buenas prácticas derivadas del paper

- Nunca inyectar toda la memoria al contexto — solo lo relevante para la pregunta actual. En mi-agente: `get_context_for(intent_type)` hace exactamente esto.
- Separar claramente memoria de trabajo (mutable, pequeña) de memoria archival (grande, buscable).
- El historial de conversación debe comprimirse, no crecer infinito. En mi-agente: `save_episode()` al salir.
- El agente debe poder actualizar su propia memoria, no solo leerla. En mi-agente: tools de escritura ya existen.

---

> Última actualización de la sección "Cómo se aplica": 25/05/2026 — alineado con arquitectura Fase 8 (Sprint 4 completo, 306 tests).
> Para más detalle de las 5 capas, ver: `data/docs/arquitectura-memoria.md`
> Para la arquitectura de memoria liviana complementaria, ver: `data/docs/referencia/paper-lightmem-resumen.md`
