from pathlib import Path
from typing import Any

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
from app.tools import (
    list_project_files,
    read_project_file,
    tool_save_fact,
    tool_create_task,
    tool_complete_task,
    tool_update_work_state,
    extract_task_id,
    parse_work_state_update,
)

from langchain_chroma import Chroma
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_community.chat_message_histories import FileChatMessageHistory
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda

STORAGE_DIR = Path("storage")
CHROMA_DIR = str(STORAGE_DIR / "chroma")
MEMORY_FILE = STORAGE_DIR / "memory.json"
MODEL_NAME = "llama3.2:latest"
MAX_TURNS = 8


QA_SYSTEM_PROMPT = """
Eres Lautaro, asistente local del proyecto.

Reglas principales:
1. Responde SIEMPRE en español claro y breve.
2. Usa la memoria estructurada para responder preguntas sobre perfil, preferencias, estado actual, tareas y hechos persistentes.
3. Usa el contexto recuperado para responder preguntas documentales sobre el proyecto.
4. No inventes nada. Si la información no está explícita en la memoria estructurada ni en el contexto recuperado, responde exactamente:
"No tengo suficiente evidencia en el contexto recuperado."
5. Si la respuesta está explícita, respóndela directamente.
6. Si la respuesta requiere unir 2 o 3 fragmentos compatibles, sintétizala de forma breve y fiel.
7. No agregues introducciones, rodeos ni explicaciones extra.

Reglas de prioridad:
8. Si la pregunta es sobre estilo de respuesta, usa "Estilo preferido" del perfil.
9. Si la pregunta es sobre cómo explicar, diagnosticar o acompañar trabajo técnico, usa "Flujo preferido" del perfil.
10. Si la pregunta es sobre estado del proyecto, usa primero los hechos persistentes y el estado de trabajo.
11. Si la pregunta es documental, usa primero el contexto recuperado.
12. No confundas estilo, flujo y estado del proyecto: son cosas distintas.

Formato:
- Respeta EXACTAMENTE el formato pedido.
- Responde de forma directa.

Memoria estructurada:
{memory_context}

Historial de conversación:
{chat_history}

Contexto recuperado:
{context}

Pregunta:
{question}
"""

QA_PROMPT = ChatPromptTemplate.from_template(QA_SYSTEM_PROMPT)


# ─────────────────────────────────────────────
# Helpers de formato para respuestas de memoria
# ─────────────────────────────────────────────

def _format_profile_answer(profile: dict) -> str:
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
    lines = ["**Estado actual de trabajo:**"]
    lines.append(f"- Foco actual: {work_state.get('current_focus', 'sin definir')}")
    lines.append(f"- Último paso completado: {work_state.get('last_completed_step', 'sin registrar')}")
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
    except Exception:
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
        preferred_style = profile.get("preferred_style", [])
        if preferred_style:
            lines.append(f"- Estilo preferido: {', '.join(preferred_style)}")
        preferred_workflow = profile.get("preferred_workflow", [])
        if preferred_workflow:
            lines.append(f"- Flujo preferido: {' | '.join(preferred_workflow)}")
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
        lines.append(f"- Último paso completado: {work_state.get('last_completed_step', '')}")
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
# Historial de conversación
# ─────────────────────────────────────────────

def build_memory() -> list:
    file_history = FileChatMessageHistory(file_path=str(MEMORY_FILE))
    messages = file_history.messages
    return list(messages[-(MAX_TURNS * 2):])


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
    file_history = FileChatMessageHistory(file_path=str(MEMORY_FILE))
    file_history.add_user_message(user_input)
    file_history.add_ai_message(answer)


def build_chain(retriever, memory_context: str):
    llm = ChatOllama(
        model=MODEL_NAME,
        base_url="http://localhost:11434",
        temperature=0.1,
    )
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

    # ── SimpleMem: hook de salida ─────────────────────────────────────────
    if route == "exit":
        turns = len(chat_history) // 2
        if turns > 0:
            print("Guardando resumen de la sesión...")
            summary = generate_session_summary(chat_history)
            save_episode(summary=summary, turns=turns)
            print(f"Episodio guardado ({turns} turnos).")
        return "__EXIT__", []

    # ── Tools de escritura ──────────────────────────────────────────
    if route == "tool_save_fact":
        prefixes = [
            "guarda como hecho que", "guarda como hecho:", "guarda como hecho",
            "guardar hecho que", "registra que", "anota que",
            "guarda el hecho que", "registra el hecho que",
            "guarda esto como hecho:", "guarda esto como hecho",
        ]
        content = user_input.strip()
        for prefix in prefixes:
            if content.lower().startswith(prefix):
                content = content[len(prefix):].strip()
                break
        if not content:
            return "No pude guardar el hecho: no entendí el contenido.", []
        return tool_save_fact(content), []

    if route == "tool_create_task":
        text = user_input.lower()
        for prefix in ["crea una tarea:", "crea una tarea", "crear tarea:", "crear tarea",
                       "agrega una tarea:", "agrega una tarea", "nueva tarea:", "nueva tarea",
                       "añade una tarea:", "añade una tarea", "anota una tarea:", "anota una tarea",
                       "registra una tarea:", "registra una tarea"]:
            if text.startswith(prefix):
                raw = user_input[len(prefix):].strip()
                priority = "medium"
                for p in ["alta", "high", "baja", "low", "media", "medium"]:
                    if raw.lower().endswith(p):
                        raw = raw[:-len(p)].strip().rstrip(",;")
                        priority = {"alta": "high", "baja": "low", "media": "medium"}.get(p, p)
                        break
                return tool_create_task(title=raw, priority=priority), []
        return tool_create_task(title=user_input, priority="medium"), []

    if route == "tool_complete_task":
        task_id = extract_task_id(user_input)
        if not task_id:
            return "No encontré el ID de la tarea. Indícalo así: 'marca T-002 como completada'", []
        return tool_complete_task(task_id), []

       if route == "tool_update_work_state":
        # La tool ahora es autosuficiente
        return tool_update_work_state(user_input), []

    if route == "tool_list_files":
        files = list_project_files()
        if not files:
            return "No encontré archivos en las carpetas permitidas.", []
        return "Archivos del proyecto:\n" + "\n".join(f"- {f}" for f in files), []

    if route == "tool_read_file":
        from app.tools import extract_file_path
        path = extract_file_path(user_input)
        if not path:
            return "No pude identificar qué archivo querías leer.", []
        return read_project_file(path), []

    if route == "memory":
        memory_answer = answer_from_memory(user_input)
        if memory_answer is not None:
            return memory_answer, []

    # ── RAG + caché semántica (10c) + fidelidad (10a) ───────────────────
    # Paso 1: caché semántica (umbral 0.88)
    cached = cache_lookup(user_input)
    if cached is not None:
        _persist_turn(user_input, cached)
        chat_history.append(HumanMessage(content=user_input))
        chat_history.append(AIMessage(content=cached))
        while len(chat_history) > MAX_TURNS * 2:
            chat_history.pop(0)
        return cached, []

    # Paso 2: flujo RAG normal
    memory_context = build_structured_memory_context()
    retriever = build_retriever(vectordb, user_input)
    source_docs = retriever.invoke(user_input)
    context_text = "\n\n".join(doc.page_content for doc in source_docs)
    chat_history_text = _format_chat_history(chat_history)

    chain = build_chain(retriever, memory_context)
    answer = chain.invoke({
        "question": user_input,
        "context": context_text,
        "chat_history": chat_history_text,
    })

    # Paso 3: verificación de fidelidad (10a)
    # Si la respuesta no está soportada por los chunks, la bloqueamos
    if not verify_fidelity(answer, source_docs):
        # NO guardar en caché ni en historial una respuesta sospechosa
        return NO_EVIDENCE_MSG, source_docs

    # Paso 4: guardar en caché solo si la fidelidad es ok
    cache_save(user_input, answer)

    _persist_turn(user_input, answer)
    chat_history.append(HumanMessage(content=user_input))
    chat_history.append(AIMessage(content=answer))
    while len(chat_history) > MAX_TURNS * 2:
        chat_history.pop(0)

    return answer, source_docs
