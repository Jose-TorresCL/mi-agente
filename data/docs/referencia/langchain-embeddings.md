# LangChain — Embedding Models

## ¿Qué es un Embedding?

Un embedding es una representación numérica (vector) de un texto que captura su significado semántico. Textos con significados similares producen vectores cercanos en el espacio vectorial. Esto permite buscar documentos relevantes por significado, no solo por palabras exactas.

## Analogía simple

Imagina que cada frase ocupa una posición en un mapa 3D. Las frases con significado similar están cerca en el mapa. El embedding es esa posición (x, y, z) pero en cientos o miles de dimensiones.

## Embeddings con Ollama (local)

Para tu proyecto, usas `nomic-embed-text` corriendo localmente con Ollama:

```python
from langchain_ollama import OllamaEmbeddings

embeddings = OllamaEmbeddings(
    model="nomic-embed-text",
    base_url="http://localhost:11434",
)

# Embeder una lista de textos
vectores = embeddings.embed_documents(["Hola mundo", "¿Cómo estás?"])
print(f"Dimensiones: {len(vectores[0])}")  # nomic produce 768 dims

# Embeder una query
vector_query = embeddings.embed_query("¿qué hace el router?")
```

## Instalar nomic-embed-text en Ollama

```powershell
ollama pull nomic-embed-text
```

## Comparación de modelos de embedding

| Modelo | Dims | Tokens max | Velocidad | Uso |
|---|---|---|---|---|
| `nomic-embed-text` | 768 | 8192 | Rápido | Proyectos locales (recomendado) |
| `mxbai-embed-large` | 1024 | 512 | Medio | Mayor calidad, más lento |
| `all-minilm` | 384 | 256 | Muy rápido | Prototipado rápido |
| `text-embedding-ada-002` | 1536 | 8192 | API | OpenAI (requiere clave) |

## Uso con Chroma

```python
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

embeddings = OllamaEmbeddings(model="nomic-embed-text")

# Crear vector store desde documentos
vectorstore = Chroma.from_documents(
    documents=chunks,
    embedding=embeddings,
    persist_directory="./storage/rag",
    collection_name="mi_coleccion",
)

# Cargar vector store existente
vectorstore = Chroma(
    persist_directory="./storage/rag",
    embedding_function=embeddings,
    collection_name="mi_coleccion",
)
```

## Singleton: reutilizar la instancia

Crear una instancia de `OllamaEmbeddings` por cada consulta es lento porque inicializa la conexión cada vez. Usa el patrón singleton:

```python
_embeddings_instance = None

def get_embeddings():
    global _embeddings_instance
    if _embeddings_instance is None:
        _embeddings_instance = OllamaEmbeddings(
            model="nomic-embed-text",
            base_url="http://localhost:11434",
        )
    return _embeddings_instance
```

## Similitud coseno

Chroma usa distancia coseno para comparar vectores. La fórmula de conversión a similitud:

```
similitud = 1 - (distancia / 2)
```

- Distancia 0 = vectores idénticos → similitud 1.0
- Distancia 2 = vectores opuestos → similitud 0.0
- Umbral recomendado para RAG: similitud > 0.6

```python
# Búsqueda con score
resultados = vectorstore.similarity_search_with_score("¿qué es el router?", k=4)
for doc, score in resultados:
    similitud = 1 - (score / 2)
    print(f"Similitud: {similitud:.2f} | {doc.page_content[:100]}")
```

## Error común

**Problema**: `ConnectionRefusedError` al usar OllamaEmbeddings.
**Causa**: Ollama no está corriendo.
**Solución**:
```powershell
ollama serve
# En otra terminal:
ollama pull nomic-embed-text
```

## Buenas prácticas

- Usa siempre el mismo modelo de embedding para indexar y para consultar. Si cambias el modelo, debes re-indexar todo.
- Guarda el nombre del modelo en una constante (`EMBED_MODEL = "nomic-embed-text"`) para no escribirlo en múltiples lugares.
- `nomic-embed-text` es bueno para inglés y aceptable para español. Para español puro considera `mxbai-embed-large`.
