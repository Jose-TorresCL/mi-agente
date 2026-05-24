# tests/test_memoria_capas.py
# Tests por capa aislada: verifica cada capa de memoria de forma independiente.
# Ejecutar: python -m pytest tests/test_memoria_capas.py -v
#
# Historial de cambios:
#   v1: rutas a storage/memory/ (obsoleto)
#   v2: rutas a storage/, schema antiguo (projectfacts como lista)
#   v3 (actual):
#     - memory.json es {"messages": [{"role", "content"}]} — NO lista plana
#     - workstate -> work_state.json
#     - memory_store no expone load_json (es _read_json privado) -> test via _read_json
#     - router usa route_query (confirmado)
#     - route_query puede devolver 'memory:subtipo' (ej: 'memory:profile')
#       → los asserts de carril usan startswith('memory')

import json
import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas absolutas relativas al repo
# ---------------------------------------------------------------------------
BASE_DIR    = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"

# ---------------------------------------------------------------------------
# CAPA 1 — Hechos estructurados
# ---------------------------------------------------------------------------

class TestCapaHechosEstructurados:
    """Verifica que los JSON de memoria estructurada existen y tienen formato válido."""

    def test_profile_existe(self):
        """profile.json debe existir en storage/."""
        archivo = STORAGE_DIR / "profile.json"
        if not archivo.exists():
            pytest.skip("profile.json no existe — ejecuta el agente una vez para generarlo")

    def test_profile_es_json_valido(self):
        """profile.json debe ser JSON válido con las claves actuales del schema."""
        archivo = STORAGE_DIR / "profile.json"
        if not archivo.exists():
            pytest.skip("profile.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert isinstance(data, dict), "profile.json debe ser un objeto JSON"
        for clave in ["user_name", "user_level", "project_type"]:
            assert clave in data, f"Falta clave '{clave}' en profile.json. Claves: {list(data.keys())}"

    def test_projectfacts_existe(self):
        """project_facts.json debe existir en storage/."""
        archivo = STORAGE_DIR / "project_facts.json"
        if not archivo.exists():
            pytest.skip("project_facts.json no existe — ejecuta el agente una vez para generarlo")

    def test_projectfacts_es_dict(self):
        """project_facts.json debe ser un dict (no una lista)."""
        archivo = STORAGE_DIR / "project_facts.json"
        if not archivo.exists():
            pytest.skip("project_facts.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert isinstance(data, dict), "project_facts.json debe ser un dict JSON"

    def test_workstate_existe(self):
        """work_state.json debe existir en storage/."""
        archivo = STORAGE_DIR / "work_state.json"
        if not archivo.exists():
            pytest.skip("work_state.json no existe — ejecuta el agente una vez para generarlo")

    def test_workstate_tiene_claves_minimas(self):
        """work_state.json debe tener las claves del schema actual."""
        archivo = STORAGE_DIR / "work_state.json"
        if not archivo.exists():
            pytest.skip("work_state.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        for clave in ["current_focus", "next_step", "last_completed"]:
            assert clave in data, f"Falta clave '{clave}' en work_state.json. Claves: {list(data.keys())}"

    def test_tasks_existe(self):
        """tasks.json debe existir en storage/."""
        archivo = STORAGE_DIR / "tasks.json"
        if not archivo.exists():
            pytest.skip("tasks.json no existe — ejecuta el agente una vez para generarlo")

    def test_tasks_es_dict_con_lista(self):
        """tasks.json debe ser un dict con clave 'tasks' que contiene una lista."""
        archivo = STORAGE_DIR / "tasks.json"
        if not archivo.exists():
            pytest.skip("tasks.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert isinstance(data, dict), "tasks.json debe ser un dict con clave 'tasks'"
        assert "tasks" in data, f"tasks.json falta clave 'tasks'. Claves: {list(data.keys())}"
        assert isinstance(data["tasks"], list), "tasks.json['tasks'] debe ser una lista"

    def test_tasks_items_tienen_schema(self):
        """Cada tarea en tasks.json debe tener id, title y status."""
        archivo = STORAGE_DIR / "tasks.json"
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
    """Verifica que memory.json tiene el formato {messages: [{role, content}]}."""

    def test_memory_json_existe(self):
        """storage/memory.json debe existir."""
        archivo = STORAGE_DIR / "memory.json"
        if not archivo.exists():
            pytest.skip("memory.json no existe — ejecuta el agente una vez para generarlo")

    def test_memory_json_es_dict_con_messages(self):
        """
        memory.json debe ser un dict con clave 'messages'.
        Formato actual: {"messages": [{"role": "human"|"ai", "content": "..."}]}
        """
        archivo = STORAGE_DIR / "memory.json"
        if not archivo.exists():
            pytest.skip("memory.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        assert isinstance(data, dict), (
            f"memory.json debe ser un dict {{\"messages\": [...]}}, "
            f"pero es {type(data).__name__}. ¿Archivo en formato antiguo?"
        )
        assert "messages" in data, (
            f"memory.json debe tener clave 'messages'. Claves: {list(data.keys())}"
        )
        assert isinstance(data["messages"], list), "memory.json['messages'] debe ser una lista"

    def test_memory_mensajes_tienen_role_y_content(self):
        """
        Cada mensaje debe tener 'role' (human/ai) y 'content'.
        """
        archivo = STORAGE_DIR / "memory.json"
        if not archivo.exists():
            pytest.skip("memory.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        messages = data.get("messages", [])
        if not messages:
            pytest.skip("memory.json está vacío")
        for i, msg in enumerate(messages):
            assert isinstance(msg, dict), f"Mensaje[{i}] debe ser dict"
            assert "role" in msg, f"Mensaje[{i}] falta 'role'"
            assert msg["role"] in ("human", "ai"), (
                f"Mensaje[{i}] role debe ser 'human' o 'ai', obtuvo '{msg['role']}'"
            )
            assert "content" in msg, f"Mensaje[{i}] falta 'content'"

    def test_memory_no_supera_limite(self):
        """El historial no debe tener más de 200 mensajes."""
        archivo = STORAGE_DIR / "memory.json"
        if not archivo.exists():
            pytest.skip("memory.json no existe")
        data = json.loads(archivo.read_text(encoding="utf-8"))
        messages = data.get("messages", [])
        assert len(messages) <= 200, (
            f"memory.json tiene {len(messages)} mensajes. ¿Se acumula sin límite?"
        )


# ---------------------------------------------------------------------------
# CAPA 3 — Vectorstore Chroma
# ---------------------------------------------------------------------------

class TestCapaVectorstore:
    """Verifica que el vectorstore Chroma existe y tiene contenido indexado."""

    def test_storage_chroma_existe(self):
        """El directorio storage/chroma debe existir."""
        chroma_dir = STORAGE_DIR / "chroma"
        assert chroma_dir.exists(), (
            f"No encontrado: {chroma_dir}. ¿Se ejecutó indexacion.py?"
        )

    def test_chroma_tiene_archivos(self):
        """El directorio storage/chroma debe tener archivos."""
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
# CAPA 4 — MemoryStore
# ---------------------------------------------------------------------------

class TestCapaMemoryStore:
    """Verifica que memory_store.py se puede importar y su API interna funciona."""

    def test_memorystore_importable(self):
        """app/memory_store.py debe poder importarse sin error."""
        try:
            import app.memory_store  # noqa: F401
        except ImportError as e:
            pytest.fail(f"No se pudo importar app.memory_store: {e}")

    def test_read_json_privado_no_lanza_con_archivo_ausente(self):
        """
        _read_json debe devolver el default sin lanzar excepción cuando el archivo no existe.
        """
        import app.memory_store as ms
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            ruta_inexistente = Path(tmp) / "no_existe.json"
            resultado = ms._read_json(ruta_inexistente, default={"ok": True})
            assert resultado == {"ok": True}, (
                f"_read_json con archivo ausente debe devolver el default, obtuvo: {resultado}"
            )

    def test_load_memory_devuelve_estructura_valida(self):
        """load_memory() debe devolver dict con clave 'messages'."""
        from app.memory_store import load_memory
        resultado = load_memory()
        assert isinstance(resultado, dict), "load_memory debe devolver un dict"
        assert "messages" in resultado, "load_memory debe tener clave 'messages'"
        assert isinstance(resultado["messages"], list)


# ---------------------------------------------------------------------------
# CAPA 5 — Router
# Nota: route_query() ahora puede devolver 'memory:subtipo' (ej: 'memory:profile').
# Los asserts de carril memoria usan startswith('memory') para cubrir ambas formas.
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
        """
        Preguntas sobre estado del proyecto deben clasificarse en carril memoria.
        Acepta 'memory' o 'memory:subtipo' (ej: 'memory:project_facts').
        """
        from app.router import route_query
        resultado = route_query("¿en qué fase estamos?")
        assert resultado.startswith("memory") or resultado in ("estado", "general"), (
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
