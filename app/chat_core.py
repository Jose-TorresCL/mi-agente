from pathlib import Path

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
2. Usa SOLO el contexto recuperado. No inventes nada.
3. Si la respuesta está explícita en el contexto (frase textual o casi textual), respóndela directamente.
4. Si la respuesta está repartida en 2-3 chunks pero la relación es clara, sintetízala en 1-2 frases.
5. Si el contexto establece un orden claro de prioridades o etapas, puedes responder el "por qué" explicando esa prioridad de forma breve y fiel, sin inventar causas no mencionadas.
6. Abstente SOLO si realmente no hay evidencia útil en NINGÚN chunk. Responde entonces exactamente:
"No tengo suficiente evidencia en el contexto recuperado."

Formato:
- Respeta EXACTAMENTE el formato pedido.
- No agregues introducciones ni explicaciones extra.

Contexto recuperado:
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