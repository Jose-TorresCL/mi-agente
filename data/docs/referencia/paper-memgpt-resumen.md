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

## Cómo se aplica a mi-agente

### Lo que ya implementé (análogo a MemGPT)

```
[Working context] → profile.json + projectfacts.json + workstate.json
                   inyectado al prompt via buildStructuredMemoryContext()

[Archival memory] → Chroma vectorstore con docs de referencia
                    recuperado via retriever de LangChain

[Recall memory]   → storage/memory.json (ConversationBufferWindowMemory)
                    últimos k=8 turnos en contexto
```

### Lo que falta para llegar a MemGPT completo

1. **Router de memoria**: decidir automáticamente si una pregunta requiere RAG, working context o búsqueda en historial.
2. **Self-editing**: el agente puede actualizar su propia memoria (guardar hechos nuevos).
3. **Compresión de conversaciones**: cuando la sesión es larga, comprimir antes de guardar.

### Implementación incremental recomendada

```python
# Fase 2C actual: el agente SOLO LEE la memoria estructurada
memorycontext = build_structured_memory_context()  # ya implementado

# Fase 2D (próxima): el agente puede ESCRIBIR en su memoria
# tools: guardar_hecho(clave, valor), actualizar_tarea(id, estado)

# Fase 3 (futura): router decide qué fuente usar
# router: RAG si es documental, memoria si es estado/preferencias, tool si es acción
```

---

## Diferencia entre MemGPT y lo que tengo ahora

| Característica | MemGPT completo | mi-agente fase 2 actual |
|---|---|---|
| Working context | Automático (LLM decide) | Manual (buildStructuredMemoryContext) |
| Archival storage | Vectorstore con tools | Chroma con retriever |
| Self-editing | Sí (LLM escribe su memoria) | No todavía |
| Compresión | Automática | No implementada |
| Multi-sesión | Sí | Parcial (memory.json) |

**Conclusión práctica**: No necesito implementar MemGPT completo. Lo valioso es entender la arquitectura de capas y aplicarla progresivamente. Mi implementación actual ya cubre los niveles 1 y 2 de forma simplificada.

---

## Resultados del paper

- MemGPT superó significativamente a GPT-4 estándar en tareas que requieren memoria larga.
- En conversaciones de 10+ turnos sobre información vista al inicio, MemGPT recuperó correctamente el 94% de los hechos vs 12% del baseline.
- La arquitectura funciona con cualquier LLM que soporte function calling.

---

## Error común al leer este paper

**Confusión**: Creer que necesitas implementar MemGPT completo para tener un agente con buena memoria.

**Realidad**: Los principios son los valiosos — capas de memoria, recuperación selectiva, working context separado de archival. Puedes implementar el 80% del valor con un 20% de la complejidad usando JSON + Chroma.

---

## Buenas prácticas derivadas del paper

- Nunca inyectar toda la memoria al contexto — solo lo relevante para la pregunta actual.
- Separar claramente memoria de trabajo (mutable, pequeña) de memoria archival (grande, buscable).
- El historial de conversación debe comprimirse, no crecer infinito.
- El agente debe poder actualizar su propia memoria, no solo leerla.
