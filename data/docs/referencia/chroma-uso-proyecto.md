# Chroma — Cómo funciona y cómo lo usa este proyecto

> Documento curado para RAG. Reemplaza `chroma-introduccion.md` que contenía scraping de la web.
> Última actualización: 25/05/2026

---

## ¿Qué es Chroma?

Chroma es una base de datos vectorial de código abierto diseñada para almacenar embeddings y permitir búsqueda por similitud semántica.

La diferencia clave con una base de datos SQL normal:

| SQL tradicional | Chroma |
|---|---|
| Busca por igualdad exacta (`WHERE nombre = 'foo'`) | Busca por significado parecido |
| Devuelve registros que coinciden | Devuelve los documentos más "cercanos" al texto consultado |
| No entiende lenguaje natural | Entiende relaciones semánticas entre palabras |

**Analogía**: Chroma es como un GPS de ideas. En vez de buscar una dirección exacta, encuentra los destinos más cercanos a donde quieres llegar.

---

## Cómo funciona internamente

### Paso 1 — Indexación (se hace una vez)

```
Texto del documento
      ↓
  nomic-embed-text  ← modelo de embeddings corriendo en Ollama
      ↓
Vector numérico de 768 dimensiones  [0.12, -0.44, 0.87, ...]
      ↓
  Chroma lo guarda en storage/chroma/
```

### Paso 2 — Búsqueda (se hace en cada consulta)

```
Pregunta del usuario
      ↓
  nomic-embed-text convierte la pregunta en vector
      ↓
  Chroma compara ese vector con todos los guardados (similitud coseno)
      ↓
Devuelve los k documentos más cercanos (por defecto k=4)
      ↓
  rag_engine.py los pasa al LLM como contexto
```

---

## Los 3 índices Chroma del proyecto

Este proyecto usa **tres colecciones Chroma separadas**, cada una con un propósito distinto:

| Índice | Ruta en disco | Qué almacena | Cuándo crece |
|---|---|---|---|
| RAG principal | `storage/chroma/` | Chunks de documentación del proyecto (269 chunks) | Al re-indexar con `indexacion.py` |
| Intent index | `storage/intent_index/` | 96 ejemplos de intenciones del router | Cuando se entrena el router |
| Experience index | `storage/experience_index/` | Episodios de sesiones pasadas | Al cerrar cada sesión |

---

## Cómo lo usa `rag_engine.py`

```python
# Configuración actual del retriever en el proyecto
retriever = chroma_db.as_retriever(
    search_type="mmr",        # Maximal Marginal Relevance
    search_kwargs={
        "k": 5,               # devolver 5 documentos
        "fetch_k": 20,        # candidatos previos al re-ranking
        "lambda_mult": 0.6    # balance relevancia vs diversidad
    }
)
```

**¿Por qué MMR y no similarity simple?**

Con similarity simple, si tienes 5 chunks muy parecidos sobre el mismo tema, los 5 serían devueltos (redundancia). MMR equilibra relevancia con diversidad: prefiere documentos relevantes pero que no digan exactamente lo mismo.

---

## Cómo verificar qué está indexado

```powershell
# Ver todas las fuentes actualmente en el índice RAG
python -c "
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
emb = OllamaEmbeddings(model='nomic-embed-text')
db = Chroma(persist_directory='./storage/chroma', embedding_function=emb)
result = db.get()
sources = sorted(set(m.get('source','?') for m in result['metadatas']))
print(f'Total chunks: {len(result[\"ids\"])}')
for s in sources: print(' -', s)
"
```

Salida esperada: lista de archivos `.md` + total de chunks (actualmente ~269).

---

## Documentos indexados actualmente (RAG principal)

Los documentos que alimentan el RAG están en `data/docs/`. Los docs **excluidos** (porque son documentos vivos que cambian frecuentemente) son:

- `estado_proyecto.md` — excluido, se lee directamente por tools
- `roadmap.md` — excluido, es planificación futura no referencia

Todos los demás `.md` en `data/docs/` son candidatos a indexación. Ver `indexacion.py` para la lista exacta y exclusiones configuradas.

---

## Cómo re-indexar

```powershell
# Reconstruir el índice RAG completo
python indexacion.py

# Salida esperada:
# Indexando data/docs/...
# Total chunks generados: ~269
# Índice guardado en storage/chroma/
```

⚠️ **Antes de re-indexar**: excluir los docs de scraping (`chroma-introduccion.md`, `chroma-queries.md`) y el API de Ollama completo (`ollama-api.md` si está presente) para no contaminar el índice con fragmentos inservibles.

---

## Errores comunes

**Error 1**: Indexar documentos de navegación web scrapeada (menús, secciones de UI, links)
> Resultado: chunks de basura que degradan la precisión del retriever para cualquier pregunta.

**Error 2**: Indexar archivos muy grandes sin filtrar (ej: 56KB de documentación API)
> Resultado: un solo archivo domina el índice con decenas de chunks de bajo valor semántico.

**Error 3**: Re-indexar sin limpiar el índice anterior
> Resultado: duplicados que aumentan el número de chunks sin mejorar calidad.
> Solución: `indexacion.py` debe borrar el índice anterior antes de reconstruir.

---

## Relación con `fidelity_check.py`

Despues de que Chroma devuelve los chunks, `fidelity_check.py` verifica que la respuesta del LLM realmente se base en ellos:

```
Chroma devuelve chunks
      ↓
  LLM genera respuesta
      ↓
  fidelity_check.py verifica:
    - ¿hay chunks? (si no → bloquear)
    - ¿la respuesta menciona datos numéricos que no están en los chunks? → bloquear
    - ¿la similitud semántica con los chunks supera el umbral dinámico? (si no → bloquear)
      ↓
  Respuesta validada o bloqueada con mensaje de abstención
```

Este mecanismo es la principal protección contra alucinaciones del sistema.
