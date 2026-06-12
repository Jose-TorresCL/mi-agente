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
from app.chat_core import handle_query
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.messages import AIMessage
from app.config import CHROMA_DIR, OLLAMA_URL
from app.logger import get_logger
from app.tools import toolresult_to_str

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
      2. Procesar el mensaje con handle_query (usa historial persistente).
      3. Responder y mostrar fuentes si las hay.
    """
    user_id   = update.effective_user.id
    user_text = update.message.text.strip()

    if not user_text:
        return

    # ─ Crear sesión SOLO si es la primera vez ─
    if user_id not in sessions:
        sessions[user_id] = {"history": build_memory()}
        _persist_sessions(sessions)
        
        # Inyectar briefing UNA sola vez al arrancar sesión
        try:
            briefing = get_session_briefing()
            if briefing:
                lines = []
                foco = briefing.get("foco", "").strip()
                goal = briefing.get("session_goal", "").strip()
                state = briefing.get("session_state", "drifting")
                suggestion = briefing.get("suggestion", "").strip()
                
                if foco:
                    lines.append(f"🎯 **Foco:** {foco}")
                if goal:
                    lines.append(f"💡 **Objetivo:** {goal}")
                lines.append(f"📊 **Estado:** {state}")
                if suggestion:
                    lines.append(f"→ {suggestion}")
                
                if lines:
                    briefing_text = "\n".join(lines)
                    sessions[user_id]["history"].insert(
                        0, AIMessage(content=f"[Briefing de arranque]\n{briefing_text}")
                    )
        except Exception as e:
            log.debug("[telegram] Session briefing no disponible: %s", e)

    # ─ Avisar que está procesando (Ollama puede tardar) ─
    await update.message.reply_text("⏳ Pensando...")

    try:
        answer, source_docs = handle_query(
            user_text,
            vector_db,
            sessions[user_id]["history"],
            channel="telegram",
        )

        if answer == "__EXIT__":
            sessions.pop(user_id, None)
            _persist_sessions(sessions)
            await update.message.reply_text(
                "👋 Sesión cerrada. Usa /start para comenzar de nuevo."
            )
            return

        safe_answer = toolresult_to_str(answer)
        await update.message.reply_text(safe_answer)

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
    """/reset — borra el historial de la sesión y muestra briefing nuevo."""
    user_id = update.effective_user.id
    sessions[user_id] = {"history": []}
    _persist_sessions(sessions)
    
    # Inyectar briefing en la sesión nueva
    try:
        briefing = get_session_briefing()
        if briefing:
            lines = []
            foco = briefing.get("foco", "").strip()
            goal = briefing.get("session_goal", "").strip()
            state = briefing.get("session_state", "drifting")
            suggestion = briefing.get("suggestion", "").strip()
            
            if foco:
                lines.append(f"🎯 **Foco:** {foco}")
            if goal:
                lines.append(f"💡 **Objetivo:** {goal}")
            lines.append(f"📊 **Estado:** {state}")
            if suggestion:
                lines.append(f"→ {suggestion}")
            
            if lines:
                briefing_text = "\n".join(lines)
                sessions[user_id]["history"].insert(
                    0, AIMessage(content=f"[Briefing de arranque]\n{briefing_text}")
                )
    except Exception as e:
        log.debug("[telegram] Session briefing en reset no disponible: %s", e)
    
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
