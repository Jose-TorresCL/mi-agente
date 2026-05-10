# LangChain — VectorStore Retriever

## ¿Qué es un Retriever?

Un Retriever es una interfaz de LangChain que encapsula la lógica de búsqueda sobre un vector store. Toma una pregunta en texto natural y devuelve una lista de documentos relevantes. Es el puente entre la pregunta del usuario y los documentos indexados.

## Crear un retriever desde Chroma

```python
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

embeddings = OllamaEmbeddings(model="nomic-embed-text")
vectorstore = Chroma(
    persist_directory="./storage/rag",
    embedding_function=embeddings,
    collection_name="mi_coleccion",
)

# Retriever básico: devuelve los 4 documentos más similares
retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

# Usar el retriever
docs = retriever.invoke("¿qué hace el módulo router?")
for doc in docs:
    print(doc.page_content[:200])
    print(doc.metadata)
```

## Tipos de búsqueda

### similarity (default)
Devuelve los k documentos más cercanos sin ningún filtro.

```python
retriever = vectorstore.as_retriever(
    search_type="similarity",
    search_kwargs={"k": 4}
)
```

### similarity_score_threshold
Filtro por similitud mínima. Si ningún documento supera el umbral, devuelve lista vacía.

```python
retriever = vectorstore.as_retriever(
    search_type="similarity_score_threshold",
    search_kwargs={
        "score_threshold": 0.6,  # mínimo 60% de similitud
        "k": 4
    }
)
```

### mmr — Maximal Marginal Relevance
Busca documentos relevantes Y diversos entre sí. Evita devolver 4 fragmentos que dicen lo mismo.

```python
retriever = vectorstore.as_retriever(
    search_type="mmr",
    search_kwargs={
        "k": 4,        # documentos a devolver
        "fetch_k": 20  # candidatos a evaluar antes de filtrar por diversidad
    }
)
```

## Filtrar por metadata

Puedes buscar solo en documentos de un archivo específico:

```python
retriever = vectorstore.as_retriever(
    search_kwargs={
        "k": 4,
        "filter": {"source": "data/docs/referencia/langchain-rag-concepto.md"}
    }
)
```

## Búsqueda directa sin retriever

```python
# Búsqueda directa con score de similitud
resultados = vectorstore.similarity_search_with_score(
    query="¿qué es el router?",
    k=4
)
for doc, distancia in resultados:
    similitud = 1 - (distancia / 2)
    print(f"[{similitud:.2f}] {doc.metadata.get('source', '?')}")
    print(doc.page_content[:150])
    print()
```

## Usar el retriever en una chain RAG

```python
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

llm = ChatOllama(model="llama3.2")

prompt = ChatPromptTemplate.from_template("""
Usando SOLO el siguiente contexto, responde la pregunta.
Si no encuentras la respuesta en el contexto, di "No tengo esa información".

Contexto:
{context}

Pregunta: {question}
""")

def format_docs(docs):
    if not docs:
        return "No se encontraron documentos relevantes."
    return "\n\n---\n\n".join(
        f"[Fuente: {d.metadata.get('source', 'desconocido')}]\n{d.page_content}"
        for d in docs
    )

chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

respuesta = chain.invoke("¿qué hace el módulo router?")
print(respuesta)
```

## Diagnóstico: ¿qué está recuperando el retriever?

Antes de conectar el retriever a la chain, pruébalo directamente:

```python
docs = retriever.invoke("¿qué hace el módulo router?")
print(f"Documentos recuperados: {len(docs)}")
for i, doc in enumerate(docs):
    print(f"\n--- Doc {i+1} ---")
    print(f"Fuente: {doc.metadata.get('source', '?')}")
    print(f"Contenido: {doc.page_content[:300]}")
```

Si el retriever devuelve 0 documentos o documentos irrelevantes, el problema está en la indexación o en el chunk_size, no en el LLM.

## Error común

**Problema**: El retriever devuelve documentos de otro tema.
**Causa**: El umbral de similitud es muy bajo o el corpus tiene pocos documentos.
**Solución**: Usar `similarity_score_threshold` con 0.6 y loggear los scores reales para ajustar.

## Buenas prácticas

- Siempre usar `format_docs` para formatear el contexto antes de mandarlo al LLM.
- Incluir la fuente del documento (`doc.metadata['source']`) en el contexto para que el LLM pueda citar.
- Loggear los documentos recuperados durante desarrollo — es la forma más rápida de diagnosticar respuestas malas.
- En producción, usar `similarity_score_threshold` en lugar de `similarity` puro para evitar respuestas con contexto irrelevante.
