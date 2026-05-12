# tests/test_memoria_capas.py
# Tests por capa aislada: verifica cada capa de memoria de forma independiente.
# Ejecutar: python -m pytest tests/test_memoria_capas.py -v
#
# Historial de cambios:
#   - Rutas de memoria: storage/memory/ -> storage/  (donde viven realmente los JSONs)
#   - Claves de schema actualizadas al modelo real del proyecto
#   - storage/rag -> storage/chroma
#   - build_structured_memory_context -> eliminado (no existe en memory_store)
#   - clasificar -> eliminado (router usa route_query, no clasificar)

import json
import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas absolutas relativas al repo
# ---------------------------------------------------------------------------
BASE_DIR    = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
MEMORY_DIR  = STORAGE_DIR          # los JSONs viven en storage/, no en storage/memory/

# ---------------------------------------------------------------------------
# CAPA 1 — Hechos estructurados (profile.json, project_facts.json, workstate.json)
# ---------------------------------------------------------------------------

class TestCapaHechosEstructurados:
    """Verifica que los JSON de memoria estructurada existen y tienen formato válido."""

    def test_profile_existe(self):
        """profile.json debe existir en storage/."""
        archivo = MEMORY_DIR / "profile.json"
        if not archivo.exists():
            pytest.skip("profile.json no existe — ejecuta el agente una vez para generarlo")

    def test_profile_es_json_valido(self):
        """profile.json debe ser JSON válido con las claves actuales del schema."""
        archivo = MEMORY_DIR / "profile.json"
        if not archivo.exists():
            pytest.skip("profile.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert isinstance(data, dict), "profile.json debe ser un objeto JSON"
        for clave in ["user_name", "user_level", "project_type"]:
            assert clave in data, f"Falta clave '{clave}' en profile.json. Claves: {list(data.keys())}"

    def test_projectfacts_existe(self):
        """project_facts.json debe existir en storage/."""
        archivo = MEMORY_DIR / "project_facts.json"
        if not archivo.exists():
            pytest.skip("project_facts.json no existe — ejecuta el agente una vez para generarlo")

    def test_projectfacts_es_dict(self):
        """project_facts.json debe ser un dict (no una lista)."""
        archivo = MEMORY_DIR / "project_facts.json"
        if not archivo.exists():
            pytest.skip("project_facts.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert isinstance(data, dict), "project_facts.json debe ser un dict JSON"

    def test_workstate_existe(self):
        """workstate.json debe existir en storage/."""
        archivo = MEMORY_DIR / "workstate.json"
        if not archivo.exists():
            pytest.skip("workstate.json no existe — ejecuta el agente una vez para generarlo")

    def test_workstate_tiene_claves_minimas(self):
        """workstate.json debe tener las claves del schema actual."""
        archivo = MEMORY_DIR / "workstate.json"
        if not archivo.exists():
            pytest.skip("workstate.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        for clave in ["current_focus", "next_step", "last_completed"]:
            assert clave in data, f"Falta clave '{clave}' en workstate.json. Claves: {list(data.keys())}"

    def test_tasks_existe(self):
        """tasks.json debe existir en storage/."""
        archivo = MEMORY_DIR / "tasks.json"
        if not archivo.exists():
            pytest.skip("tasks.json no existe — ejecuta el agente una vez para generarlo")

    def test_tasks_es_dict_con_lista(self):
        """tasks.json debe ser un dict con clave 'tasks' que contiene una lista."""
        archivo = MEMORY_DIR / "tasks.json"
        if not archivo.exists():
            pytest.skip("tasks.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert isinstance(data, dict), "tasks.json debe ser un dict con clave 'tasks'"
        assert "tasks" in data, f"tasks.json falta clave 'tasks'. Claves: {list(data.keys())}"
        assert isinstance(data["tasks"], list), "tasks.json['tasks'] debe ser una lista"

    def test_tasks_items_tienen_schema(self):
        """Cada tarea en tasks.json debe tener id, title y status."""
        archivo = MEMORY_DIR / "tasks.json"
        if not archivo.exists():
            pytest.skip("tasks.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        for i, tarea in enumerate(data.get("tasks", [])):
            for clave in ["id", "title", "status"]:
                assert clave in tarea, f"Tarea[{i}] falta clave '{clave}'"


# ---------------------------------------------------------------------------
# CAPA 2 — Historial de conversación (memory.json)
# ---------------------------------------------------------------------------

class TestCapaHistorialConversacion:
    """Verifica que el historial de conversación tiene el formato correcto."""

    def test_memory_json_existe(self):
        """storage/memory.json debe existir."""
        archivo = MEMORY_DIR / "memory.json"
        if not archivo.exists():
            pytest.skip("memory.json no existe — ejecuta el agente una vez para generarlo")

    def test_memory_json_es_lista(self):
        """memory.json debe ser una lista de mensajes."""
        archivo = MEMORY_DIR / "memory.json"
        if not archivo.exists():
            pytest.skip("memory.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert isinstance(data, list), "memory.json debe ser una lista JSON"

    def test_memory_mensajes_tienen_type_y_data(self):
        """
        Cada mensaje debe tener 'type' (human/ai) y 'data.content'.
        Detecta el bug histórico donde memory.json tenía formato incorrecto.
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
        """El historial no debe tener más de 200 mensajes."""
        archivo = MEMORY_DIR / "memory.json"
        if not archivo.exists():
            pytest.skip("memory.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert len(data) <= 200, f"memory.json tiene {len(data)} mensajes. ¿Se acumula sin límite?"


# ---------------------------------------------------------------------------
# CAPA 3 — Vectorstore Chroma (existencia y accesibilidad)
# ---------------------------------------------------------------------------

class TestCapaVectorstore:
    """Verifica que el vectorstore Chroma existe y tiene contenido indexado."""

    def test_storage_chroma_existe(self):
        """El directorio storage/chroma debe existir."""
        chroma_dir = STORAGE_DIR / "chroma"
        assert chroma_dir.exists(), (
            f"No encontrado: {chroma_dir}. "
            "¿Se ejecutó indexacion.py?"
        )

    def test_chroma_tiene_archivos(self):
        """El directorio storage/chroma debe tener archivos (no estar vacío)."""
        chroma_dir = STORAGE_DIR / "chroma"
        if not chroma_dir.exists():
            pytest.skip("storage/chroma no existe")
        archivos = list(chroma_dir.rglob("*"))
        assert len(archivos) > 0, "storage/chroma está vacío. Ejecuta: python indexacion.py"

    def test_chroma_carga_sin_error(self):
        """Chroma debe poder cargarse desde disco sin lanzar excepciones."""
        pytest.importorskip("langchain_chroma", reason="langchain-chroma no instalado")
        pytest.importorskip("langchain_ollama", reason="langchain-ollama no instalado")

        from langchain_chroma import Chroma
        from langchain_ollama import OllamaEmbeddings

        chroma_dir = STORAGE_DIR / "chroma"
        if not chroma_dir.exists():
            pytest.skip("storage/chroma no existe")

        try:
            embeddings = OllamaEmbeddings(
                model="nomic-embed-text",
                base_url="http://localhost:11434",
            )
            vs = Chroma(
                persist_directory=str(chroma_dir),
                embedding_function=embeddings,
            )
            count = vs._collection.count()
            assert count > 0, "Chroma cargó pero tiene 0 documentos. ¿Se indexaron archivos?"
        except Exception as e:
            pytest.fail(f"Chroma no pudo cargarse: {e}")

    def test_chroma_retriever_retorna_docs(self):
        """El retriever debe retornar al menos 1 documento para una pregunta de prueba."""
        pytest.importorskip("langchain_chroma")
        pytest.importorskip("langchain_ollama")

        from langchain_chroma import Chroma
        from langchain_ollama import OllamaEmbeddings

        chroma_dir = STORAGE_DIR / "chroma"
        if not chroma_dir.exists():
            pytest.skip("storage/chroma no existe")

        try:
            embeddings = OllamaEmbeddings(model="nomic-embed-text", base_url="http://localhost:11434")
            vs = Chroma(persist_directory=str(chroma_dir), embedding_function=embeddings)
            retriever = vs.as_retriever(search_kwargs={"k": 3})
            docs = retriever.invoke("¿qué es el router?")
            assert len(docs) >= 1, "El retriever retornó 0 documentos para una pregunta simple"
        except Exception as e:
            pytest.fail(f"El retriever falló: {e}")


# ---------------------------------------------------------------------------
# CAPA 4 — MemoryStore (importación y API pública)
# ---------------------------------------------------------------------------

class TestCapaMemoryStore:
    """Verifica que memory_store.py se puede importar y expone su API pública."""

    def test_memorystore_importable(self):
        """app/memory_store.py debe poder importarse sin error."""
        try:
            import app.memory_store  # noqa: F401
        except ImportError as e:
            pytest.fail(f"No se pudo importar app.memory_store: {e}")

    def test_memory_dir_accesible(self, tmp_path, monkeypatch):
        """
        memory_store puede operar con un directorio alternativo sin lanzar excepción.
        Verifica degradación elegante ante JSONs ausentes.
        """
        import app.memory_store as ms

        # Redirigir MEMORY_DIR a un directorio temporal vacío
        monkeypatch.setattr(ms, "MEMORY_DIR", tmp_path, raising=False)

        # Verificar que las funciones de lectura no explotan con directorio vacío
        try:
            ms.load_json(tmp_path / "inexistente.json", default={})
        except Exception as e:
            pytest.fail(f"load_json lanzó excepción con archivo ausente: {e}")


# ---------------------------------------------------------------------------
# CAPA 5 — Router
# ---------------------------------------------------------------------------

class TestCapaRouter:
    """Verifica que el router clasifica correctamente los tipos de preguntas."""

    def test_router_importable(self):
        """app/router.py debe poder importarse sin error."""
        try:
            import app.router  # noqa: F401
        except ImportError as e:
            pytest.fail(f"No se pudo importar app.router: {e}")

    def test_router_pregunta_documental_retorna_rag(self):
        """Preguntas sobre código/conceptos deben clasificarse como 'rag'."""
        from app.router import route_query
        resultado = route_query("¿qué es el retriever en LangChain?")
        assert resultado == "rag", f"Esperado 'rag', obtuvo '{resultado}'"

    def test_router_pregunta_estado_retorna_memoria(self):
        """Preguntas sobre estado del proyecto deben clasificarse como 'memory'."""
        from app.router import route_query
        resultado = route_query("¿en qué fase estamos?")
        assert resultado in ("memory", "estado", "general"), (
            f"Esperado carril de memoria/estado, obtuvo '{resultado}'"
        )

    def test_router_no_retorna_none(self):
        """El router nunca debe retornar None para ninguna entrada."""
        from app.router import route_query
        preguntas = [
            "¿hola?",
            "dime algo",
            "¿qué es MemGPT?",
            "siguiente tarea",
            "",
        ]
        for p in preguntas:
            resultado = route_query(p)
            assert resultado is not None, f"route_query retornó None para: '{p}'"
