"""logger.py — Logging persistente a archivo rotativo.

Uso:
    from app.logger import get_logger
    log = get_logger(__name__)
    log.info("Mensaje")
    log.warning("Advertencia")
    log.error("Error", exc_info=True)   # incluye traceback

Archivos generados en storage/logs/:
    lautaro.log          ← activo (hoy)
    lautaro.log.1        ← ayer
    lautaro.log.2        ← anteayer
    (hasta 7 archivos, 1 MB máximo cada uno)

El logger también sigue mostrando mensajes en consola
(StreamHandler) para no romper la experiencia actual.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_DIR = Path("storage/logs")
_LOG_FILE = _LOG_DIR / "lautaro.log"
_MAX_BYTES = 1 * 1024 * 1024   # 1 MB por archivo
_BACKUP_COUNT = 7               # guarda hasta 7 archivos históricos
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_initialized = False


def _setup_root_logger() -> None:
    """Configura el root logger la primera vez que se llama."""
    global _initialized
    if _initialized:
        return

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()   # root logger: captura todo
    root.setLevel(logging.DEBUG)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # ── Handler 1: archivo rotativo ──────────────────────────────────
    file_handler = RotatingFileHandler(
        filename=_LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # ── Handler 2: consola (igual que antes) ───────────────────────
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)   # en consola: solo INFO y superior
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """Retorna un logger con el nombre dado, inicializando el sistema si es necesario."""
    _setup_root_logger()
    return logging.getLogger(name)
