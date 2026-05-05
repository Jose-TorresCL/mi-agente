"""
Asistente local:
- Usa Ollama (por defecto llama3.2:latest) como LLM.
- Recupera contexto de tus docs con Chroma (RAG).
- Guarda memoria de conversación en storage/memory.json.

Ejecutar:
    python chat.py

Salir:
    escribir 'salir', 'exit' o 'quit'.

Comando especial:
    !reset  -> borra la memoria de conversación (storage/memory.json)
"""

from pathlib import Path

from langchain_chroma import Chroma
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_classic.chains import ConversationalRetrievalChain
from langchain_classic.memory import ConversationBufferWindowMemory
from langchain_community.chat_message_histories import FileChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate

from rich.console import Console
from rich.markdown import Markdown


STORAGE_DIR = Path("storage")
CHROMA_DIR = str(STORAGE_DIR / "chroma")
MEMORY_FILE = STORAGE_DIR / "memory.json"
MODEL_NAME = "llama3.2:latest"

console = Console()

QA_SYSTEM_PROMPT = QA_SYSTEM_PROMPT = """
Eres Lautaro, asistente local del proyecto.

Reglas:
- Responde siempre en español claro, directo y breve.
- Usa únicamente el contexto recuperado para responder.
- No inventes datos, no completes huecos y no uses conocimiento general externo.
- Si hay evidencia suficiente en una o múltiples fuentes recuperadas, une esa evidencia lógicamente y responde.
- Si la evidencia no es suficiente o es demasiado ambigua, responde exactamente:
No tengo suficiente evidencia en el contexto recuperado.

Formato:
- Respeta exactamente el formato pedido por la pregunta.
- Si pide una frase, responde una frase.
- Si pide una lista, responde una lista.
- Si pide dos líneas o una estructura específica, respétala exactamente.
- No agregues introducciones, saludos, explicaciones extra ni consejos no solicitados.

Criterio:
- Prioriza la respuesta más fiel al texto recuperado.
- Si una respuesta breve y directa ya está respaldada por el contexto, no te abstengas.
- Si necesitas combinar dos o más fragmentos recuperados para responder, hazlo solo cuando la relación entre ellos sea clara y explícita.

Contexto:
{context}

Pregunta:
{question}
"""

QA_PROMPT = ChatPromptTemplate.from_template(QA_SYSTEM_PROMPT)


def ensure_storage():
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


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
        "estado del proyecto", "rag"
    ]):
        doc_types.add("estado")

    return list(doc_types)


def build_retriever(vectordb, question: str):
    doc_types = infer_doc_types(question)

    search_kwargs = {
        "k": 3,
        "fetch_k": 6,
        "lambda_mult": 0.5,
    }

    if len(doc_types) == 1:
        search_kwargs["filter"] = {"doc_type": doc_types[0]}
    elif len(doc_types) > 1:
        search_kwargs["filter"] = {
            "$or": [{"doc_type": dt} for dt in doc_types]
        }

    retriever = vectordb.as_retriever(
        search_type="mmr",
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


def build_chain(retriever, memory):
    llm = ChatOllama(
        model=MODEL_NAME,
        base_url="http://localhost:11434",
        temperature=0.1,
    )

    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        return_source_documents=True,
        output_key="answer",
        combine_docs_chain_kwargs={"prompt": QA_PROMPT},
    )

    return chain


def print_sources(docs):
    if not docs:
        return

    console.print("[dim]Basado en:[/dim]")
    seen = set()
    idx = 1

    for d in docs:
        src = d.metadata.get("source", "desconocido")
        name = Path(src).name if src != "desconocido" else src
        doc_type = d.metadata.get("doc_type", "sin_tipo")
        section = d.metadata.get("section", "sin_seccion")

        key = (src, doc_type, section)
        if key not in seen:
            console.print(f"  {idx}. {name} | {doc_type} | {section}")
            seen.add(key)
            idx += 1


def main():
    ensure_storage()

    if not Path(CHROMA_DIR).exists():
        raise FileNotFoundError(
            f"No encuentro el vector store en {CHROMA_DIR}. "
            "Primero ejecuta 'python indexacion.py'."
        )

    vectordb = load_vector_store()
    memory = build_memory()

    console.print("[bold green]Lautaro está iniciado[/bold green]")
    console.print("Escribe tu pregunta. 'salir', 'exit' o 'quit' para terminar.")
    console.print("Comando especial: [yellow]!reset[/yellow] para borrar la memoria.\n")

    while True:
        user_input = console.input("[bold cyan]Tú:[/bold cyan] ").strip()

        if user_input.lower() in {"salir", "exit", "quit"}:
            console.print("[yellow]Hasta luego 👋[/yellow]")
            break

        if user_input.lower() == "!reset":
            if MEMORY_FILE.exists():
                MEMORY_FILE.unlink()
            console.print("[red]Memoria de conversación borrada.[/red]")
            memory = build_memory()
            continue

        if not user_input:
            continue

        console.print("[magenta]Pensando...[/magenta]")

        retriever = build_retriever(vectordb, user_input)
        chain = build_chain(retriever, memory)

        result = chain.invoke({"question": user_input})

        answer = result["answer"]
        docs = result.get("source_documents", [])

        console.print(Markdown(f"**Lautaro:** {answer}"))
        print_sources(docs)


if __name__ == "__main__":
    main()