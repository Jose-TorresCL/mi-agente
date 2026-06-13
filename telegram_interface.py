"""Interfaz de Telegram para Lautaro — gateway de entrada de mensajes.

Responsabilidad:
  Recibir mensajes de Telegram, mantener sesiones aisladas por usuario
  y delegarlos a handle_turn() (app/chat_core.py).
  No contiene lógica de negocio — solo transporte y gestión de sesión.

Variables de entorno requeridas:
  TELEGRAM_TOKEN  — token del bot obtenido desde @BotFather en Telegram.
                    Formato: '123456789:AABBccDDeeFF...'  (nunca hardcodeado).
                    Definir en el archivo .env de la raíz del proyecto.
                    Sin este token el arranque falla con error al construir
                    la Application de python-telegram-bot.

Aislamiento de sesiones:
  Cada Telegram user_id tiene su propio historial en RAM (lista LangChain
  messages). Los historiales NO se comparten entre usuarios ni se persisten
  entre reinicios del proceso (solo se guarda qué IDs tienen sesión activa
  en storage/telegram_sessions.json — sin los mensajes).
  Esto garantiza que dos usuarios no leen el contexto del otro.
  Ver ADR-002 para la decisión de diseño de memoria por sesión.

Flujo de un mensaje:
  1. Telegram → handle_message() recibe Update.
  2. Si es primer mensaje del usuario → crear sesión + inyectar briefing una vez.
  3. handle_turn(user_text, history, vectordb, channel="telegram") → (response, should_exit).
  4. Responder al usuario.
  5. Persistir el ID de sesión en storage/telegram_sessions.json.

Comandos disponibles:
  /start  — bienvenida y presentación de capacidades.
  /reset  — borra el historial en RAM del usuario actual.

Prerequisitos para arrancar:
  - Ollama corriendo en localhost:11434 con el modelo configurado en app/config.py.
  - ChromaDB indexado (ejecutar python indexacion.py si es la primera vez).
  - .env con TELEGRAM_TOKEN definido.

Uso:
  python telegram_interface.py
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import TypedDict
from app.memory_manager import get_session_briefing
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler,
    CommandHandler, filters, ContextTypes,
)
from app.chat_core import handle_turn
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.messages import AIMessage
from app.config import CHROMA_DIR, OLLAMA_URL
from app.logger import get_logger

load_dotenv()
TOKEN       = os.getenv("TELEGRAM_TOKEN")
EMBED_MODEL = "nomic-embed-text"
log         = get_logger(__name__)

# ─────────────────────────────────────────────
# Tipo explícito de sesión por usuario
# ─────────────────────────────────────────────

# Un stub inicial con `run_polling` para que `patch("telegram_interface.app.run_polling")`
# no falle al importar el módulo (el `main()` sobrescribe esta variable).
class _AppStub:
    def run_polling(self):
        pass

# Objeto `app` visible en el módulo (será sobrescrito por `main()`).
app = _AppStub()

class UserSession(TypedDict):
    history: list   # LangChain messages (HumanMessage / AIMessage)

SESSIONS_FILE = Path("storage/telegram_sessions.json")


def _load_sessions() -> dict[int, UserSession]:
    """Carga sesiones desde disco. Devuelve dict vacío si no existe.

    Solo persiste qué usuarios tienen sesión activa.
    El historial en RAM es específico de cada usuario y no se reconstruye
    desde storage/memory.json.
    """
    if not SESSIONS_FILE.exists():
        return {}
    try:
        raw: dict = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
        return {int(uid): {"history": []} for uid in raw}
    except Exception as exc:
        log.warning("No se pudo leer telegram_sessions.json: %s", exc)
        return {}


def _persist_sessions(sessions: dict[int, UserSession]) -> None:
    """Guarda qué usuarios tienen sesión activa (sin serializar mensajes LangChain)."""
    try:
        SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {str(uid): True for uid in sessions}
        SESSIONS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        log.warning("No se pudo persistir telegram_sessions.json: %s", exc)


# Cargar sesiones previas al arrancar
sessions: dict[int, UserSession] = _load_sessions()

# Cargar vectorstore una sola vez al arrancar
embeddings = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_URL)
vector_db  = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)


# ─────────────────────────────────────────────
# Handlers
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start — bienvenida para usuarios nuevos."""
    await update.message.reply_text(
        "👋 Hola, soy *Lautaro*, tu asistente de proyecto local.\n\n"
        "Puedo ayudarte con:\n"
        "• 📋 Tus tareas y estado de trabajo\n"
        "• 🧠 Documentación indexada del proyecto\n"
        "• 💾 Guardar hechos y recordar contexto\n"
        "• 🔍 Responder preguntas sobre tus documentos\n\n"
        "Escríbeme lo que necesitas. Usa /reset para borrar el historial.",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja mensajes de texto del usuario en Telegram.

    Lógica:
      1. Si es primer mensaje del usuario: crear sesión + inyectar briefing UNA VEZ.
      2. Procesar el mensaje con handle_turn(channel="telegram").
      3. Responder al usuario.
      4. Si should_exit es True (comando de salida), cerrar sesión en RAM.
    """
    user_id   = update.effective_user.id
    user_text = update.message.text.strip()

    if not user_text:
        return

    # ─ Crear sesión SOLO si es la primera vez ─
    if user_id not in sessions:
        sessions[user_id] = {"history": []}
        _persist_sessions(sessions)
        log.info("Nueva sesión Telegram: user_id=%d", user_id)

        # Inyectar briefing de sesión anterior una sola vez
        briefing = get_session_briefing()
        if briefing:
            sessions[user_id]["history"].append(AIMessage(content=briefing))
            log.info("Briefing inyectado para user_id=%d", user_id)

    history = sessions[user_id]["history"]

    # ─ Procesar con handle_turn ─
    try:
        response, should_exit = handle_turn(
            user_text,
            history,
            vector_db,
            channel="telegram",
        )
    except Exception as exc:
        log.error("Error en handle_turn: %s", exc)
        response    = "Hubo un error procesando tu mensaje. Intenta de nuevo."
        should_exit = False

    # ─ Enviar respuesta ─
    if response and response != "__EXIT__":
        await update.message.reply_text(response, parse_mode="Markdown")

    # ─ Si el usuario pidió salir, limpiar sesión en RAM ─
    if should_exit:
        sessions[user_id]["history"] = []
        _persist_sessions(sessions)
        log.info("Sesión cerrada por comando exit: user_id=%d", user_id)

    _persist_sessions(sessions)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reset — borra el historial en RAM del usuario actual."""
    user_id = update.effective_user.id
    if user_id in sessions:
        sessions[user_id]["history"] = []
    await update.message.reply_text("🔄 Historial borrado. ¡Empezamos de nuevo!")


# ─────────────────────────────────────────────
# Arranque
# ─────────────────────────────────────────────

def main() -> None:
    """Construye la Application de python-telegram-bot y arranca el polling.

    Requiere TELEGRAM_TOKEN en el entorno (.env o variable de sistema).
    Si TOKEN es None el arranque fallará con InvalidToken de la librería.
    """
    if not TOKEN:
        raise RuntimeError(
            "TELEGRAM_TOKEN no está definido. "
            "Agrega TELEGRAM_TOKEN=<tu_token> en el archivo .env"
        )

    global app  # sobrescribe el stub inicial
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Lautaro Telegram arrancando (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
