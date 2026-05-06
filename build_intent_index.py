"""build_intent_index.py — Fase 3B

Qué hace:
  Lee data/intent_examples.json, embede cada frase con nomic-embed-text
  y las guarda en storage/intent_index (colección Chroma separada del RAG).

Cuándo ejecutarlo:
  - La primera vez (construir el índice desde cero)
  - Cada vez que agregues o edites frases en intent_examples.json
  NO es necesario ejecutarlo con git pull si no tocaste intent_examples.json.

Uso:
  python build_intent_index.py

Salida esperada:
  INFO: 88 ejemplos cargados desde data/intent_examples.json
  INFO: Embebiendo frases con nomic-embed-text...
  INFO: [88/88] completado
  ✅ Índice de intenciones guardado en storage/intent_index (88 vectores)
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document


# ─────────────────────────────────────────────
EXAMPLES_PATH  = Path("data/intent_examples.json")
INTENT_DIR     = Path("storage/intent_index")
EMBED_MODEL    = "nomic-embed-text"
OLLAMA_URL     = "http://localhost:11434"
# ─────────────────────────────────────────────


def load_examples() -> list[dict]:
    """Lee intent_examples.json eliminando comentarios estilo // ...

    JSON estándar no permite comentarios, pero los hemos añadido
    como líneas que empiezan con // para documentar los carriles.
    Esta función los filtra antes de parsear.
    """
    raw = EXAMPLES_PATH.read_text(encoding="utf-8")
    lines = [line for line in raw.splitlines() if not line.strip().startswith("/")]
    return json.loads("\n".join(lines))


def build_documents(examples: list[dict]) -> list[Document]:
    """Convierte cada ejemplo en un Document de LangChain.

    El texto es la frase, el metadato 'lane' es la etiqueta de carril.
    Chroma almacena el texto como contenido y el metadato para filtrarlo.
    """
    return [
        Document(
            page_content=ex["text"],
            metadata={"lane": ex["lane"]},
        )
        for ex in examples
    ]


def main() -> None:
    # ─ 1. Validar que existen los archivos necesarios ────────────
    if not EXAMPLES_PATH.exists():
        print(f"ERROR: No se encontró {EXAMPLES_PATH}")
        print("       Ejecuta primero: git pull origin main")
        return

    # ─ 2. Cargar ejemplos ──────────────────────────────
    examples = load_examples()
    print(f"INFO: {len(examples)} ejemplos cargados desde {EXAMPLES_PATH}")

    docs = build_documents(examples)

    # ─ 3. Borrar índice anterior (rebuild limpio) ──────────────
    if INTENT_DIR.exists():
        shutil.rmtree(INTENT_DIR)
        print(f"INFO: Índice anterior eliminado: {INTENT_DIR}")

    INTENT_DIR.mkdir(parents=True, exist_ok=True)

    # ─ 4. Embedear y guardar en Chroma ─────────────────────
    print(f"INFO: Embebiendo frases con {EMBED_MODEL}...")
    print("      (tarda ~10-20 segundos si Ollama ya está caliente)")

    embeddings = OllamaEmbeddings(
        model=EMBED_MODEL,
        base_url=OLLAMA_URL,
    )

    # Chroma.from_documents embebe todo en un solo batch y persiste
    Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory=str(INTENT_DIR),
        collection_name="intent_index",
    )

    print(f"INFO: [✓] {len(docs)}/{len(docs)} completado")
    print(f"✅ Índice de intenciones guardado en {INTENT_DIR} ({len(docs)} vectores)")


if __name__ == "__main__":
    main()
