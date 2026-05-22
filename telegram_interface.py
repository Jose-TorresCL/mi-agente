from __future__ import annotations
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

from app.chat_core import build_memory, handle_query
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from app.config import CHROMA_DIR, OLLAMA_URL
from app.logger import get_logger

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
EMBED_MODEL = "nomic-embed-text"
log = get_logger(__name__)

# Historial por usuario (en memoria, se reinicia al reiniciar el bot)
sessions: dict = {}

# Cargar vectorstore una sola vez al arrancar
embeddings = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_URL)
vector_db = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text.strip()

    if not user_text:
        return

    # Crear sesión nueva si es el primer mensaje
    if user_id not in sessions:
        sessions[user_id] = build_memory()

    # Avisar que está procesando (Ollama puede tardar)
    await update.message.reply_text("⏳ Pensando...")

    try:
        answer, source_docs = handle_query(user_text, vector_db, sessions[user_id])
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
    """Comando /reset — borra el historial de la sesión."""
    user_id = update.effective_user.id
    sessions[user_id] = build_memory()
    await update.message.reply_text("🔄 Historial borrado. Empezamos de nuevo.")


def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_TOKEN no encontrado en .env")

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("reset", reset))

    print("🤖 Lautaro bot arrancado. Esperando mensajes...")
    app.run_polling()


if __name__ == "__main__":
    main()