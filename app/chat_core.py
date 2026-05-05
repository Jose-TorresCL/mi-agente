from pathlib import Path
from app.memory_store import (
    load_profile,
    load_project_facts,
    load_tasks,
    load_work_state,
)

from langchain_chroma import Chroma
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_classic.chains import ConversationalRetrievalChain
from langchain_classic.memory import ConversationBufferWindowMemory
from langchain_community.chat_message_histories import FileChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate

STORAGE_DIR = Path("storage")
CHROMA_DIR = str(STORAGE_DIR / "chroma")
MEMORY_FILE = STORAGE_DIR / "memory.json"
MODEL_NAME = "llama3.2:latest"


QA_SYSTEM_PROMPT = """
Eres Lautaro, asistente local del proyecto.

Reglas principales:
1. Responde SIEMPRE en español claro y breve.
2. Usa la memoria estructurada para responder preguntas sobre perfil, preferencias, estado actual, tareas y hechos persistentes.
3. Usa el contexto recuperado para responder preguntas documentales sobre el proyecto.
4. No inventes nada. Si la información no está explícita en la memoria estructurada ni en el contexto recuperado, responde exactamente:
"No tengo suficiente evidencia en el contexto recuperado."
5. Si la respuesta está explícita, respóndela directamente.
6. Si la respuesta requiere unir 2 o 3 fragmentos compatibles, sintetízala de forma breve y fiel.
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

Contexto recuperado:
{context}

Pregunta:
{question}
"""

QA_PROMPT = ChatPromptTemplate.from_template(QA_SYSTEM_PROMPT)


def ensure_storage():
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

def build_structured_memory_context() -> str:
    profile = load_profile()
    project_facts = load_project_facts()
    work_state = load_work_state()
    tasks_data = load_tasks()

    tasks = tasks_data.get("tasks", [])
    pending_tasks = [t for t in tasks if t.get("status") != "done"][:3]

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


def build_memory():
    chat_history = FileChatMessageHistory(file_path=str(MEMORY_FILE))
    memory = ConversationBufferWindowMemory(
        k=8,
        memory_key="chat_history",
        chat_memory=chat_history,
        return_messages=True,
        output_key="answer",
    )
    return memory


def build_chain(retriever, memory, memory_context: str):
    llm = ChatOllama(
        model=MODEL_NAME,
        base_url="http://localhost:11434",
        temperature=0.1,
    )

    qa_prompt_with_memory = QA_PROMPT.partial(memory_context=memory_context)

    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        return_source_documents=True,
        output_key="answer",
        combine_docs_chain_kwargs={"prompt": qa_prompt_with_memory},
    )
    return chain