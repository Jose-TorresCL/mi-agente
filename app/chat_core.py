from pathlib import Path
from typing import Any
import json

from app.memory_store import (
    load_profile,
    load_project_facts,
    load_tasks,
    load_work_state,
    save_episode,
    load_last_episode,
)
from app.semantic_cache import cache_lookup, cache_save, cache_invalidate, cache_stats
from app.fidelity_check import verify_fidelity, NO_EVIDENCE_MSG
from app.router import route_query, classify_memory_query

from app.tool_registry import TOOLS, dispatch_tool  # B4: despacho centralizado
from app.tools import (
    suggest_next_step,
    extract_task_id,
    parse_work_state_update,
)
from app.logger import get_logger

from langchain_chroma import Chroma
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda

log = get_logger(__name__)

STORAGE_DIR = Path("storage")
CHROMA_DIR = str(STORAGE_DIR / "chroma")
MEMORY_FILE = STORAGE_DIR / "memory.json"
MODEL_NAME = "llama3.2:latest"
MAX_TURNS = 8


from app.prompts import QA_SYSTEM_PROMPT   # ← importar desde prompts.py
QA_PROMPT = ChatPromptTemplate.from_template(QA_SYSTEM_PROMPT) 


# ─────────────────────────────────────────────
# Helpers de formato para respuestas de memoria
# ─────────────────────────────────────────────

def _format_profile_answer(profile: dict) -> str:
    """Formatea el perfil completo — solo para respuestas del carril memory."""
    lines = ["**Perfil del usuario:**"]
    lines.append(f"- Nombre: {profile.get('user_name', 'desconocido')}")
    lines.append(f"- Nivel: {profile.get('user_level', 'desconocido')}")
    lines.append(f"- Proyecto: {profile.get('project_type', 'desconocido')}")
    preferred_style = profile.get("preferred_style", [])
    if preferred_style:
        lines.append(f"- Estilo preferido: {', '.join(preferred_style)}")
    preferred_workflow = profile.get("preferred_workflow", [])
    if preferred_workflow:
        lines.append(f"- Flujo preferido: {' | '.join(preferred_workflow)}")
    return "\n".join(lines)


def _format_project_facts_answer(facts: dict) -> str:
    lines = ["**Hechos persistentes del proyecto:**"]
    for key, value in facts.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def _format_tasks_answer(tasks_data: dict) -> str:
    tasks = tasks_data.get("tasks", [])
    pending = [t for t in tasks if t.get("status") not in ("done", "completed")]
    if not pending:
        return "No hay tareas pendientes registradas."
    lines = ["**Tareas pendientes:**"]
    for t in pending:
        lines.append(
            f"- [{t.get('id', '?')}] {t.get('title', '')} "
            f"(prioridad: {t.get('priority', 'media')}, estado: {t.get('status', 'pending')})"
        )
    return "\n".join(lines)


def _format_work_state_answer(work_state: dict) -> str:
    # A2: clave corregida last_completed_step → last_completed (nombre real en schemas.py)
    lines = ["**Estado actual de trabajo:**"]
    lines.append(f"- Foco actual: {work_state.get('current_focus', 'sin definir')}")
    lines.append(f"- Último paso completado: {work_state.get('last_completed', 'sin registrar')}")
    lines.append(f"- Siguiente paso: {work_state.get('next_step', 'sin definir')}")
    blockers = work_state.get("current_blockers", [])
    if blockers:
        lines.append(f"- Bloqueos: {', '.join(blockers)}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# Respuesta directa desde memoria estructurada
# ─────────────────────────────────────────────

def answer_from_memory(question: str) -> str | None:
    memory_kind = classify_memory_query(question)
    log.debug("Carril memory clasificado como: %s", memory_kind)
    if memory_kind == "profile":
        profile = load_profile()
        if not profile:
            return "No encontré información de perfil todavía."
        return _format_profile_answer(profile)
    if memory_kind == "project_facts":
        facts = load_project_facts()
        if not facts:
            return "No encontré hechos del proyecto todavía."
        return _format_project_facts_answer(facts)
    if memory_kind == "tasks":
        tasks = load_tasks()
        if not tasks:
            return "No encontré tareas registradas."
        return _format_tasks_answer(tasks)
    if memory_kind == "work_state":
        work_state = load_work_state()
        if not work_state:
            return "No encontré estado de trabajo actual."
        return _format_work_state_answer(work_state)
    return None


# ─────────────────────────────────────────────
# SimpleMem — memoria episódica
# ─────────────────────────────────────────────

def generate_session_summary(chat_history: list) -> str:
    if not chat_history:
        return "Sesión sin mensajes registrados."
    recent = chat_history[-(MAX_TURNS * 2):]
    history_text = "\n".join(
        f"{'Usuario' if isinstance(m, HumanMessage) else 'Lautaro'}: {m.content}"
        for m in recent
    )
    prompt = (
        "Eres un asistente que resume sesiones de trabajo.\n"
        "Resume la siguiente conversación en exactamente 3 líneas en español.\n"
        "La primera línea: qué tema principal se trató.\n"
        "La segunda línea: qué se logró o decidió.\n"
        "La tercera línea: cuál es el siguiente paso pendiente.\n"
        "No uses bullet points ni numeración. Solo 3 líneas.\n\n"
        f"Conversación:\n{history_text}\n\nResumen:"
    )
    try:
        import requests
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 120},
            },
            timeout=30,
        )
        return response.json().get("response", "Resumen no disponible.").strip()
    except Exception as exc:
        log.warning("No se pudo generar resumen de sesión: %s", exc)
        return "Resumen no disponible (Ollama no respondió al cerrar)."


def get_last_episode_context() -> str:
    episode = load_last_episode()
    if not episode:
        return ""
    return (
        f"\nÚltima sesión ({episode['date']} {episode['time']}, "
        f"{episode['turns']} turnos):\n{episode['summary']}"
    )


# ─────────────────────────────────────────────
# Infraestructura RAG
# ─────────────────────────────────────────────

def ensure_storage():
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def build_structured_memory_context() -> str:
    """Construye el contexto de memoria para el prompt RAG.

    fix #6: preferred_workflow y preferred_style se omiten aquí.
    Esos campos solo deben usarse cuando el usuario pregunta por su
    perfil (carril memory -> _format_profile_answer).
    """
    profile = load_profile()
    project_facts = load_project_facts()
    work_state = load_work_state()
    tasks_data = load_tasks()
    tasks = tasks_data.get("tasks", [])
    pending_tasks = [t for t in tasks if t.get("status") not in ("done", "completed")][:3]
    lines = []
    if profile:
        lines.append("Perfil del usuario:")
        lines.append(f"- Nombre: {profile.get('user_name', 'desconocido')}")
        lines.append(f"- Nivel: {profile.get('user_level', 'desconocido')}")
        lines.append(f"- Proyecto: {profile.get('project_type', 'desconocido')}")
        # fix #6: preferred_style y preferred_workflow NO se inyectan en RAG
    if project_facts:
        lines.append("")
        lines.append("Hechos persistentes del proyecto:")
        lines.append(f"- Nombre del proyecto: {project_facts.get('project_name', 'desconocido')}")
        lines.append(f"- Fase actual: {project_facts.get('current_phase', 'desconocido')}")
        lines.append(f"- Foco actual: {project_facts.get('current_focus', 'desconocido')}")
        lines.append(f"- Estado RAG: {project_facts.get('rag_status', 'desconocido')}")
        lines.append(f"- Estado memoria: {project_facts.get('memory_status', 'desconocido')}")
    if work_state:
        lines.append("")
        lines.append("Estado actual de trabajo:")
        lines.append(f"- Foco actual: {work_state.get('current_focus', '')}")
        # A2: clave corregida last_completed_step → last_completed
        lines.append(f"- Último paso completado: {work_state.get('last_completed', '')}")
        lines.append(f"- Siguiente paso: {work_state.get('next_step', '')}")
    if pending_tasks:
        lines.append("")
        lines.append("Tareas pendientes prioritarias:")
        for task in pending_tasks:
            lines.append(
                f"- {task.get('id', '')}: {task.get('title', '')} "
                f"(prioridad: {task.get('priority', 'media')}, estado: {task.get('status', 'pending')})"
            )
    last_episode = get_last_episode_context()
    if last_episode:
        lines.append("")
        lines.append("Contexto de la sesión anterior:")
        lines.append(last_episode)
    return "\n".join(lines).strip()


def load_vector_store():
    embeddings = OllamaEmbeddings(
        model="nomic-embed-text",
        base_url="http://localhost:11434",
    )
    vectordb = Chroma(
        embedding_function=embeddings,
        persist_directory=CHROMA_DIR,
    )
    return vectordb


def infer_doc_types(question: str) -> list[str]:
    q = question.lower()
    doc_types = set()
    if any(word in q for word in [
        "arquitectura", "componente", "componentes", "chat.py",
        "indexacion", "índice", "indice", "vector store",
        "base documental", "documentos fuente"
    ]):
        doc_types.add("arquitectura")
    if any(word in q for word in [
        "memoria", "memoria híbrida", "memoria hibrida",
        "grounded", "correcta", "corto plazo", "largo plazo"
    ]):
        doc_types.add("memoria")
    if any(word in q for word in [
        "estado", "próximos pasos", "proximos pasos",
        "objetivo actual", "objetivo de esta etapa",
        "estado del proyecto"
    ]):
        doc_types.add("estado")
    return list(doc_types)


def build_retriever(vectordb, question: str):
    doc_types = infer_doc_types(question)
    search_kwargs = {"k": 5}
    if len(doc_types) == 1:
        search_kwargs["filter"] = {"doc_type": doc_types[0]}
    elif len(doc_types) > 1:
        search_kwargs["filter"] = {
            "$or": [{"doc_type": dt} for dt in doc_types]
        }
    retriever = vectordb.as_retriever(
        search_type="similarity",
        search_kwargs=search_kwargs,
    )
    return retriever


# ─────────────────────────────────────────────
# A1: Historial de conversación — lector/escritor JSON propio
# ─────────────────────────────────────────────

def build_memory() -> list:
    """Lee el historial desde memory.json en formato propio {messages: [...]}."""
    if not MEMORY_FILE.exists():
        return []
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        raw_messages = data.get("messages", [])
        messages = []
        for m in raw_messages[-(MAX_TURNS * 2):]:
            if m.get("role") == "human":
                messages.append(HumanMessage(content=m["content"]))
            elif m.get("role") == "ai":
                messages.append(AIMessage(content=m["content"]))
        return messages
    except Exception as exc:
        log.warning("No se pudo leer memory.json: %s", exc)
        return []


def _format_chat_history(messages: list) -> str:
    if not messages:
        return "(sin historial previo)"
    lines = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            lines.append(f"Usuario: {msg.content}")
        elif isinstance(msg, AIMessage):
            lines.append(f"Lautaro: {msg.content}")
    return "\n".join(lines)


def _persist_turn(user_input: str, answer: str) -> None:
    """Persiste un turno en memory.json usando formato propio {messages: [...]}."""
    if MEMORY_FILE.exists():
        try:
            data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(data.get("messages"), list):
                data = {"messages": []}
        except Exception:
            data = {"messages": []}
    else:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"messages": []}

    data["messages"].append({"role": "human", "content": user_input})
    data["messages"].append({"role": "ai", "content": answer})

    if len(data["messages"]) > MAX_TURNS * 2:
        data["messages"] = data["messages"][-(MAX_TURNS * 2):]

    MEMORY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─────────────────────────────────────────────
# B1: LLM singleton
# ─────────────────────────────────────────────

_llm_instance: ChatOllama | None = None


def _get_llm() -> ChatOllama:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = ChatOllama(
            model=MODEL_NAME,
            base_url="http://localhost:11434",
            temperature=0.1,
        )
        log.debug("LLM singleton inicializado: %s", MODEL_NAME)
    return _llm_instance


def build_chain(retriever, memory_context: str):
    llm = _get_llm()
    qa_prompt_with_memory = QA_PROMPT.partial(memory_context=memory_context)
    chain = qa_prompt_with_memory | llm | StrOutputParser()
    return chain


# ─────────────────────────────────────────────
# Punto de entrada principal del chat
# ─────────────────────────────────────────────

def handle_query(
    user_input: str,
    vectordb: Any,
    chat_history: list,
) -> tuple[str, list]:
    route = route_query(user_input)
    log.debug("Ruta asignada: '%s' para consulta: %s", route, user_input[:60])

    # ── SimpleMem: hook de salida ────────────────────────────────────────
    if route == "exit":
        turns = len(chat_history) // 2
        if turns > 0:
            log.info("Guardando resumen episódico (%d turnos)", turns)
            summary = generate_session_summary(chat_history)
            save_episode(summary=summary, turns=turns)
            log.info("Episodio guardado correctamente")
        return "__EXIT__", []

    # ── B4: despacho centralizado via tool_registry ───────────────────────
    if route in TOOLS:
        result = dispatch_tool(route, user_input)
        log.info("Tool despachada: %s", route)
        return result, []

    # ── Carril memory ─────────────────────────────────────────────────────
    if route == "memory":
        memory_answer = answer_from_memory(user_input)
        if memory_answer is not None:
            return memory_answer, []

    # ── RAG + caché semántica + fidelidad ─────────────────────────────────
    cached = cache_lookup(user_input)
    if cached is not None:
        log.debug("Respuesta servida desde caché semántica")
        _persist_turn(user_input, cached)
        chat_history.append(HumanMessage(content=user_input))
        chat_history.append(AIMessage(content=cached))
        while len(chat_history) > MAX_TURNS * 2:
            chat_history.pop(0)
        return cached, []

    memory_context = build_structured_memory_context()
    retriever = build_retriever(vectordb, user_input)
    source_docs = retriever.invoke(user_input)
    log.debug("RAG: recuperados %d documentos", len(source_docs))
    context_text = "\n\n".join(doc.page_content for doc in source_docs)
    chat_history_text = _format_chat_history(chat_history)

    chain = build_chain(retriever, memory_context)
    answer = chain.invoke({
        "question": user_input,
        "context": context_text,
        "chat_history": chat_history_text,
    })

    is_faithful, score = verify_fidelity(answer, source_docs)
    if not is_faithful:
        log.warning(
            "Respuesta bloqueada por fidelidad insuficiente (score=%.3f) para: %s",
            score, user_input[:60],
        )
        return NO_EVIDENCE_MSG, source_docs

    cache_save(user_input, answer)
    _persist_turn(user_input, answer)
    chat_history.append(HumanMessage(content=user_input))
    chat_history.append(AIMessage(content=answer))
    while len(chat_history) > MAX_TURNS * 2:
        chat_history.pop(0)

    return answer, source_docs
