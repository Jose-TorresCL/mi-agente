# 🤖 mi-agente

Asistente de IA local con arquitectura modular: RAG, memoria en capas,
router híbrido de intenciones y sistema de métricas. Funciona 100% offline
usando modelos locales a través de Ollama.

---

## ¿Qué hace?

- Clasifica cada consulta por intención (16 carriles) antes de responder
- Recupera documentos relevantes con RAG + caché semántica anti-repetición
- Mantiene memoria en 4 capas: trabajo, episódica, semántica y larga duración
- Verifica calidad de respuesta antes de entregarla (fidelity check, 2 modos)
- Ejecuta herramientas propias: guardar hechos, crear tareas, consultar estado
- Registra métricas por turno: latencia, carril usado, tokens, calidad RAG, canal de acceso
- Funciona 100% local: sin APIs externas, sin costos, sin internet
- Mantiene memoria episódica entre sesiones y sugiere tareas automáticamente al arranque

---

## Stack tecnológico

| Herramienta | Función |
|---|---|
| [Ollama](https://ollama.ai) | Ejecutar modelos de lenguaje localmente |
| [LangChain](https://langchain.com) | Orquestar el flujo RAG y las herramientas |
| [ChromaDB](https://trychroma.com) | Base de datos vectorial (RAG + caché semántica) |
| Python 3.11 | Lenguaje principal del proyecto |

---

## Estructura del proyecto

```text
mi-agente/
├── chat.py                     # Punto de entrada — inicia la sesión
├── run_eval.py                 # Evaluador de calidad de respuestas
├── show_metrics.py             # Dashboard de métricas por sesión
├── build_intent_index.py       # Construye el índice de intenciones
├── indexacion.py               # Indexa documentos en ChromaDB
├── requirements.txt            # Dependencias
│
├── app/                        # Módulos del asistente (26 módulos)
│   ├── __init__.py             # Inicialización del paquete
│   ├── intelligence.py         # Orquestador principal (16 carriles)
│   ├── router.py               # Router híbrido 3 capas
│   ├── rag_engine.py           # Motor RAG
│   ├── memory_manager.py       # Guardián único de lectura/escritura de memoria
│   ├── memory_store.py         # Persistencia de las 4 capas
│   ├── memory_context.py       # Recuperación selectiva por tipo de memoria
│   ├── episode_store.py        # Almacén de episodios y experiencias
│   ├── fidelity_check.py       # Verificación de calidad de respuesta (2 modos)
│   ├── semantic_cache.py       # Caché semántica de consultas
│   ├── llm_client.py           # Cliente Ollama unificado
│   ├── tools.py                # Herramientas ejecutables (5)
│   ├── tool_registry.py        # Registro de herramientas disponibles
│   ├── tool_helpers.py         # Utilidades para herramientas
│   ├── schemas.py              # TypedDict — contratos de datos
│   ├── metrics.py              # Registro de métricas por turno
│   ├── chat_core.py            # Orquestación de turno e historial
│   ├── chat_ui.py              # Interfaz de usuario (terminal + Telegram)
│   ├── session_state.py        # Estado de sesión activa
│   ├── prompts.py              # Plantillas de prompts
│   ├── formatters.py           # Formatos de respuesta
│   ├── text_utils.py           # Normalización de texto
│   ├── logger.py               # Logging estructurado
│   ├── intent_index.py         # Interfaz de intent_index (Capa 2)
│   ├── indexing_core.py        # Core de indexación de documentos
│   └── config.py               # Configuración centralizada
│
├── docs/                       # Documentación del proyecto
│   ├── adr/                    # Decisiones de arquitectura (ADR-001 a ADR-008)
│   ├── vision-agente.md        # Visión y hoja de ruta
│   ├── arquitectura-memoria.md # Detalle de las 4 capas de memoria
│   └── hardware-modelos.md     # Hardware y modelos recomendados
│
├── data/                       # Documentos a indexar
└── tests/                      # Tests del proyecto
```

> `storage/` (ChromaDB e índices) y `.venv/` se generan localmente
> y no están en el repositorio.

---

## Canales de Acceso

El agente puede ejecutarse desde dos interfaces. Ambas comparten el mismo núcleo (`intelligence.py`) y la misma memoria.

### Terminal (CLI)

```bash
python chat.py
```

Modo interactivo directo. Ideal para desarrollo, pruebas y uso local sin configuración extra.

### Telegram

Permite usar el agente desde cualquier dispositivo vía bot de Telegram. Requiere configurar `TELEGRAM_TOKEN` en las variables de entorno.

```bash
# Configurar token (Windows PowerShell)
$env:TELEGRAM_TOKEN = "tu_token_aqui"
python chat.py --telegram
```

El canal de acceso se registra en cada turno como campo `channel` dentro de `storage/metrics/*.jsonl`.
Esto permite filtrar métricas por canal (CLI vs Telegram) en `show_metrics.py`.

> **Aislamiento de sesiones**: cada sesión de Telegram genera su propio `session_id`
> y no interfiere con sesiones CLI activas. La memoria es compartida entre canales.

---

## Carriles de Enrutamiento (Router Híbrido — 16 carriles)

El agente clasifica cada consulta en uno de estos 16 carriles antes de procesar:

### Herramientas (7 carriles)
- `tool_list_files` — Listar archivos del proyecto
- `tool_read_file` — Leer contenido de archivo
- `tool_save_fact` — Guardar hecho en memoria
- `tool_create_task` — Crear tarea nueva
- `tool_complete_task` — Marcar tarea como completada
- `tool_update_work_state` — Actualizar foco de trabajo
- `tool_set_session_goal` — Guardar objetivo de sesión

### Memoria (6 carriles)
- `memory` — Consulta genérica de memoria
- `memory:profile` — Consultar perfil del usuario
- `memory:work_state` — Consultar foco actual
- `memory:tasks` — Listar tareas
- `memory:project_facts` — Consultar hechos del proyecto
- `memory:episode` — Consultar sesiones anteriores

### Especiales (3 carriles)
- `identity` — Preguntas sobre el agente (respuesta hardcodeada)
- `rag` — Consultas a documentos (RAG)
- `unsupported` — Solicitudes no soportadas

> Nota: los 9 carriles originales se refinaron en subtipos de memoria.
> La arquitectura actual trabaja con 16 carriles lógicos documentados arriba.

---

## Herramientas Disponibles (5)

El agente puede ejecutar estas herramientas sin pasar por el LLM:

- `tool_save_fact(content)` — Guarda hecho en `project_facts.json`
- `tool_create_task(title, priority, notes)` — Crea tarea en `tasks.json`
- `tool_complete_task(task_id)` — Marca tarea como completada
- `tool_update_work_state(field, value)` — Actualiza `work_state.json`
- `tool_set_session_goal(content)` — Guarda objetivo de sesión

---

## Verificación de Fidelidad (Fidelity Check)

Antes de entregar cada respuesta RAG, el agente verifica que el LLM no haya inventado información. Existen dos modos según el carril:

### Modo `numeric` (por defecto para carril `rag`)

Además de similitud semántica, comprueba que cada número de la respuesta aparezca literalmente en los chunks fuente.

- **Cuándo se usa**: carriles técnicos o documentales donde el LLM puede inventar cifras precisas.
- **Ejemplo bloqueado**: el LLM dice "342 líneas" pero ningún chunk menciona ese número — la respuesta se bloquea aunque la similitud semántica sea alta.
- **Excepciones**: números de 1 dígito (0-9), años (1900-2099), y números que ya estaban en la pregunta original.

### Modo `semantic` (para carriles de memoria)

Solo verifica similitud coseno entre la respuesta y los chunks. Sin verificación numérica literal.

- **Cuándo se usa**: carriles donde los números provienen de JSON de memoria (`tasks`, `work_state`), no de chunks RAG.
- **Ejemplo**: "tengo 3 tareas pendientes" — el 3 viene de `tasks.json`, no de un chunk, por lo que la verificación numérica aplicaría un falso positivo.

### Umbral dinámico (ADR-004)

| Longitud de pregunta | Umbral |
|---|---|
| ≤4 tokens (pregunta corta) | 0.40 |
| 5–12 tokens (normal) | 0.55 |
| >12 tokens (larga) | 0.60 |

### Ver estadísticas de fidelidad

```bash
python -c "from app.fidelity_check import fidelity_stats; print(fidelity_stats())"
```

Los logs se guardan en `storage/logs/fidelity_failures.jsonl` y `storage/logs/fidelity_successes.jsonl`.

---

## Flujo Automático de Memoria (`main_memory_flow`)

Al arrancar una nueva sesión, el agente ejecuta automáticamente `main_memory_flow()` desde `chat_core.py`. Este proceso:

1. **Lee** todos los episodios anteriores desde `storage/episodes.json`.
2. **Detecta** episodios con señales de acción (palabras: `decisión`, `tarea`, `acción` en el resumen).
3. **Crea tareas** sugeridas en `storage/tasks.json` para cada episodio relevante (sin duplicados).

```python
from app.memory_manager import main_memory_flow


# Llamar una vez por sesión, al arranque
tareas_nuevas = main_memory_flow()
print(f"{tareas_nuevas} tarea(s) sugeridas desde episodios anteriores")
```

> **Advertencia**: produce escritura en disco (`storage/tasks.json`).
> No llamar en bucle — puede crear tareas duplicadas si los resúmenes
> cambian entre ejecuciones. Llamar **una vez por sesión** desde `chat_core`.

---

## Instalación

### Requisitos previos

- Python 3.11+
- [Ollama](https://ollama.ai) instalado y corriendo
- Modelo recomendado: `ollama pull llama3.2`
- Modelo de embeddings: `ollama pull nomic-embed-text`

### Pasos

```bash
# 1. Clonar el repositorio
git clone https://github.com/Jose-TorresCL/mi-agente.git
cd mi-agente

# 2. Crear y activar entorno virtual
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Indexar documentos
python indexacion.py

# 5. Construir índice de intenciones
python build_intent_index.py

# 6. Iniciar el chat
python chat.py
```

---

## Variables de Entorno

| Variable | Requerida | Descripción |
|---|---|---|
| `TELEGRAM_TOKEN` | Solo Telegram | Token del bot de Telegram |

Todas las demás opciones de configuración (modelos, rutas, umbrales) se encuentran en `app/config.py`.

---

## Uso

```text
Tú: ¿Qué hace el módulo router.py?
Agente: [responde basándose en documentos indexados + memoria]

Tú: Guarda que el proyecto usa Python 3.11
Agente: [ejecuta tool_save_fact sin pasar por el LLM]

Tú: ¿Cuáles son mis tareas pendientes?
Agente: [consulta memory:tasks y responde desde JSON]
```

---

## Métricas

Cada turno registra un JSON en `storage/metrics/`. Ver resumen:

```bash
python show_metrics.py
```

Campos registrados por turno: `session_id`, `timestamp`, `route`, `channel`, `latency_ms`, `tokens`, `rag_quality`, `fidelity_score`, `fidelity_mode`.

---

## Documentación

| Documento | Contenido |
|---|---|
| [ADR-001](docs/adr/ADR-001-router-hibrido.md) | Router híbrido 3 capas |
| [ADR-002](docs/adr/ADR-002-memoria-en-capas.md) | Memoria en capas y tipos formales |
| [ADR-003](docs/adr/ADR-003-memory-manager.md) | memory_manager como guardián único |
| [ADR-004](docs/adr/ADR-004-calidad-rag.md) | Calidad RAG: caché, fidelity y exclusiones |
| [ADR-005](docs/adr/ADR-005-arquitectura-inteligencia.md) | Carriles de decisión e intelligence.py |
| [ADR-006](docs/adr/ADR-006-experience-index.md) | Experience index y feedback loop |
| [ADR-007](docs/adr/ADR-007-modelo-unico-vs-multi-modelo.md) | Modelo único vs multi-modelo |
| [ADR-008](docs/adr/ADR-008-candidato-reemplazo-modelo.md) | Candidato de reemplazo de modelo |
| [Visión](docs/vision-agente.md) | Hoja de ruta del proyecto |
| [Arquitectura de memoria](docs/arquitectura-memoria.md) | Detalle de las 4 capas |
| [Hardware y modelos](docs/hardware-modelos.md) | Modelos compatibles con el hardware |

---

## Estado del proyecto

✅ Fases 1-8 completadas — base funcional, memoria, router, inteligencia, herramientas  
✅ R1 — Sistema de métricas por turno  
✅ R2 — Dashboard de métricas con análisis de drift  
✅ R3 — Caché semántica + mejoras fidelity  
✅ R4 — Recuperación selectiva de memoria por tipo  

🔭 Próximo: pruebas integrales + definir siguiente dirección

---

## Autor

**Jose Torres** — [@Jose-TorresCL](https://github.com/Jose-TorresCL)