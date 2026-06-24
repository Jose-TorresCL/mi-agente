"""Script liviano de consulta de mercado — para subprocess desde Lautaro.

Este script es el único punto de entrada del bot_trading que Lautaro
puede llamar. No ejecuta el ciclo de trading, no abre posiciones,
no modifica ningún estado del bot.

Uso:
  python consulta_mercado.py --symbol BTCUSDT --modo full
  python consulta_mercado.py --symbol ETHUSDT --modo precio

Salida: una línea JSON en stdout con este schema estricto:
  {
    "ok": true,
    "symbol": "BTCUSDT",
    "price": 62814.2,
    "signal": "sell",          # buy | sell | hold
    "timeframe": "1m",
    "indicators": {
      "rsi": 62.1,
      "atr": 30.2,
      "ema_fast": 62780.1,
      "ema_slow": 62610.4
    },
    "source": "live"           # live | cache
  }

En caso de error:
  {"ok": false, "error": "<descripcion>", "source": "none"}

Garantías:
  - Siempre imprime exactamente un JSON en la última línea de stdout.
  - Resuelve .env desde el directorio del script, no desde cwd.
  - Si Binance falla, intenta leer data/last_market_data.json (caché).
  - PYTHONUTF8=1 en el subprocess previene UnicodeError en Windows.

Dependencias (deben estar en bot_trading/.venv):
  python-binance, pandas, pandas-ta, python-dotenv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ───────────────────────────────────────────────
# Resolucín de rutas — siempre desde este archivo, no desde cwd
# ───────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
DOTENV     = SCRIPT_DIR / ".env"
CACHE_FILE = SCRIPT_DIR / "data" / "last_market_data.json"

# Agregar el directorio razíz del bot al path para imports relativos
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Cargar .env antes de cualquier import del bot
try:
    from dotenv import load_dotenv
    load_dotenv(DOTENV)
except ImportError:
    pass  # python-dotenv no instalado, continuar sin .env


def _emit(data: dict) -> None:
    """Imprime el JSON de salida y termina. Única función de output."""
    print(json.dumps(data, ensure_ascii=False))
    sys.stdout.flush()


def _cargar_cache(symbol: str) -> dict | None:
    """Lee data/last_market_data.json y devuelve el último snapshot del símbolo."""
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            cache = json.load(f)
        # El caché puede ser un dict por símbolo o un dict directo
        if symbol in cache:
            return cache[symbol]
        # Si no hay símbolo específico, devolver el primero disponible
        if cache:
            return next(iter(cache.values()))
    except Exception:
        pass
    return None


def _guardar_cache(symbol: str, data: dict) -> None:
    """Escribe el snapshot actual en data/last_market_data.json."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        cache = {}
        if CACHE_FILE.exists():
            with open(CACHE_FILE, encoding="utf-8") as f:
                cache = json.load(f)
        cache[symbol] = data
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # fallo silencioso — el caché es best-effort


def _consultar_live(symbol: str) -> dict:
    """Conecta a Binance, obtiene datos reales y calcula indicadores.

    Importa solo los módulos necesarios del bot (no el ciclo productivo).
    """
    from src.pipeline.conexionapi import connect_to_binance, get_historical_data
    from src.core.estrategias_bot1 import tomar_decision
    from src.core.gestor_indicadores import calcular_indicadores

    client = connect_to_binance()
    raw    = get_historical_data(client, symbol=symbol, interval="1m", limit=100)

    if not raw or len(raw) < 20:
        raise ValueError(f"Datos insuficientes de Binance para {symbol}: {len(raw) if raw else 0} velas")

    import pandas as pd
    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "num_trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ])
    df["close"] = pd.to_numeric(df["close"])
    df["high"]  = pd.to_numeric(df["high"])
    df["low"]   = pd.to_numeric(df["low"])

    indicadores = calcular_indicadores(df)
    decision    = tomar_decision(indicadores)

    precio_actual = float(df["close"].iloc[-1])

    signal = "hold"
    if decision == "buy":
        signal = "buy"
    elif decision == "sell":
        signal = "sell"

    return {
        "ok":         True,
        "symbol":     symbol,
        "price":      round(precio_actual, 4),
        "signal":     signal,
        "timeframe":  "1m",
        "indicators": {
            "rsi":      round(float(indicadores.get("RSI") or 0), 2),
            "atr":      round(float(indicadores.get("ATR") or 0), 4),
            "ema_fast": round(float(indicadores.get("EMA_fast") or 0), 4),
            "ema_slow": round(float(indicadores.get("EMA_slow") or 0), 4),
        },
        "source":     "live",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Consulta de mercado para Lautaro")
    parser.add_argument("--symbol", default="BTCUSDT", help="Ticker Binance (ej. BTCUSDT)")
    parser.add_argument(
        "--modo",
        choices=["precio", "indicadores", "full"],
        default="full",
        help="Nivel de detalle de la consulta",
    )
    args = parser.parse_args()
    symbol = args.symbol.upper().strip()

    # Modo precio: solo el precio actual, sin indicadores (más rápido)
    if args.modo == "precio":
        try:
            from src.pipeline.conexionapi import connect_to_binance, get_historical_data
            client = connect_to_binance()
            raw    = get_historical_data(client, symbol=symbol, interval="1m", limit=5)
            import pandas as pd
            df    = pd.DataFrame(raw, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "num_trades",
                "taker_buy_base", "taker_buy_quote", "ignore",
            ])
            price = round(float(pd.to_numeric(df["close"]).iloc[-1]), 4)
            _emit({"ok": True, "symbol": symbol, "price": price, "source": "live"})
        except Exception as exc:
            cached = _cargar_cache(symbol)
            if cached:
                cached["source"] = "cache"
                _emit(cached)
            else:
                _emit({"ok": False, "error": str(exc), "source": "none"})
        return

    # Modo indicadores / full: precio + indicadores + señal
    try:
        data = _consultar_live(symbol)
        _guardar_cache(symbol, data)   # actualizar caché si todo fue bien
        _emit(data)
    except Exception as exc:
        # Fallback a caché local
        cached = _cargar_cache(symbol)
        if cached:
            cached["source"] = "cache"
            _emit(cached)
        else:
            _emit({"ok": False, "error": str(exc), "source": "none"})


if __name__ == "__main__":
    main()
