# ADR-005 — Arquitectura de inteligencia: carriles, orquestador y tests

**Estado:** ✅ Aceptado  
**Fecha:** 2026-05  
**Autores:** Jose Torres + Asistente IA local

---

## Contexto

A medida que el agente creció, `chat_core.py` acumuló lógica heterogénea:
clasificación de intención, ejecución de tools, llamada al LLM, gestión de
memoria y métricas. Esto hacía el código difícil de leer, testear y extender.

Se necesitaba una capa de orquestación que:
- Centralizara el ciclo de vida de cada turno
- Hiciera explícito el flujo por carriles
- Permitiera testear la arquitectura sin depender del LLM

## Decisión

Se creó `app/intelligence.py` como **orquestador único del agente**,
con un modelo de 9 carriles de decisión explícitos.

### Los 9 carriles

```
┌──────────────────────────────────────────────────────────┐
│                   intelligence.py                        │
│                                                          │
│  1. exit          → cierra sesión, guarda episodio       │
│  2. memory        → memory_manager.get_context_for()     │
│  3. rag           → RAG pipeline + fidelity check        │
│  4. tool_list_files    → lista archivos del proyecto     │
│  5. tool_read_file     → lee un archivo específico       │
│  6. tool_save_fact     → guarda hecho en memoria         │
│  7. tool_create_task   → crea tarea en memoria           │
│  8. tool_complete_task → marca tarea completada          │
│  9. unsupported   → respuesta honesta de límite          │
└──────────────────────────────────────────────────────────┘
```

### Carril TERMINAL: `exit`

El carril `exit` es el único que interrumpe el ciclo de turnos.
Al detectarse, `intelligence.py` ejecuta la secuencia de cierre:

1. Genera resumen episódico de la sesión (llama al LLM)
2. Guarda el episodio en la Capa 4 (memory.json) y Capa 5 (experience_index)
3. Registra el carril dominante de la sesión en el episodio
4. Solicita al usuario la señal de calidad (s/n)
5. Actualiza `exitoso` en el episodio según la señal recibida
6. Cierra limpiamente

Este flujo garantiza que **cada sesión queda registrada** en el experience_index
independientemente de cómo terminó.

### Métricas por turno

Cada turno registra en `app/metrics.py`:

```python
@dataclass
class TurnMetrics:
    lane: str           # carril usado
    latency_ms: int     # tiempo total del turno
    cache_hit: bool     # si la caché semántica respondió
    router_layer: str   # "kw" | "emb" | "llm"
    tokens_in: int      # tokens del prompt
    tokens_out: int     # tokens de la respuesta
```

Las métricas se acumulan en sesión y son visibles con `!estado`.

### Tests de arquitectura

`tests/test_architecture.py` verifica invariantes sin LLM:

- Todos los carriles del router están manejados en `intelligence.py`
- Ningún módulo fuera de `memory_manager.py` importa `memory_store.py`
- `intelligence.py` no importa directamente `memory_store.py`
- Las métricas se registran en todos los carriles

`tests/test_routing_matrix.py` verifica la cobertura del router:

- 30 casos distribuidos en todos los carriles
- Al menos 2 casos por carril
- Los 3 carriles especiales (exit, memory, unsupported) tienen casos propios

## Alternativas consideradas

| Alternativa | Pros | Contras |
|-------------|------|---------|
| Lógica en `chat_core.py` (anterior) | Sin archivos extra | Mezcla de responsabilidades, difícil de testear |
| Framework de agentes (LangChain Agent) | Abstracciones predefinidas | Oculta el flujo, difícil de depurar localmente |
| **`intelligence.py` como orquestador** ✅ | Flujo explícito, testeable sin LLM | Un archivo más, convención a mantener |

## Consecuencias

**Positivas:**
- El flujo de cada turno es legible de un vistazo en `intelligence.py`.
- Los tests de arquitectura detectan regresiones sin necesidad de Ollama.
- Agregar un carril nuevo requiere: (1) keywords en `router.py`,
  (2) handler en `intelligence.py`, (3) casos en la matriz de tests.
- `!estado` muestra distribución de carriles de la sesión actual.

**Trade-offs:**
- `intelligence.py` tiende a crecer. Si supera ~200 líneas, considerar
  extraer los handlers de tools a un módulo `tool_handlers.py`.
- Los tests de arquitectura dependen de los nombres de los carriles —
  renombrar un carril requiere actualizar los tests.

## Archivos clave

- `app/intelligence.py` — orquestador
- `app/metrics.py` — `TurnMetrics` dataclass
- `tests/test_architecture.py` — invariantes de arquitectura
- `tests/test_routing_matrix.py` — matriz de 30 casos
