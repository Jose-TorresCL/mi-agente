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
    "signal": "sell",
    "timeframe": "1m",
    "indicators": {
      "rsi": 62.1,
      "atr": 30.2,
      "ema_fast": 62780.1,
      "ema_slow": 62610.4
    },
    "source": "live"
  }

En caso de error:
  {"ok": false, "error": "<descripcion>", "source": "none"}

Módulos y firmas reales confirmadas:
  get_historical_data(symbol, interval, limit, client, ...) — symbol es posicional
  calcular_todos_los_indicadores(df)
  estrategia_compra(indicadores), estrategia_venta(indicadores)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ───────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
DOTENV     = SCRIPT_DIR / ".env"
CACHE_FILE = SCRIPT_DIR / "data" / "last_market_data.json"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(DOTENV)
except ImportError:
    pass


def _emit(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False))
    sys.stdout.flush()


def _cargar_cache(symbol: str) -> dict | None:
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            cache = json.load(f)
        if symbol in cache:
            return cache[symbol]
        if cache:
            return next(iter(cache.values()))
    except Exception:
        pass
    return None


def _guardar_cache(symbol: str, data: dict) -> None:
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
        pass


def _derivar_signal(indicadores: dict) -> str:
    try:
        from src.core.estrategias_bot1 import estrategia_compra, estrategia_venta
    except ImportError:
        return "hold"

    signal = "hold"

    try:
        resultado_compra = estrategia_compra(indicadores)
        if isinstance(resultado_compra, bool) and resultado_compra:
            signal = "buy"
        elif isinstance(resultado_compra, str) and resultado_compra.lower() in ("buy", "compra", "long"):
            signal = "buy"
        elif isinstance(resultado_compra, dict):
            v = resultado_compra.get("decision") or resultado_compra.get("accion") or resultado_compra.get("signal") or ""
            if v is True or str(v).lower() in ("buy", "compra", "long", "true", "1"):
                signal = "buy"
    except Exception:
        pass

    if signal == "hold":
        try:
            resultado_venta = estrategia_venta(indicadores)
            if isinstance(resultado_venta, bool) and resultado_venta:
                signal = "sell"
            elif isinstance(resultado_venta, str) and resultado_venta.lower() in ("sell", "venta", "short"):
                signal = "sell"
            elif isinstance(resultado_venta, dict):
                v = resultado_venta.get("decision") or resultado_venta.get("accion") or resultado_venta.get("signal") or ""
                if v is True or str(v).lower() in ("sell", "venta", "short", "true", "1"):
                    signal = "sell"
        except Exception:
            pass

    return signal


def _consultar_live(symbol: str) -> dict:
    """Conecta a Binance y calcula indicadores.

    Firma real confirmada:
      get_historical_data(symbol, interval, limit, client, ...)
      symbol es el primer parámetro posicional — NO pasar client primero.
    """
    from src.pipeline.conexion_api import connect_to_binance, get_historical_data
    from src.core.gestor_indicadores import calcular_todos_los_indicadores

    client = connect_to_binance()

    # Firma: get_historical_data(symbol, interval, limit, client, ...)
    df = get_historical_data(symbol, "1m", 100, client=client)

    # get_historical_data ya retorna DataFrame normalizado
    if df is None or len(df) < 20:
        raise ValueError(f"Datos insuficientes para {symbol}: {len(df) if df is not None else 0} velas")

    import pandas as pd
    # Asegurar tipos numéricos por si acaso
    for col in ("close", "high", "low", "open", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    resultado_ind = calcular_todos_los_indicadores(df)

    if isinstance(resultado_ind, list) and resultado_ind:
        indicadores = resultado_ind[-1]
    elif isinstance(resultado_ind, dict):
        indicadores = resultado_ind
    else:
        indicadores = {}

    signal = _derivar_signal(indicadores)
    precio_actual = float(df["close"].iloc[-1])

    def _safe(key):
        v = indicadores.get(key) or indicadores.get(key.lower()) or 0
        try:
            return round(float(v), 4)
        except Exception:
            return 0.0

    return {
        "ok":         True,
        "symbol":     symbol,
        "price":      round(precio_actual, 4),
        "signal":     signal,
        "timeframe":  "1m",
        "indicators": {
            "rsi":      _safe("RSI"),
            "atr":      _safe("ATR"),
            "ema_fast": _safe("EMA_fast"),
            "ema_slow": _safe("EMA_slow"),
        },
        "source":     "live",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Consulta de mercado para Lautaro")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--modo", choices=["precio", "indicadores", "full"], default="full")
    args = parser.parse_args()
    symbol = args.symbol.upper().strip()

    if args.modo == "precio":
        try:
            from src.pipeline.conexion_api import connect_to_binance, get_historical_data
            import pandas as pd
            client = connect_to_binance()
            df     = get_historical_data(symbol, "1m", 5, client=client)
            price  = round(float(pd.to_numeric(df["close"]).iloc[-1]), 4)
            _emit({"ok": True, "symbol": symbol, "price": price, "source": "live"})
        except Exception as exc:
            cached = _cargar_cache(symbol)
            if cached:
                cached["source"] = "cache"
                _emit(cached)
            else:
                _emit({"ok": False, "error": str(exc), "source": "none"})
        return

    try:
        data = _consultar_live(symbol)
        _guardar_cache(symbol, data)
        _emit(data)
    except Exception as exc:
        cached = _cargar_cache(symbol)
        if cached:
            cached["source"] = "cache"
            _emit(cached)
        else:
            _emit({"ok": False, "error": str(exc), "source": "none"})


if __name__ == "__main__":
    main()
