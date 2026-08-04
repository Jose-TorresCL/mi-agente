# ADR-010 — Integración de bot_trading como tool externa (subprocess + JSON)

**Estado:** Aceptado
**Fecha:** 2026-08-03
**Ramas:** implementación en `feat/integracion-bot-trading` — documentación en `feat/perplexity-sync`
**Autor:** Jose-TorresCL

---

## Contexto

`bot_trading` es un proyecto **separado** (otro repositorio, otro `.venv`) que consulta
precio, indicadores (RSI, ATR, EMA rápida/lenta) y señal de mercado de criptomonedas
usando la API de Binance.

Lautaro (`mi-agente`) necesita responder consultas como:

- "Analiza el mercado de BTC"
- "Qué precio tiene ETH"
- "Dame la señal de BTCUSDT"

El problema: Lautaro es un agente **local primero** (Ollama + Chroma, sin APIs externas),
mientras que `bot_trading` depende de red, claves de API y un stack de dependencias propio
(`python-binance`, `pandas`, `ta`). Importar `bot_trading` dentro del proceso de Lautaro
mezclaría ambos mundos: conflictos de versiones, imports cruzados entre repos y un fallo
de red del bot capaz de tumbar el asistente completo.

Hasta este ADR, el código de la integración existía (`app/tools_trading.py`,
`tool_analizar_mercado`, `RiskLevel.SYSTEM`) **sin ninguna decisión de arquitectura
documentada** — exactamente el riesgo de "documentación desincronizada" que ADR-009
declaró como inaceptable.

---

## Decisión

Integrar `bot_trading` como **tool externa aislada por proceso**, con dos reglas duras:

1. **Frontera = `subprocess`.** Lautaro nunca importa módulos de `bot_trading`.
   Ejecuta el intérprete del bot con su propio script de consulta.
2. **Contrato = JSON por stdout.** El bot imprime una línea JSON; Lautaro la parsea
   y la traduce a `ToolResult`. Nada más cruza la frontera.

```text
Usuario
  ↓
router.py            (keywords: mercado, precio, btc, eth, señal, indicadores…)
  ↓
tool_registry.py     (carril tool_analizar_mercado — risk = RiskLevel.SYSTEM)
  ↓
app/tools_trading.py (único punto de contacto con el bot)
  ↓ subprocess (timeout 15s, cwd=BOT_DIR, PYTHONUTF8=1)
bot_trading/.venv/Scripts/python.exe  consulta_mercado.py --symbol BTCUSDT --modo full
  ↓ JSON por stdout
app/tools_trading.py → ToolResult(ok, message, data, error_code)
  ↓
intelligence.py → respuesta al usuario
```

### Parámetros de la decisión

| Parámetro | Valor actual | Dónde vive |
|---|---|---|
| Intérprete del bot | `C:\Users\lenovo\Proyectos\bot_trading\.venv\Scripts\python.exe` | `tools_trading.PYTHON_BOT` |
| Script invocado | `consulta_mercado.py --symbol <TICKER> --modo full` | `tools_trading.SCRIPT` |
| Timeout duro | 15 s | `tools_trading.TIMEOUT` |
| Entorno | copia de `os.environ` + `PYTHONUTF8=1` | `_llamar_bot_trading()` |
| Nivel de riesgo | `RiskLevel.SYSTEM` | `tool_registry.TOOLS` |
| Símbolos soportados | BTC, ETH, BNB, SOL, XRP, ADA, DOGE (+ normalización `xxx` → `XXXUSDT`) | `_SYMBOL_MAP` |
| Alcance | **solo lectura de mercado** — no ejecuta órdenes | por diseño |

### Reparto de responsabilidades

- Lautaro decide **cuándo** consultar mercado (routing).
- `bot_trading` decide **cómo** obtener precio, indicadores y señal.
- `tools_trading.py` **traduce** la respuesta externa al contrato interno (`ToolResult`).

---

## Alternativas descartadas

### A. Import directo (`from bot_trading import ...`)
Descartado. Obliga a fusionar los dos `.venv` y a versionar dependencias de trading
dentro de `mi-agente/requirements.txt`. Además, una excepción no capturada del bot
(o un `pandas` incompatible) rompería el arranque de Lautaro.

### B. Servicio HTTP local (FastAPI en `bot_trading`)
Descartado **por ahora**, no por siempre. Es la evolución natural si aparece un cuello
de botella real (varias consultas por minuto, o necesidad de streaming). Hoy agrega:
proceso extra que hay que levantar y monitorear, puerto, manejo de estado y un modo de
fallo nuevo ("servicio caído") que `subprocess` no tiene. No se justifica para 1–2
consultas por sesión.

### C. Copiar la lógica de Binance dentro de `mi-agente`
Descartado. Duplica código con dos dueños, obliga a mantener claves de Binance dentro
del repo del asistente y rompe el principio de un solo lugar por responsabilidad.

### D. Base de datos / archivo compartido entre proyectos
Descartado como mecanismo principal. Acopla ambos proyectos a un esquema de archivo
y no permite consultas bajo demanda (solo lo último que el bot haya escrito).
Se conserva únicamente como **caché de respaldo** dentro de `bot_trading`.

---

## Riesgos y mitigaciones

| # | Riesgo | Impacto | Mitigación implementada | Pendiente |
|---|---|---|---|---|
| R1 | Binance no responde / sin internet | Consulta falla | El bot cae a su caché local (`last_market_data.json`) y marca `source: "cache"`, que Lautaro muestra como `[caché]` | Mostrar antigüedad del dato (edad en minutos) |
| R2 | El bot se cuelga | Lautaro bloqueado | `timeout=15s` duro; devuelve `error_code="TIMEOUT"` | Métrica de latencia por consulta de mercado |
| R3 | Datos stale presentados como frescos | Decisión mal informada | Etiqueta `[caché]` en el mensaje | Umbral de "demasiado viejo" → abstención |
| R4 | Bot ausente o ruta cambiada | Error opaco | `BOT_NOT_FOUND` / `SCRIPT_NOT_FOUND` con mensaje claro | Mover rutas a `config.py` / `.env` (hoy están hardcodeadas) |
| R5 | JSON inválido o stdout sucio | Crash de parseo | `_extraer_json_de_stdout()` toma la última línea `{...}`; si falla → `INVALID_JSON` con `raw` truncado a 500 chars | — |
| R6 | Excepción del bot | Crash de Lautaro | Todo capturado → `SCRIPT_ERROR` con `stderr` truncado y `returncode` | — |
| R7 | **Ejecución no autorizada de órdenes** | Pérdida de dinero real | La tool solo consulta. Está clasificada `RiskLevel.SYSTEM`, y `dispatch_tool()` rechaza `SYSTEM` salvo habilitación explícita | Confirmación humana obligatoria antes de cualquier tool que opere |
| R8 | Fuga de claves de Binance | Compromiso de cuenta | Las claves viven en el `.env` de `bot_trading`, nunca en `mi-agente`; el subprocess hereda el entorno pero Lautaro no las lee ni loggea | Verificar que ningún log imprima el entorno |
| R9 | Alucinación sobre datos de mercado | Respuesta falsa | Si el LLM no interpreta bien la salida, `intelligence.py` hace fallback al mensaje estructurado de la tool | Evaluar `fidelity_check` en modo `numeric` para este carril |

### Sobre `RiskLevel.SYSTEM`

`SYSTEM` significa "accede a recursos externos al agente". Es el primer caso real del
proyecto. La regla se mantiene: **ninguna tool `SYSTEM` con efectos irreversibles se
habilita sin confirmación humana explícita**. Hoy `tool_analizar_mercado` es lectura pura,
por eso puede convivir con la regla; una futura `tool_ejecutar_orden` no podría.

---

## Consecuencias

### Positivas
- Los dos proyectos evolucionan por separado; ninguna dependencia de trading entra en
  `mi-agente/requirements.txt`.
- Un fallo del bot degrada la respuesta, no el asistente (`ToolResult(ok=False)`).
- El contrato JSON es inspeccionable a mano, sin levantar Lautaro:
  `python consulta_mercado.py --symbol BTCUSDT --modo full`.
- Queda un límite explícito entre "razonamiento local" (Ollama/Chroma) y "datos externos"
  (Binance vía bot), sin romper el principio *local primero* del proyecto.

### Negativas / costos aceptados
- Overhead de arranque de proceso e intérprete (~1–3 s) en cada consulta.
- Rutas absolutas de Windows hardcodeadas: el repo no es portable en este punto (R4).
- La integración no tiene test automatizado todavía; se valida a mano (ver abajo).
- El JSON de mercado no se persiste en la memoria de Lautaro: cada consulta es efímera.

---

## Cómo validar (batería manual mínima)

| Caso | Cómo provocarlo | Salida esperada |
|---|---|---|
| Camino feliz | "Analiza el mercado de BTC" | Bloque `📊 BTCUSDT — 1m`, precio, señal, RSI/ATR/EMAs |
| Normalización | "precio de eth" | Consulta `ETHUSDT`, no `BTCUSDT` |
| Símbolo desconocido | "analiza el mercado de zzz" | Fallback a `BTCUSDT` sin crash |
| Bot ausente | renombrar temporalmente `consulta_mercado.py` | `⚠️ El script de consulta del bot no existe todavía.` (`SCRIPT_NOT_FOUND`) |
| Sin internet | desactivar Wi-Fi | Respuesta con etiqueta `[caché]` o error controlado |
| Aislamiento | ejecutar toda la batería seguida | Lautaro sigue vivo y responde consultas RAG normales |

Prueba directa del wrapper, sin pasar por el chat:

```powershell
python -c "from app.tools_trading import tool_analizar_mercado; r = tool_analizar_mercado('btc'); print(r['ok'], r.get('error_code')); print(r['message'])"
```

---

## Próximos pasos (post-integración)

1. Mover `BOT_DIR`, `PYTHON_BOT`, `SCRIPT` y `TIMEOUT` a `app/config.py` o `.env` (cierra R4).
2. Exponer la edad del dato cuando `source == "cache"` (cierra R3).
3. Registrar métrica de latencia y tasa de error del carril `tool_analizar_mercado`.
4. Definir el contrato de confirmación humana **antes** de escribir cualquier tool que opere.
5. Test con `subprocess` mockeado: camino feliz, timeout e `INVALID_JSON`.

> Regla de alcance: mientras no existan 1–4, `bot_trading` es **fuente de datos**,
> no ejecutor de operaciones.

---

## Referencias

- `app/tools_trading.py` — wrapper de la integración
- `app/tool_registry.py` — carril y `RiskLevel.SYSTEM`
- `data/docs/proyecto/integracion_bot_trading.md` — guía operativa
- `data/docs/proyecto/roles_lautaro_bot_trading.md` — reparto de roles
- ADR-005 — carriles de decisión en `intelligence.py`
- ADR-009 — regla de documentación sincronizada
- `analysis/retoma_plan.json` — auditoría que originó este ADR
