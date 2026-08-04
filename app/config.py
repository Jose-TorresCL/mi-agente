"""Configuración central del proyecto mi-agente.

Importar desde aquí en todos los módulos que necesiten estas constantes.
Nunca hardcodear MODEL_NAME, OLLAMA_URL ni MAX_TURNS en otros archivos.

Integración externa (bot_trading)
---------------------------------
La ruta al proyecto `bot_trading` era una ruta absoluta de Windows escrita
dentro de `app/tools_trading.py` (riesgo R4 de ADR-010: el repo no era
portable y mover la carpeta rompía la tool en silencio).

Ahora vive aquí y se puede sobrescribir con variables de entorno:

    BOT_TRADING_PATH      carpeta raíz del proyecto bot_trading
    BOT_TRADING_PYTHON    intérprete a usar (por defecto: <PATH>/.venv/Scripts/python.exe)
    BOT_TRADING_SCRIPT    script a ejecutar  (por defecto: <PATH>/consulta_mercado.py)
    BOT_TRADING_TIMEOUT   timeout duro en segundos (por defecto: 15)

Ver `.env.example`. El valor por defecto de BOT_TRADING_PATH conserva la ruta
que ya funcionaba en la máquina de desarrollo, para no romper el setup actual:
el cambio es reversible y no exige configurar nada para seguir trabajando.

Uso:
    from app.config import BOT_TRADING_PATH, BOT_TRADING_PYTHON, BOT_TRADING_SCRIPT
"""
from __future__ import annotations

import os
from pathlib import Path

# python-dotenv está en requirements.txt, pero el import es opcional:
# si falta, se leen las variables del entorno del sistema igual.
try:  # pragma: no cover — depende del entorno
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

MODEL_NAME  = "llama3.2:latest"
OLLAMA_URL  = "http://localhost:11434"
MAX_TURNS   = 8
CHROMA_DIR  = "storage/chroma"
STORAGE_DIR = "storage"

# ─────────────────────────────────────────────
# Integración con bot_trading (ADR-010)
# ─────────────────────────────────────────────

#: Ruta por defecto — solo se usa si no hay BOT_TRADING_PATH en el entorno.
DEFAULT_BOT_TRADING_PATH = r"C:\Users\lenovo\Proyectos\bot_trading"

BOT_TRADING_PATH: Path = Path(
    os.getenv("BOT_TRADING_PATH") or DEFAULT_BOT_TRADING_PATH
).expanduser()

BOT_TRADING_PYTHON: Path = Path(
    os.getenv("BOT_TRADING_PYTHON")
    or BOT_TRADING_PATH / ".venv" / "Scripts" / "python.exe"
).expanduser()

BOT_TRADING_SCRIPT: Path = Path(
    os.getenv("BOT_TRADING_SCRIPT") or BOT_TRADING_PATH / "consulta_mercado.py"
).expanduser()


def _leer_timeout(valor: str | None, por_defecto: int = 15) -> int:
    """Convierte BOT_TRADING_TIMEOUT a int. Valor inválido → por_defecto."""
    try:
        n = int(str(valor).strip())
        return n if n > 0 else por_defecto
    except (TypeError, ValueError):
        return por_defecto


BOT_TRADING_TIMEOUT: int = _leer_timeout(os.getenv("BOT_TRADING_TIMEOUT"))

# Invariante de configuración: una ruta vacía dejaría a tools_trading.py
# ejecutando "" como comando. Preferimos fallar al importar (temprano y claro)
# que fallar dentro de un subprocess (tarde y opaco).
assert str(BOT_TRADING_PATH).strip(), (
    "BOT_TRADING_PATH está vacío. Define la variable en tu .env "
    "(ver .env.example) o deja el valor por defecto de app/config.py."
)


def bot_trading_disponible() -> bool:
    """True si el intérprete y el script del bot existen en disco.

    Pensado para diagnóstico y para que la tool devuelva un error legible
    (BOT_NOT_FOUND / SCRIPT_NOT_FOUND) en vez de intentar el subprocess.
    No toca red ni ejecuta nada.
    """
    return BOT_TRADING_PYTHON.exists() and BOT_TRADING_SCRIPT.exists()
