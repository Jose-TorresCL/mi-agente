from __future__ import annotations
import json
import os
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler,
    CommandHandler, filters, ContextTypes,
)

from app.chat_core import build_memory, handle_query
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from app.config import CHROMA_DIR, OLLAMA_URL
from app.logger import get_logger

load_dotenv()
TOKEN       = os.getenv("TELEGRAM_TOKEN")
EMBED_MODEL = "nomic-embed-text"
log         = get_logger(__name__)

# ─────────────────────────────────────────────
# Tipo explícito de sesión por usuario
# ─────────────────────────────────────────────

class UserSession(TypedDict):
    history: list   # LangChain messages (HumanMessage / AIMessage)

SESSIONS_FILE = Path("storage/telegram_sessions.json")


def _load_sessions() -> dict[int, UserSession]:
    """Carga sesiones desde disco. Devuelve dict vacío si no existe.

    Solo persiste qué usuarios tienen sesión activa.
    El historial en RAM se reconstruye desde storage/memory.json
    (mismo origen que la CLI) vía build_memory().
    """
    if not SESSIONS_FILE.exists():
        return {}
    try:
        raw: dict = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
        return {int(uid): {"history": build_memory()} for uid in raw}
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
    user_id   = update.effective_user.id
    user_text = update.message.text.strip()

    if not user_text:
        return

    # Crear sesión nueva si es el primer mensaje
    if user_id not in sessions:
        sessions[user_id] = {"history": build_memory()}
        _persist_sessions(sessions)

    # Avisar que está procesando (Ollama puede tardar)
    await update.message.reply_text("⏳ Pensando...")

    try:
        answer, source_docs = handle_query(
            user_text, vector_db, sessions[user_id]["history"]
        )
        await update.message.reply_text(answer)

        # Mostrar fuentes si las hay
        if source_docs:
            fuentes = "\n".join(
                f"• {doc.metadata.get('source', 'doc')}"
                for doc in source_docs[:3]
            )
            await update.message.reply_text(f"📄 Fuentes:\n{fuentes}")

    except Exception as e:
        log.error("Error en handle_message: %s", e)
        await update.message.reply_text("❌ Hubo un error procesando tu mensaje.")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reset — borra el historial de la sesión."""
    user_id = update.effective_user.id
    sessions[user_id] = {"history": build_memory()}
    await update.message.reply_text("🔄 Historial borrado. Empezamos de nuevo.")


def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_TOKEN no encontrado en .env")

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("reset", reset))

    print("🤖 Lautaro bot arrancado. Esperando mensajes...")
    app.run_polling()


if __name__ == "__main__":
    main()
