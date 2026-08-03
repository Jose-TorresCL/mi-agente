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
│   ├── tools_trading.py        # Wrapper de bot_trading (rama feat/integracion-bot-trading)
│   ├── tool_plan_retoma.py     # Lectura de analysis/retoma_plan.json (solo lectura)
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
│   ├── adr/                    # Decisiones de arquitectura (ADR-001 a ADR-010)
│   ├── vision-agente.md        # Visión y hoja de ruta
│   ├── arquitectura-memoria.md # Detalle de las 4 capas de memoria
│   └── hardware-modelos.md     # Hardware y modelos recomendados
│
├── analysis/                   # Planes y auditorías en JSON
│   └── retoma_plan.json        # Plan de retoma / auditoría de documentación
│
├── data/                       # Documentos a indexar
└── tests/                      # Tests del proyecto
```

> `storage/` (ChromaDB e índices) y `.venv/` se generan localmente
> y no están en el repositorio. Excepciones versionadas a propósito:
> `storage/project_facts.json`, `storage/workstate.json` y
> `storage/episodic_memory.json` (este último con **un episodio semilla**
> `type: plan_retoma`, no con memoria real).
>
> ⚠️ Antes de hacer pull, respalda tu memoria local. Ver
> [Storage / Episodic memory](#storage--episodic-memory).

---

## Storage / Episodic memory

`storage/episodic_memory.json` guarda los episodios de trabajo de Lautaro
(qué se hizo en cada sesión). El repositorio versiona ese archivo **solo con
un episodio semilla** (`type: plan_retoma`), no con memoria real.

### El problema

Como el archivo está versionado, tu copia local y la del repo compiten:

- Si tienes episodios propios y haces `git pull`, git puede **abortar el merge**
  ("local changes would be overwritten") o, si resuelves mal el conflicto,
  **sobrescribir tus episodios**.
- Cada sesión con Lautaro ensucia `git status` con cambios que no quieres commitear.

### La receta (una sola vez por máquina)

**1. Respalda antes de cualquier pull o merge**

```powershell
Copy-Item storage\episodic_memory.json storage\episodic_memory.backup.json
```

O usa el script, que además guarda una copia fechada en `storage/backups/`
y te recuerda el paso siguiente:

```powershell
.\scripts\backup_memory.ps1
```

**2. Dile a git que ignore los cambios locales de ese archivo**

```powershell
git update-index --skip-worktree storage/episodic_memory.json
```

Desde ese momento tus episodios dejan de aparecer en `git status` y `git pull`
ya no pelea con ellos. El flag es **local**: no viaja al repositorio ni afecta
a nadie más.

**3. Para revertirlo** (cuando quieras volver a versionar el archivo)

```powershell
git update-index --no-skip-worktree storage/episodic_memory.json
```

### Cómo verificar

```powershell
git ls-files -v storage/episodic_memory.json
```

| Salida | Significa |
|---|---|
| `H storage/episodic_memory.json` | rastreado normal (pull puede pisarlo) |
| `S storage/episodic_memory.json` | `skip-worktree` activo (protegido) |

> ⚠️ Con `skip-worktree` activo, un `git pull` que traiga cambios en ese archivo
> puede fallar. Si pasa: desactiva el flag, respalda, haz pull, restaura tu
> backup y vuelve a activar el flag.
>
> ⚠️ Nunca borres `storage/episodic_memory.json` sin respaldo previo:
> es memoria real de trabajo y no se puede reconstruir.

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
---

### Integración con bot_trading (mercado cripto)

Lautaro se integra con el proyecto externo `bot_trading` para consultar precio,
indicadores y señal de mercado de criptomonedas de forma segura. [docs/integracion_bot_trading.md]

**Características:**

- Usa un wrapper dedicado `app/tools_trading.py` que llama a
  `bot_trading/consulta_mercado.py` vía `subprocess`, sin importar módulos internos
  del bot.
- Mantiene separación de entornos: Lautaro usa su `.venv` y `bot_trading` el suyo,
  evitando conflictos de dependencias.
- Devuelve un snapshot técnico completo: símbolo, timeframe, precio, señal
  (BUY/SELL/HOLD), RSI, ATR y EMAs, más alertas simples de contexto alcista/bajista.
- Se enruta mediante el carril `tool_analizar_mercado` en `app/tool_registry.py`,
  activado por keywords como `mercado`, `precio`, `btc`, `bitcoin`, `eth`,
  `trading`, `binance`, `cripto`.

**Ejemplo de uso (CLI):**

```bash
python chat.py
# En la sesión:
Analiza el mercado de BTC
```

```text
📊 BTCUSDT — 1m
Precio: $63,768.08
Señal: 🟡 HOLD
RSI: 41.1
ATR: 20.03
EMA rápida: 63,780.64
EMA lenta: 63,796.01

Alertas:
📉 EMA rápida < EMA lenta — contexto bajista
```

> Detalles completos de esta integración (paths, manejo de errores, pruebas
> manuales) están documentados en `docs/integracion_bot_trading.md`.
El agente puede ejecutar estas herramientas sin pasar por el LLM:

- `tool_save_fact(content)` — Guarda hecho en `project_facts.json`
- `tool_create_task(title, priority, notes)` — Crea tarea en `tasks.json`
- `tool_complete_task(task_id)` — Marca tarea como completada
- `tool_update_work_state(field, value)` — Actualiza `work_state.json`
- `tool_set_session_goal(content)` — Guarda objetivo de sesión

Herramientas de solo lectura añadidas después (no escriben nada):

- `tool_plan_retoma(seccion=None)` — Lee `analysis/retoma_plan.json` y devuelve el plan
  completo o una sección concreta. Claves: `validation`, `missing_sections`,
  `recommendations`, `next_actions` (acepta alias en español: `validacion`, `faltantes`,
  `recomendaciones`, `acciones`). Devuelve `ToolResult`; `risk = READ`.

```powershell
# Uso directo, sin pasar por el chat
python -m app.tool_plan_retoma next_actions
python -m app.tool_plan_retoma            # plan completo
```

  Carril registrado en `tool_registry.TOOLS["tool_plan_retoma"]` (`risk = READ`).
  Frases que lo activan: *"plan de retoma"*, *"acciones del plan"*,
  *"recomendaciones del plan"*, *"retomar el proyecto"*, *"auditoría de documentación"*.
  No se usan "plan" ni "tareas" sueltos para no robarle consultas a
  `memory:work_state` ni a `memory:tasks`.

- `tool_analizar_mercado(texto)` — Consulta mercado vía `bot_trading`. Ver sección
  [Integración con bot_trading](#integración-con-bot_trading); `risk = SYSTEM`.

---

## Integración con bot_trading

Lautaro puede consultar mercado de criptomonedas delegando en **`bot_trading`**, un
proyecto externo con su propio repositorio y su propio `.venv`. La decisión completa
(alternativas, riesgos y mitigaciones) está en
[ADR-010](docs/adr/ADR-010-integracion-bot_trading.md).

> **Estado:** el código de la integración (`app/tools_trading.py`, carril
> `tool_analizar_mercado`) vive hoy en la rama `feat/integracion-bot-trading`.
> Esta sección y ADR-010 documentan esa decisión desde `feat/perplexity-sync`.

### Qué hace

`tool_analizar_mercado(texto)` devuelve precio, señal (BUY/SELL/HOLD) e indicadores
(RSI, ATR, EMA rápida y lenta) del símbolo detectado, más alertas simples
(sobreventa/sobrecompra, cruce de EMAs).

### Cómo se comunican

```text
Usuario → router.py → tool_registry.py → app/tools_trading.py
                                              ↓ subprocess (timeout 15s)
                          bot_trading/.venv/Scripts/python.exe
                          consulta_mercado.py --symbol BTCUSDT --modo full
                                              ↓ JSON por stdout
                              app/tools_trading.py → ToolResult → respuesta
```

| Aspecto | Valor |
|---|---|
| Mecanismo | `subprocess` (sin imports cruzados entre proyectos) |
| Contrato | una línea JSON por `stdout` |
| Timeout | 15 s duro |
| Entorno | copia de `os.environ` + `PYTHONUTF8=1`, `cwd` = carpeta del bot |
| Nivel de riesgo | `RiskLevel.SYSTEM` (accede a recursos externos) |
| Alcance | **solo lectura de mercado — no ejecuta órdenes** |
| Símbolos | BTC, ETH, BNB, SOL, XRP, ADA, DOGE (`btc` → `BTCUSDT`; fallback `BTCUSDT`) |

### Ejemplos

```text
Tú: Analiza el mercado de BTC
Agente: 📊 BTCUSDT — 1m
        Precio: $63,120.45
        Señal: 🟡 HOLD
        RSI: 48.3 · ATR: 112.40 · EMA rápida/lenta
        Alertas: 📈 EMA rápida > EMA lenta — contexto alcista
```

### Riesgos y mitigaciones (resumen)

| Riesgo | Mitigación |
|---|---|
| Binance caído / sin internet | El bot cae a su caché local y la respuesta se marca `[caché]` |
| El bot se cuelga | Timeout de 15 s → `error_code="TIMEOUT"`, Lautaro sigue vivo |
| JSON inválido o stdout sucio | Se toma la última línea `{...}`; si falla → `INVALID_JSON` |
| Bot o script ausente | `BOT_NOT_FOUND` / `SCRIPT_NOT_FOUND` con mensaje claro |
| Ejecución no autorizada de órdenes | La tool solo consulta; `dispatch_tool()` rechaza `SYSTEM` sin habilitación explícita |
| Fuga de claves de Binance | Las claves viven en el `.env` de `bot_trading`; Lautaro no las lee ni las loguea |

Ningún fallo del bot lanza excepción hacia Lautaro: todo se traduce a
`ToolResult(ok=False, error_code=...)`.

### Verificación rápida

```powershell
# 1. El bot responde por sí solo (dentro de bot_trading)
python consulta_mercado.py --symbol BTCUSDT --modo full

# 2. El wrapper traduce bien (dentro de mi-agente)
python -c "from app.tools_trading import tool_analizar_mercado; r = tool_analizar_mercado('btc'); print(r['ok'], r.get('error_code')); print(r['message'])"
```

Esperado: `ok=True` y un bloque `📊 BTCUSDT`. Si el bot no está disponible,
`ok=False` con un `error_code` legible — nunca un traceback.

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
| `BOT_TRADING_PATH` | Solo trading | Carpeta raíz de **`bot_trading`**. Default en `app/config.py`; sobrescribible por `.env` |
| `BOT_TRADING_PYTHON` | No | Intérprete del bot. Default: `<BOT_TRADING_PATH>/.venv/Scripts/python.exe` |
| `BOT_TRADING_SCRIPT` | No | Script a ejecutar. Default: `<BOT_TRADING_PATH>/consulta_mercado.py` |
| `BOT_TRADING_TIMEOUT` | No | Timeout duro del subprocess en segundos (default: `15`) |
| `BINANCE_API_KEY` | Solo trading | Clave de API de Binance — vive en el `.env` de **`bot_trading`**, no en este repo |
| `BINANCE_API_SECRET` | Solo trading | Secreto de API de Binance — ídem, nunca en `mi-agente` |

Plantilla lista para copiar: [`.env.example`](.env.example) → `Copy-Item .env.example .env`.
El `.env` real está en `.gitignore`; la plantilla no lleva secretos.

> ⚠️ Las claves de Binance **no se configuran en `mi-agente`**. El subprocess hereda el
> entorno del sistema y el bot lee su propio `.env`. Lautaro nunca lee ni loguea esas claves.

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
| [ADR-009](docs/adr/ADR-009-perplexity-sync.md) | Sincronización de documentación (feat/perplexity-sync) |
| [ADR-010](docs/adr/ADR-010-integracion-bot_trading.md) | Integración de bot_trading como tool externa (subprocess + JSON) |
| [Plan de retoma](analysis/retoma_plan.json) | Auditoría de documentación y próximas acciones (leíble con `tool_plan_retoma`) |
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
✅ Integración `bot_trading` como tool externa (subprocess + JSON) — documentada en ADR-010  
✅ Plan de retoma versionado (`analysis/retoma_plan.json`) + `tool_plan_retoma`  

🔭 Próximo (consolidación antes de expandir):

1. Mover rutas y timeout de `tools_trading.py` a `config.py` / `.env` (hoy son rutas absolutas de Windows)
2. Exponer la antigüedad del dato cuando la respuesta viene de caché
3. Métricas del carril `tool_analizar_mercado` (latencia + tasa de error)
4. Definir el contrato de confirmación humana **antes** de cualquier tool que opere en el mercado
5. Actualizar `docs/vision-agente.md` con el estado post-integración (ver `analysis/retoma_plan.json`)

---

## Autor

**Jose Torres** — [@Jose-TorresCL](https://github.com/Jose-TorresCL)