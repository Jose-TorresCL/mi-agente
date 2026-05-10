# LangChain — RAG (Retrieval Augmented Generation)

## ¿Qué es RAG?

Retrieval Augmented Generation (RAG) es una técnica que combina la recuperación de documentos relevantes con la generación de texto usando un LLM. En lugar de confiar solo en el conocimiento del modelo, RAG busca información actualizada en una base de datos (vector store) y la inyecta como contexto al modelo antes de generar la respuesta.

## Flujo típico de RAG

```
Pregunta del usuario
       ↓
[Embedding de la pregunta]
       ↓
[Búsqueda en Vector Store] → documentos relevantes
       ↓
[Contexto + Pregunta] → LLM
       ↓
  Respuesta final
```

## Componentes principales

### 1. Document Loader
Carga documentos desde distintas fuentes: archivos, URLs, PDFs, bases de datos.

```python
from langchain_community.document_loaders import TextLoader
loader = TextLoader("mi_documento.txt")
docs = loader.load()
```

### 2. Text Splitter
Divide los documentos en fragmentos (chunks) manejables para el embedding.

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_documents(docs)
```

### 3. Embedding Model
Convierte cada chunk en un vector numérico que representa su significado semántico.

```python
from langchain_ollama import OllamaEmbeddings
embeddings = OllamaEmbeddings(model="nomic-embed-text")
```

### 4. Vector Store
Almacena los embeddings y permite buscar por similitud semántica.

```python
from langchain_chroma import Chroma
vectorstore = Chroma.from_documents(chunks, embedding=embeddings, persist_directory="./storage/rag")
```

### 5. Retriever
Interfaz de búsqueda sobre el vector store. Devuelve los k documentos más similares a una consulta.

```python
retriever = vectorstore.as_retriever(search_kwargs={"k": 4})
docs_relevantes = retriever.invoke("¿qué hace el módulo router?")
```

### 6. Chain RAG
Une retriever + prompt + LLM en una cadena de procesamiento.

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

llm = ChatOllama(model="llama3.2")

prompt = ChatPromptTemplate.from_template("""
Responde la pregunta usando SOLO el siguiente contexto:

Contexto:
{context}

Pregunta: {question}
""")

def format_docs(docs):
    return "\n\n".join(d.page_content for d in docs)

chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

respuesta = chain.invoke("¿qué hace el módulo router?")
```

## Parámetros importantes

| Parámetro | Descripción | Valor típico |
|---|---|---|
| `chunk_size` | Tamaño máximo de cada fragmento (en caracteres) | 300–1000 |
| `chunk_overlap` | Solapamiento entre chunks contiguos | 10–15% del chunk_size |
| `k` | Número de documentos a recuperar | 3–6 |
| `score_threshold` | Similitud mínima para incluir un documento | 0.5–0.75 |

## Tipos de búsqueda en Chroma

- **similarity** (default): devuelve los k más similares sin filtro de score.
- **similarity_score_threshold**: filtra por umbral mínimo de similitud.
- **mmr** (Maximal Marginal Relevance): balancea relevancia y diversidad.

```python
# Con umbral de similitud
retriever = vectorstore.as_retriever(
    search_type="similarity_score_threshold",
    search_kwargs={"score_threshold": 0.6, "k": 4}
)

# Con MMR para diversidad
retriever = vectorstore.as_retriever(
    search_type="mmr",
    search_kwargs={"k": 4, "fetch_k": 20}
)
```

## Error común

**Problema**: El retriever devuelve documentos irrelevantes.
**Causa**: chunk_size demasiado grande (pierde precisión) o demasiado pequeño (pierde contexto).
**Solución**: Experimentar con chunk_size entre 300 y 800, overlap 10–15%.

## Buenas prácticas

- Siempre hacer `persist_directory` para no re-indexar en cada ejecución.
- Usar `nomic-embed-text` con Ollama: buen balance velocidad/calidad para texto en español.
- Incluir metadata en los documentos (nombre de archivo, fecha) para filtrar después.
- Loggear qué documentos devuelve el retriever para diagnosticar respuestas malas.
