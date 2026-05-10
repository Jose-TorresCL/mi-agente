# tests/test_memoria_capas.py
# Tests por capa aislada: verifica cada capa de memoria de forma independiente.
# Ejecutar: python -m pytest tests/test_memoria_capas.py -v

import json
import os
import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas absolutas relativas al repo
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
MEMORY_DIR  = STORAGE_DIR / "memory"

# ---------------------------------------------------------------------------
# CAPA 1 — Hechos estructurados (profile.json, projectfacts.json, workstate.json)
# ---------------------------------------------------------------------------

class TestCapaHechosEstructurados:
    """Verifica que los JSON de memoria estructurada existen y tienen formato válido."""

    def test_profile_existe(self):
        """profile.json debe existir."""
        archivo = MEMORY_DIR / "profile.json"
        assert archivo.exists(), f"No encontrado: {archivo}"

    def test_profile_es_json_valido(self):
        """profile.json debe ser JSON válido y tener las claves mínimas."""
        archivo = MEMORY_DIR / "profile.json"
        if not archivo.exists():
            pytest.skip("profile.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert isinstance(data, dict), "profile.json debe ser un objeto JSON"
        # Claves mínimas esperadas
        for clave in ["nombre", "estilo"]:
            assert clave in data, f"Falta clave '{clave}' en profile.json"

    def test_projectfacts_existe(self):
        """projectfacts.json debe existir."""
        archivo = MEMORY_DIR / "projectfacts.json"
        assert archivo.exists(), f"No encontrado: {archivo}"

    def test_projectfacts_es_lista(self):
        """projectfacts.json debe ser una lista de hechos."""
        archivo = MEMORY_DIR / "projectfacts.json"
        if not archivo.exists():
            pytest.skip("projectfacts.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert isinstance(data, list), "projectfacts.json debe ser una lista JSON"

    def test_workstate_existe(self):
        """workstate.json debe existir."""
        archivo = MEMORY_DIR / "workstate.json"
        assert archivo.exists(), f"No encontrado: {archivo}"

    def test_workstate_tiene_claves_minimas(self):
        """workstate.json debe tener foco, siguiente y último."""
        archivo = MEMORY_DIR / "workstate.json"
        if not archivo.exists():
            pytest.skip("workstate.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        for clave in ["foco", "siguiente", "ultimo"]:
            assert clave in data, f"Falta clave '{clave}' en workstate.json"

    def test_tasks_existe(self):
        """tasks.json debe existir."""
        archivo = MEMORY_DIR / "tasks.json"
        assert archivo.exists(), f"No encontrado: {archivo}"

    def test_tasks_es_lista(self):
        """tasks.json debe ser una lista."""
        archivo = MEMORY_DIR / "tasks.json"
        if not archivo.exists():
            pytest.skip("tasks.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert isinstance(data, list), "tasks.json debe ser una lista JSON"

    def test_tasks_items_tienen_schema(self):
        """Cada tarea en tasks.json debe tener id, descripcion y estado."""
        archivo = MEMORY_DIR / "tasks.json"
        if not archivo.exists():
            pytest.skip("tasks.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        for i, tarea in enumerate(data):
            for clave in ["id", "descripcion", "estado"]:
                assert clave in tarea, f"Tarea[{i}] falta clave '{clave}'"


# ---------------------------------------------------------------------------
# CAPA 2 — Historial de conversación (memory.json)
# ---------------------------------------------------------------------------

class TestCapaHistorialConversacion:
    """Verifica que el historial de conversación tiene el formato que espera LangChain."""

    def test_memory_json_existe(self):
        """storage/memory/memory.json debe existir."""
        archivo = MEMORY_DIR / "memory.json"
        assert archivo.exists(), f"No encontrado: {archivo}"

    def test_memory_json_es_lista(self):
        """memory.json debe ser una lista de mensajes."""
        archivo = MEMORY_DIR / "memory.json"
        if not archivo.exists():
            pytest.skip("memory.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert isinstance(data, list), "memory.json debe ser una lista JSON (formato LangChain)"

    def test_memory_mensajes_tienen_type_y_data(self):
        """
        Cada mensaje debe tener 'type' (human/ai) y 'data.content'.
        Este test captura el bug histórico donde memory.json tenía formato
        incorrecto y causaba TypeError: string indices must be integers.
        """
        archivo = MEMORY_DIR / "memory.json"
        if not archivo.exists():
            pytest.skip("memory.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        if not data:
            pytest.skip("memory.json está vacío")
        for i, msg in enumerate(data):
            assert "type" in msg, f"Mensaje[{i}] falta 'type'"
            assert msg["type"] in ("human", "ai"), f"Mensaje[{i}] type debe ser 'human' o 'ai'"
            assert "data" in msg, f"Mensaje[{i}] falta 'data'"
            assert "content" in msg["data"], f"Mensaje[{i}] falta 'data.content'"

    def test_memory_no_supera_limite(self):
        """El historial no debe tener más de 200 mensajes (si llega a eso, algo falla)."""
        archivo = MEMORY_DIR / "memory.json"
        if not archivo.exists():
            pytest.skip("memory.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert len(data) <= 200, f"memory.json tiene {len(data)} mensajes. ¿Se está acumulando sin límite?"


# ---------------------------------------------------------------------------
# CAPA 3 — Vectorstore Chroma (existencia y accesibilidad)
# ---------------------------------------------------------------------------

class TestCapaVectorstore:
    """Verifica que el vectorstore Chroma existe y tiene contenido indexado."""

    def test_storage_rag_existe(self):
        """El directorio storage/rag debe existir."""
        rag_dir = STORAGE_DIR / "rag"
        assert rag_dir.exists(), f"No encontrado: {rag_dir}. ¿Se ejecutó indexar_documentos.py?"

    def test_chroma_tiene_archivos(self):
        """El directorio storage/rag debe tener archivos de Chroma (no estar vacío)."""
        rag_dir = STORAGE_DIR / "rag"
        if not rag_dir.exists():
            pytest.skip("storage/rag no existe")
        archivos = list(rag_dir.rglob("*"))
        assert len(archivos) > 0, "storage/rag está vacío. Ejecuta python indexar_documentos.py"

    def test_chroma_carga_sin_error(self):
        """Chroma debe poder cargarse desde disco sin lanzar excepciones."""
        pytest.importorskip("langchain_chroma", reason="langchain-chroma no instalado")
        pytest.importorskip("langchain_ollama", reason="langchain-ollama no instalado")

        from langchain_chroma import Chroma
        from langchain_ollama import OllamaEmbeddings

        rag_dir = STORAGE_DIR / "rag"
        if not rag_dir.exists():
            pytest.skip("storage/rag no existe")

        try:
            embeddings = OllamaEmbeddings(
                model="nomic-embed-text",
                base_url="http://localhost:11434",
            )
            vs = Chroma(
                persist_directory=str(rag_dir),
                embedding_function=embeddings,
            )
            count = vs._collection.count()
            assert count > 0, f"Chroma cargó pero tiene 0 documentos. ¿Se indexaron los archivos?"
        except Exception as e:
            pytest.fail(f"Chroma no pudo cargarse: {e}")

    def test_chroma_retriever_retorna_docs(self):
        """El retriever debe retornar al menos 1 documento para una pregunta de prueba."""
        pytest.importorskip("langchain_chroma")
        pytest.importorskip("langchain_ollama")

        from langchain_chroma import Chroma
        from langchain_ollama import OllamaEmbeddings

        rag_dir = STORAGE_DIR / "rag"
        if not rag_dir.exists():
            pytest.skip("storage/rag no existe")

        try:
            embeddings = OllamaEmbeddings(model="nomic-embed-text", base_url="http://localhost:11434")
            vs = Chroma(persist_directory=str(rag_dir), embedding_function=embeddings)
            retriever = vs.as_retriever(search_kwargs={"k": 3})
            docs = retriever.invoke("¿qué es el router?")
            assert len(docs) >= 1, "El retriever retornó 0 documentos para una pregunta simple"
        except Exception as e:
            pytest.fail(f"El retriever falló: {e}")


# ---------------------------------------------------------------------------
# CAPA 4 — MemoryStore (build_structured_memory_context)
# ---------------------------------------------------------------------------

class TestCapaMemoryStore:
    """Verifica que memorystore.py funciona correctamente de forma aislada."""

    def test_memorystore_importable(self):
        """app/memory_store.py (o memory/store.py) debe poder importarse sin error."""
        try:
            import app.memory_store as ms  # ajusta si tu ruta es diferente
        except ImportError:
            try:
                import app.memory.store as ms
            except ImportError:
                pytest.skip("No se encontró el módulo memory_store. Ajusta la ruta en el test.")

    def test_build_context_retorna_string(self):
        """build_structured_memory_context() debe retornar un string no vacío."""
        try:
            from app.memory_store import build_structured_memory_context
        except ImportError:
            try:
                from app.memory.store import build_structured_memory_context
            except ImportError:
                pytest.skip("No se encontró build_structured_memory_context. Ajusta la ruta en el test.")

        resultado = build_structured_memory_context()
        assert isinstance(resultado, str), "build_structured_memory_context debe retornar str"
        assert len(resultado) > 0, "build_structured_memory_context retornó string vacío"

    def test_build_context_no_lanza_excepcion_si_faltan_json(self, tmp_path, monkeypatch):
        """
        Si algún JSON de memoria no existe, build_structured_memory_context
        NO debe lanzar excepción — debe degradarse con gracia.
        """
        try:
            import app.memory_store as ms
        except ImportError:
            try:
                import app.memory.store as ms
            except ImportError:
                pytest.skip("Módulo no encontrado")

        # Apuntar al directorio temporal (sin JSONs)
        monkeypatch.setattr(ms, "MEMORY_DIR", tmp_path, raising=False)
        try:
            resultado = ms.build_structured_memory_context()
            assert isinstance(resultado, str)
        except Exception as e:
            pytest.fail(f"build_structured_memory_context lanzó excepción con JSONs ausentes: {e}")


# ---------------------------------------------------------------------------
# CAPA 5 — Router
# ---------------------------------------------------------------------------

class TestCapaRouter:
    """Verifica que el router clasifica correctamente los tipos de preguntas."""

    def test_router_importable(self):
        """app/router.py debe poder importarse sin error."""
        pytest.importorskip("app.router", reason="app/router.py no encontrado")

    def test_router_pregunta_documental_retorna_rag(self):
        """Preguntas sobre código/conceptos deben clasificarse como 'rag'."""
        try:
            from app.router import clasificar
        except ImportError:
            pytest.skip("Función 'clasificar' no encontrada en app.router")

        resultado = clasificar("¿qué es el retriever en LangChain?")
        assert resultado == "rag", f"Esperado 'rag', got '{resultado}'"

    def test_router_pregunta_estado_retorna_memoria(self):
        """Preguntas sobre estado del proyecto deben clasificarse como 'memoria'."""
        try:
            from app.router import clasificar
        except ImportError:
            pytest.skip("Función 'clasificar' no encontrada en app.router")

        resultado = clasificar("¿en qué fase estamos?")
        assert resultado in ("memoria", "structured"), f"Esperado 'memoria', got '{resultado}'"

    def test_router_no_retorna_none(self):
        """El router nunca debe retornar None para ninguna entrada."""
        try:
            from app.router import clasificar
        except ImportError:
            pytest.skip("Función 'clasificar' no encontrada en app.router")

        preguntas = [
            "¿hola?",
            "dime algo",
            "¿qué es MemGPT?",
            "siguiente tarea",
            "",
        ]
        for p in preguntas:
            resultado = clasificar(p)
            assert resultado is not None, f"El router retornó None para la pregunta: '{p}'"
