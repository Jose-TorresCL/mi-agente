# Integración con bot_trading

> Última actualización: 03/08/2026

## Propósito

Este documento describe cómo Lautaro se integra con el proyecto externo `bot_trading`
para consultar precio, indicadores y señal de mercado de criptomonedas.

La integración está diseñada para mantener aislados ambos entornos Python:
Lautaro no importa módulos internos de `bot_trading` directamente.
En cambio, ejecuta un script externo vía `subprocess` y recibe la respuesta en formato JSON.

## Alcance

Esta integración permite responder consultas como:

- "Analiza el mercado de BTC"
- "Qué precio tiene ETH"
- "Dame la señal de BTCUSDT"

Su objetivo es consultar y resumir información de mercado desde una tool segura
y desacoplada. No está diseñada para ejecutar órdenes ni automatizar operaciones sensibles.

## Arquitectura

```text
Usuario
  ↓
chat.py / telegram_interface.py
  ↓
router.py
  ↓
tool_registry.py
  ↓
tool_analizar_mercado
  ↓
app/tools_trading.py
  ↓ subprocess
bot_trading/.venv/Scripts/python.exe
  ↓
bot_trading/consulta_mercado.py
  ↓ JSON stdout
app/tools_trading.py
  ↓
ToolResult
  ↓
intelligence.py
  ↓
Respuesta al usuario
```

## Principio de aislamiento

La integración usa `subprocess` como frontera entre proyectos.

Esto evita:

- conflictos de dependencias entre `.venv`
- imports cruzados entre repositorios
- acoplamiento fuerte entre Lautaro y la lógica interna de `bot_trading`

Regla de responsabilidad:

- Lautaro decide **cuándo** consultar mercado.
- `bot_trading` decide **cómo** obtener precio, indicadores y señal.
- `tools_trading.py` traduce la respuesta externa al contrato interno de Lautaro.

## Archivos involucrados

### En Lautaro

- `app/tools_trading.py`
  - wrapper principal de integración con `bot_trading`
  - llama al script externo vía `subprocess`
  - controla timeout, parsea JSON y devuelve `ToolResult`

- `app/tool_registry.py`
  - registra `tool_analizar_mercado`
  - expone el carril `tool_analizar_mercado`
  - preserva `ToolResult` estructurado en `dispatch_tool()`

- `app/router.py`
  - detecta consultas de mercado por keywords
  - enruta preguntas como "Analiza el mercado de BTC"

- `app/intelligence.py`
  - usa la tool
  - si el LLM no logra interpretar la salida, hace fallback al formato estructurado

### En bot_trading

- `.venv/Scripts/python.exe`
  - intérprete Python aislado del proyecto `bot_trading`

- `consulta_mercado.py`
  - script ejecutado por Lautaro vía `subprocess`
  - consulta mercado y emite JSON por stdout

## Flujo de ejecución

1. El usuario hace una consulta como:
   - "Analiza el mercado de BTC"

2. `router.py` detecta keywords de mercado y enruta a:
   - `tool_analizar_mercado`

3. `tool_registry.py` llama al handler correspondiente.

4. El handler usa `tool_analizar_mercado(...)`, que termina llamando a:
   - `app/tools_trading.py`

5. `tools_trading.py`:
   - normaliza el símbolo (`btc` → `BTCUSDT`)
   - valida que existan el Python y el script del bot
   - ejecuta el subprocess
   - captura `stdout` y `stderr`
   - detecta errores, timeout o JSON inválido
   - devuelve un `ToolResult`

6. Si todo sale bien, Lautaro muestra:
   - precio
   - señal
   - RSI
   - ATR
   - EMA rápida / lenta
   - alertas simples de contexto

7. Si el LLM no logra generar una interpretación adicional, Lautaro responde igual
   usando el mensaje estructurado de la tool.

## Contrato de respuesta

La tool devuelve un `ToolResult` estructurado.

### Caso exitoso

- `ok=True`
- `message=<texto formateado>`
- `data=<json original del bot>`
- `tool_name="tool_analizar_mercado"`

### Caso fallido

- `ok=False`
- `message=<error amigable>`
- `error_code=<código estable>`
- `tool_name="tool_analizar_mercado"`

Esto garantiza que Lautaro no crashee aunque el bot externo falle.

## Manejo de errores y fallback

La integración contempla estos casos:

- Python del bot no encontrado
- script de consulta no encontrado
- timeout del subprocess
- retorno distinto de cero
- stdout vacío
- JSON inválido
- error interno inesperado

Además:

- `stderr` del bot se mapea a error estructurado
- si el LLM no genera interpretación, Lautaro usa el formato estructurado
- `consulta_mercado.py` puede usar caché local si Binance falla

## Pruebas manuales recomendadas

### 1. Tool aislada

```powershell
python -c "from app.tool_registry import dispatch_tool; r = dispatch_tool('tool_analizar_mercado', 'precio btc'); print(type(r)); print(r['ok']); print(r['message']); print(r.get('tool_name'))"
```

Esperado:

- tipo `dict` (ToolResult tipado)
- `ok=True`
- mensaje con snapshot de mercado
- `tool_name=tool_analizar_mercado`

### 2. Flujo real desde chat

```powershell
python chat.py
```

Pregunta:

```text
Analiza el mercado de BTC
```

Esperado:

- el router enruta a `tool_analizar_mercado`
- `tools_trading.py` loguea consulta exitosa
- Lautaro responde con snapshot técnico aunque el LLM no interprete

### 3. Prueba de degradación sana

Simular alguno de estos casos:

- mover temporalmente el path del script del bot
- cambiar el nombre del Python del bot
- forzar timeout o salida inválida

Esperado:

- Lautaro no crashea
- devuelve `ToolResult(ok=False)` con mensaje entendible

## Decisiones de diseño

### 1. Subprocess en vez de import directo

Se eligió `subprocess` para mantener aislamiento entre proyectos.

Ventajas:
- separa dependencias
- evita conflictos de entorno
- deja una frontera clara entre sistemas

Costo:
- hay que validar paths, timeout y parseo de stdout

### 2. ToolResult como contrato interno

Se decidió conservar `ToolResult` hasta `dispatch_tool()` para no perder:

- `ok`
- `error_code`
- `data`
- `tool_name`

Esto mejora pruebas, métricas y depuración.

### 3. Fallback sin LLM

La tool debe seguir siendo útil aunque el modelo local falle,
esté lento o no logre interpretar la salida.

Por eso la respuesta estructurada de mercado no depende del LLM.

## Límites actuales

Hoy esta integración:

- consulta mercado
- devuelve snapshot técnico
- no ejecuta órdenes
- no modifica balances
- no automatiza operaciones sensibles

Esto es intencional: la prioridad actual es consolidación y seguridad.

## Próximos pasos sugeridos

- resumir esta integración en el `README.md`
- agregar pruebas manuales repetibles para BTC, ETH y error controlado
- revisar si el carril trading necesita una interpretación LLM más corta