"""logger.py — Logging persistente a archivo rotativo."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_DIR = Path("storage/logs")
_LOG_FILE = _LOG_DIR / "lautaro.log"
_MAX_BYTES = 1 * 1024 * 1024
_BACKUP_COUNT = 7
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_CONSOLE_LOG_LEVEL = os.getenv("LAUTARO_CONSOLE_LOG_LEVEL", "WARNING").upper()

_LOGGER_NAME = "lautaro"
_initialized = False


class _MaxLevelFilter(logging.Filter):
    def __init__(self, max_level: int) -> None:
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


def _setup_root_logger() -> None:
    global _initialized
    if _initialized:
        return

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        _initialized = True
        return

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        filename=_LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(getattr(logging, _CONSOLE_LOG_LEVEL, logging.WARNING))
    stdout_handler.addFilter(_MaxLevelFilter(logging.WARNING))
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    _setup_root_logger()

    if name.startswith(f"{_LOGGER_NAME}."):
        return logging.getLogger(name)

    if name == _LOGGER_NAME:
        return logging.getLogger(name)

    return logging.getLogger(f"{_LOGGER_NAME}.{name}")