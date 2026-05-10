# LangChain — Text Splitters

## ¿Qué es un Text Splitter?

Un Text Splitter divide documentos largos en fragmentos (chunks) más pequeños antes de indexarlos en el vector store. Es uno de los pasos más críticos de un pipeline RAG: chunks demasiado grandes pierden precisión semántica; chunks demasiado pequeños pierden contexto.

## ¿Por qué es importante?

Los modelos de embedding tienen límites de tokens (por ejemplo, `nomic-embed-text` acepta hasta ~8192 tokens). Además, recuperar un chunk de 200 palabras es mucho más preciso que recuperar páginas enteras.

## Tipos principales

### 1. RecursiveCharacterTextSplitter (recomendado)

El más utilizado. Intenta dividir respetando separadores naturales del texto en orden de prioridad: `\n\n` → `\n` → ` ` → carácter a carácter.

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,       # máximo de caracteres por chunk
    chunk_overlap=50,     # solapamiento entre chunks
    separators=["\n\n", "\n", " ", ""],  # orden de prioridad
)

chunks = splitter.split_documents(docs)
```

### 2. CharacterTextSplitter

Divide por un separador fijo. Más simple pero menos inteligente.

```python
from langchain.text_splitter import CharacterTextSplitter

splitter = CharacterTextSplitter(
    separator="\n",
    chunk_size=1000,
    chunk_overlap=100,
)
```

### 3. MarkdownHeaderTextSplitter

Ideal para documentos `.md`: divide respetando la jerarquía de headers (`#`, `##`, `###`).

```python
from langchain.text_splitter import MarkdownHeaderTextSplitter

headers_to_split_on = [
    ("#", "titulo"),
    ("##", "seccion"),
    ("###", "subseccion"),
]

splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
chunks = splitter.split_text(texto_markdown)
```

### 4. TokenTextSplitter

Divide por tokens reales (no caracteres). Necesario si trabajas con límites de tokens del modelo.

```python
from langchain.text_splitter import TokenTextSplitter

splitter = TokenTextSplitter(chunk_size=256, chunk_overlap=20)
```

## Parámetros clave

| Parámetro | Descripción | Impacto |
|---|---|---|
| `chunk_size` | Tamaño máximo por chunk (caracteres o tokens) | Más grande = más contexto, menos precisión |
| `chunk_overlap` | Cuántos caracteres se repiten entre chunks | Evita cortar ideas a la mitad |
| `separators` | Lista de separadores en orden de preferencia | Controla dónde se corta |
| `length_function` | Función para medir longitud (default: `len`) | Cambiar por `tiktoken` para tokens |

## Elegir chunk_size según el caso

```
Documentos técnicos (código, APIs):  chunk_size = 300–500
Documentos conceptuales (artículos): chunk_size = 500–800
Conversaciones / logs:               chunk_size = 200–400
Documentos largos (libros):          chunk_size = 800–1200
```

## Ver los chunks generados

```python
chunks = splitter.split_documents(docs)

print(f"Total chunks: {len(chunks)}")
for i, chunk in enumerate(chunks[:3]):
    print(f"--- Chunk {i} ({len(chunk.page_content)} chars) ---")
    print(chunk.page_content[:200])
    print(f"Metadata: {chunk.metadata}")
```

## Error común

**Problema**: `chunk_overlap` mayor que `chunk_size`.
**Error**: `ValueError: Got a larger chunk overlap than chunk size`.
**Solución**: `chunk_overlap` debe ser menor que `chunk_size`. Regla práctica: overlap = 10% del chunk_size.

## Buenas prácticas

- Para archivos `.md` del proyecto: usar `MarkdownHeaderTextSplitter` primero, luego `RecursiveCharacterTextSplitter` si los chunks siguen siendo grandes.
- Incluir la metadata del archivo original en cada chunk para poder citarla en la respuesta.
- Loggear cuántos chunks genera cada archivo para detectar documentos muy grandes o muy pequeños.
- El `chunk_overlap` es tu seguro contra respuestas cortadas: no lo pongas en 0.
