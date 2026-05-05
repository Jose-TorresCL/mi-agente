# Memoria en mi-agente (Fase 2 - 05/05/2026)

## Idea general

La memoria permite al asistente usar contexto previo y hechos persistentes de forma más útil que solo historial conversacional.

## Tipos de memoria implementados

| Tipo | Archivo | Contenido | Uso |
|------|---------|-----------|-----|
| **Corto plazo** | `storage/memory.json` | Conversación reciente | Contexto inmediato de sesión |
| **Perfil** | `storage/profile.json` | Preferencias usuario | Cómo prefiere trabajar Lautaro |
| **Semántica** | `storage/project_facts.json` | Hechos estables proyecto | Estado de fases, prioridades |
| **Episódica/Continuidad** | `storage/work_state.json` | Estado actual trabajo | En qué iba, qué sigue |
| **Tareas** | `storage/tasks.json` | Pendientes y acciones | Qué hacer, qué está hecho |

## Módulos de memoria

- **`app/memory_store.py`**: lectura/escritura segura de JSON.
- **`app/session_state.py`**: vista resumida de estado actual.
- **`app/prompts.py`**: instrucciones que guían uso de memoria.

## Diferencia práctica: RAG vs Memoria

| RAG (Chroma) | Memoria estructurada |
|--------------|---------------------|

| Conocimiento estable del proyecto (`estado_proyecto.md`, `arquitectura_actual.md`) | Estado dinámico del trabajo (`tasks.json`, `work_state.json`) |
| “Qué es el proyecto” | “En qué estamos hoy” |
| Recuperación semántica | Acceso directo por clave |
| Preguntas documentales | Consultas de estado/tareas |

## Estado actual de memoria (Fase 2)

**Implementado**:

- 5 JSON con estructura base.
- `memory_store.py` funcional (leer, escribir, actualizar).
- Datos iniciales cargados (perfil, hechos, tareas, estado).

**Próximo**:

- Conectar memoria al chat.
- Router para decidir RAG vs memoria.
- Tools para actualizar memoria (guardar hecho, agregar tarea).

## Qué es memoria híbrida en mi-agente

Combinación práctica:

1. **RAG**: consulta documentos estables.
2. **Memoria corta**: contexto reciente.
3. **Memoria persistente**: hechos, tareas, estado.
4. **Router**: decide qué usar según consulta.

**Ejemplo**:Pregunta: "¿En qué fase estamos?"
→ Router: memoria semántica → project_facts.json → "fase_2"

Pregunta: "¿Qué dice arquitectura_actual.md?"
→ Router: RAG → Chroma → documentos fuente

## Respuesta correcta vs respuesta grounded

| Correcta | Grounded |
|----------|----------|

| Coincide con realidad del proyecto | + Evidencia explícita (fuente/cita) |

| “Estamos en fase 2” | “project_facts.json indica fase_2” |

## Comportamiento ideal por capa

**RAG**:

- Responder solo con evidencia documental clara.
- Abstenerse si falta contexto.

**Memoria**:

- Usar datos estructurados para hechos, estado, tareas.
- Actualizar vía tools cuando corresponda.

**Router**:"guarda esto" → tool → memory_store.update()
"qué sigue" → memoria → work_state.json
"qué dice X" → RAG → Chroma

## Próximos commits de memoria

1. "2B: memoria estructurada base + conexión al chat"
2. "2C: tools para memoria (guardar hecho, agregar tarea)"
3. "2D: router RAG/memoria/tool"
