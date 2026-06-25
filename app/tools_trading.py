"""Wrapper de integración con bot_trading — via subprocess.

Este módulo es el único punto de contacto entre Lautaro y bot_trading.
No importa ningún módulo del bot directamente — usa subprocess para
aislarlo y evitar conflictos de dependencias.

Arquitectura:
  Lautaro (mi-agente/.venv)  ←→  tools_trading.py
        ↓ subprocess
  bot_trading/.venv/python.exe  →  bot_trading/consulta_mercado.py
        ↓ JSON stdout
  tools_trading.py  →  ToolResult para Lautaro

Garantías:
  - Nunca crashea Lautaro: toda excepción es capturada y mapeada a ToolResult(ok=False).
  - Timeout duro de 15 segundos: si Binance no responde, falla rápido.
  - Stderr del bot mapeado a error_code, no ignorado.
  - Fallback: si Binance falla, consulta_mercado.py intenta leer caché local.

Path de configuración:
  BOT_DIR    = C:\\Users\\lenovo\\Proyectos\\bot_trading
  PYTHON_BOT = BOT_DIR\\.venv\\Scripts\\python.exe
  SCRIPT     = BOT_DIR\\consulta_mercado.py
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from app.logger import get_logger
from app.schemas import ToolResult

log = get_logger(__name__)

# ──────────────────────────────────────────────
BOT_DIR    = Path(r"C:\Users\lenovo\Proyectos\bot_trading")
PYTHON_BOT = BOT_DIR / ".venv" / "Scripts" / "python.exe"
SCRIPT     = BOT_DIR / "consulta_mercado.py"
TIMEOUT    = 15   # segundos
# ──────────────────────────────────────────────

_SYMBOL_MAP: dict[str, str] = {
    "btc":     "BTCUSDT",
    "bitcoin": "BTCUSDT",
    "eth":     "ETHUSDT",
    "ethereum": "ETHUSDT",
    "bnb":     "BNBUSDT",
    "sol":     "SOLUSDT",
    "solana":  "SOLUSDT",
    "xrp":     "XRPUSDT",
    "ada":     "ADAUSDT",
    "doge":    "DOGEUSDT",
}


def _normalizar_simbolo(texto: str) -> str:
    lower = texto.strip().lower()
    if lower in _SYMBOL_MAP:
        return _SYMBOL_MAP[lower]
    upper = texto.strip().upper()
    if upper.isalpha() and len(upper) <= 10:
        if not upper.endswith("USDT") and not upper.endswith("BTC"):
            return upper + "USDT"
        return upper
    return "BTCUSDT"


def _detectar_alertas(ind: dict) -> list[str]:
    """Detecta condiciones extremas y retorna lista de alertas."""
    alertas = []
    rsi      = ind.get("rsi", 0)
    ema_fast = ind.get("ema_fast", 0)
    ema_slow = ind.get("ema_slow", 0)

    if rsi and rsi < 20:
        alertas.append(f"⚠️  RSI {rsi:.1f} — SOBREVENTA EXTREMA (posible rebote)")
    elif rsi and rsi > 80:
        alertas.append(f"⚠️  RSI {rsi:.1f} — SOBRECOMPRA EXTREMA (posible corrección)")

    if ema_fast and ema_slow and ema_fast > 0 and ema_slow > 0:
        diff_pct = abs(ema_fast - ema_slow) / ema_slow * 100
        if ema_fast < ema_slow:
            alertas.append("📉 EMA rápida < EMA lenta — contexto bajista")
        else:
            alertas.append("📈 EMA rápida > EMA lenta — contexto alcista")
        if diff_pct > 0.3:
            alertas.append(f"   Divergencia EMAs: {diff_pct:.2f}% — tendencia acentuada")

    return alertas


def _llamar_bot_trading(symbol: str = "BTCUSDT", modo: str = "full") -> ToolResult:
    """Llama a consulta_mercado.py vía subprocess y devuelve ToolResult.

    El subprocess hereda os.environ completo para que Binance pueda
    conectarse (PATH, variables de red, proxies, etc.).
    Solo se sobreescribe PYTHONUTF8=1 para forzar UTF-8 en Windows.
    """
    if not PYTHON_BOT.exists():
        log.warning("[tools_trading] Python del bot no encontrado: %s", PYTHON_BOT)
        return ToolResult(
            ok=False,
            message="⚠️  El bot de trading no está disponible en este momento.",
            error_code="BOT_NOT_FOUND",
            tool_name="tool_analizar_mercado",
        )
    if not SCRIPT.exists():
        log.warning("[tools_trading] Script de consulta no encontrado: %s", SCRIPT)
        return ToolResult(
            ok=False,
            message="⚠️  El script de consulta del bot no existe todavía.",
            error_code="SCRIPT_NOT_FOUND",
            tool_name="tool_analizar_mercado",
        )

    # Heredar entorno completo del sistema + forzar UTF-8
    # Sin esto, Binance falla desde subprocess (sin PATH ni variables de red)
    subprocess_env = os.environ.copy()
    subprocess_env["PYTHONUTF8"] = "1"

    try:
        result = subprocess.run(
            [str(PYTHON_BOT), str(SCRIPT), "--symbol", symbol, "--modo", modo],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            cwd=str(BOT_DIR),
            env=subprocess_env,
        )
    except subprocess.TimeoutExpired:
        log.warning("[tools_trading] Timeout (%ds) consultando %s", TIMEOUT, symbol)
        return ToolResult(
            ok=False,
            message=f"⚠️  El bot no respondió en {TIMEOUT}s.",
            error_code="TIMEOUT",
            tool_name="tool_analizar_mercado",
        )
    except Exception as exc:
        log.error("[tools_trading] Error inesperado en subprocess: %s", exc)
        return ToolResult(
            ok=False,
            message=f"⚠️  Error al llamar al bot: {exc}",
            error_code="SUBPROCESS_ERROR",
            tool_name="tool_analizar_mercado",
        )

    if result.returncode != 0:
        stderr = result.stderr.strip()[:300] if result.stderr else "(sin detalle)"
        log.warning("[tools_trading] Script terminó con código %d: %s", result.returncode, stderr)
        return ToolResult(
            ok=False,
            message=f"⚠️  El bot encontró un error al consultar {symbol}.",
            error_code="SCRIPT_ERROR",
            data={"stderr": stderr, "returncode": result.returncode},
            tool_name="tool_analizar_mercado",
        )

    stdout = result.stdout.strip()
    if not stdout:
        return ToolResult(
            ok=False,
            message="⚠️  El bot no devolvió datos.",
            error_code="EMPTY_OUTPUT",
            tool_name="tool_analizar_mercado",
        )

    try:
        json_line = ""
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                json_line = line
                break
        if not json_line:
            raise ValueError("No se encontró JSON en stdout")
        data = json.loads(json_line)
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("[tools_trading] JSON inválido en stdout: %s", exc)
        return ToolResult(
            ok=False,
            message="⚠️  El bot respondió pero el formato no es válido.",
            error_code="INVALID_JSON",
            data={"raw": stdout[:200]},
            tool_name="tool_analizar_mercado",
        )

    log.info(
        "[tools_trading] Consulta exitosa: %s precio=%.2f senal=%s fuente=%s",
        data.get("symbol", symbol),
        data.get("price", 0),
        data.get("signal", "?"),
        data.get("source", "?"),
    )

    return ToolResult(
        ok=True,
        message=_formatear_respuesta(data),
        data=data,
        tool_name="tool_analizar_mercado",
    )


def _formatear_respuesta(data: dict) -> str:
    """Convierte el dict JSON del bot en texto estructurado.

    Incluye snapshot de precio/señal/indicadores y bloque de alertas
    si hay condiciones extremas (opción 4).
    """
    if not data.get("ok"):
        return f"⚠️  {data.get('error', 'Error desconocido en el bot')}"

    symbol  = data.get("symbol", "?")
    price   = data.get("price", 0)
    signal  = data.get("signal", "?").upper()
    source  = data.get("source", "live")
    tf      = data.get("timeframe", "1m")
    ind     = data.get("indicators", {})

    signal_icon = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(signal, "ℹ️ ")
    source_tag  = " [caché]" if source == "cache" else ""

    lines = [
        f"📊 **{symbol}** — {tf}{source_tag}",
        f"  Precio: **${price:,.2f}**",
        f"  Señal:  {signal_icon} {signal}",
    ]
    if ind:
        if "rsi" in ind:      lines.append(f"  RSI:    {ind['rsi']:.1f}")
        if "atr" in ind:      lines.append(f"  ATR:    {ind['atr']:.2f}")
        if "ema_fast" in ind: lines.append(f"  EMA rápida: {ind['ema_fast']:,.2f}")
        if "ema_slow" in ind: lines.append(f"  EMA lenta:  {ind['ema_slow']:,.2f}")

    # Alertas de condiciones extremas (opción 4)
    alertas = _detectar_alertas(ind)
    if alertas:
        lines.append("")
        lines.append("─" * 36)
        for alerta in alertas:
            lines.append(alerta)

    return "\n".join(lines)
