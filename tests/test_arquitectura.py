# tests/test_arquitectura.py
"""
Test arquitectural del proyecto mi-agente.

Propósito: verificar que la ESTRUCTURA del proyecto es correcta,
not el comportamiento en tiempo de ejecución.

Responde estas preguntas:
  1. ¿Los archivos y carpetas requeridos existen?
  2. ¿Los módulos se importan sin errores de sintaxis o dependencias?
  3. ¿Los JSON de memoria tienen el schema correcto?
  4. ¿La API pública de cada módulo expone lo que se espera?
  5. ¿Los docs de referencia tienen contenido real (> 500 bytes)?

NO requiere Ollama ni Chroma corriendo — todo es import y lectura de archivos.

Ejecutar:
    python -m pytest tests/test_arquitectura.py -v
"""

import inspect
import json
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 1. Estructura de archivos y carpetas
# ---------------------------------------------------------------------------

class TestEstructuraCarpetas:
    """Las carpetas esenciales del proyecto existen."""

    CARPETAS = [
        "app",
        "data/docs",
        "data/docs/referencia",
        "storage",
        "tests",
    ]

    @pytest.mark.parametrize("carpeta", CARPETAS)
    def test_carpeta_existe(self, carpeta):
        assert (BASE_DIR / carpeta).is_dir(), f"Falta carpeta: {carpeta}/"


class TestArchivosRequeridos:
    """Los archivos clave del proyecto existen."""

    ARCHIVOS = [
        # Entry points
        "chat.py",
        "indexacion.py",          # renombrado desde indexar_documentos.py
        # Paquete app
        "app/__init__.py",
        "app/chat_core.py",
        "app/memory_manager.py",
        "app/memory_context.py",
        "app/memory_store.py",
        "app/rag_engine.py",
        "app/router.py",
        "app/fidelity_check.py",
        "app/config.py",
        # Docs de referencia mínimas
        "data/docs/referencia/langchain-rag-concepto.md",
        "data/docs/referencia/langchain-retriever.md",
        "data/docs/referencia/langchain-embeddings.md",
        "data/docs/referencia/langchain-text-splitters.md",
    ]

    @pytest.mark.parametrize("archivo", ARCHIVOS)
    def test_archivo_existe(self, archivo):
        assert (BASE_DIR / archivo).is_file(), f"Falta archivo: {archivo}"


class TestArchivosNoVacios:
    """Los docs de referencia tienen contenido real (> 500 bytes).

    Detecta el bug histórico donde el WebBaseLoader descargaba
    archivos de 14 bytes (solo el título, sin contenido).
    """

    DOCS = [
        "data/docs/referencia/langchain-rag-concepto.md",
        "data/docs/referencia/langchain-retriever.md",
        "data/docs/referencia/langchain-embeddings.md",
        "data/docs/referencia/langchain-text-splitters.md",
    ]

    @pytest.mark.parametrize("archivo", DOCS)
    def test_doc_no_vacio(self, archivo):
        ruta = BASE_DIR / archivo
        if not ruta.exists():
            pytest.skip(f"{archivo} no existe")
        size = ruta.stat().st_size
        assert size > 500, (
            f"{archivo} tiene {size} bytes — parece vacío. "
            f"Ejecuta 'git pull origin main' para obtener el contenido real."
        )


# ---------------------------------------------------------------------------
# 2. Módulos Python: import sin errores
# ---------------------------------------------------------------------------

class TestImportModulos:
    """Todos los módulos del paquete app importan sin errores.

    Un fallo aquí significa error de sintaxis, import circular
    o dependencia faltante — antes de siquiera ejecutar el agente.
    """

    MODULOS = [
        "app",
        "app.config",
        "app.logger",
        "app.memory_store",
        "app.memory_context",
        "app.memory_manager",
        "app.router",
        "app.fidelity_check",
        "app.prompts",
    ]

    @pytest.mark.parametrize("modulo", MODULOS)
    def test_importable(self, modulo):
        try:
            __import__(modulo)
        except ImportError as e:
            pytest.fail(f"ImportError en '{modulo}': {e}")
        except SyntaxError as e:
            pytest.fail(f"SyntaxError en '{modulo}': {e}")


# ---------------------------------------------------------------------------
# 3. API pública de memory_manager (ADR-004)
# ---------------------------------------------------------------------------

class TestMemoryManagerAPI:
    """memory_manager expone la API completa incluyendo get_selective_context.

    Estos tests no leen ni escriben storage/ — solo verifican
    que las funciones existen y son callables.
    """

    def _mm(self):
        import app.memory_manager as mm
        return mm

    FUNCIONES_PUBLICAS = [
        "get_full_context",
        "get_selective_context",   # Nueva — ADR-004
        "get_working_context",
        "get_semantic_context",
        "get_episodic_context",
        "get_profile",
        "get_project_facts",
        "get_tasks",
        "get_work_state",
        "save_fact",
        "update_state",
        "create_task",
        "complete_task",
        "record_episode",
    ]

    @pytest.mark.parametrize("func", FUNCIONES_PUBLICAS)
    def test_funcion_existe(self, func):
        mm = self._mm()
        assert hasattr(mm, func), (
            f"memory_manager no expone '{func}'. "
            f"Verifica el último git pull."
        )
        assert callable(getattr(mm, func)), f"'{func}' existe pero no es callable."

    def test_get_selective_context_acepta_route(self):
        """get_selective_context(route) acepta un string y devuelve string."""
        mm = self._mm()
        for carril in ("rag", "estado", "memoria", "general", "save_fact"):
            resultado = mm.get_selective_context(carril)
            assert isinstance(resultado, str), (
                f"get_selective_context('{carril}') devolver {type(resultado)}, "
                f"se esperaba str."
            )

    def test_get_selective_context_rag_es_mas_corto(self):
        """El carril 'rag' debe inyectar menos texto que el contexto completo.

        Fundamento ADR-004: RAG no necesita historial de trabajo ni hechos
        del proyecto — los chunks de Chroma ya aportan el contexto técnico.
        """
        mm = self._mm()
        ctx_rag  = mm.get_selective_context("rag")
        ctx_full = mm.get_full_context()
        # Solo verificamos si hay datos — si storage/ está vacío, skip
        if not ctx_full.strip():
            pytest.skip("storage/ está vacío, no se puede comparar longitudes")
        assert len(ctx_rag) <= len(ctx_full), (
            f"Carril 'rag' ({len(ctx_rag)} chars) debería ser <= "
            f"contexto completo ({len(ctx_full)} chars)."
        )


# ---------------------------------------------------------------------------
# 4. API de fidelity_check: acepta question= (umbral dinámico ADR-004)
# ---------------------------------------------------------------------------

class TestFidelityCheckAPI:
    """verify_fidelity acepta el parámetro question= para umbral dinámico."""

    def test_verify_fidelity_acepta_question_kwarg(self):
        """Verifica que la firma de verify_fidelity incluye 'question'.

        Sin ejecutar el LLM — solo inspección de la firma.
        """
        from app.fidelity_check import verify_fidelity
        sig = inspect.signature(verify_fidelity)
        assert "question" in sig.parameters, (
            "verify_fidelity no tiene parámetro 'question'. "
            "El umbral dinámico de ADR-004 no está conectado. "
            "Revisa app/fidelity_check.py."
        )

    def test_no_evidence_msg_existe(self):
        """La constante NO_EVIDENCE_MSG existe y es string no vacío."""
        from app.fidelity_check import NO_EVIDENCE_MSG
        assert isinstance(NO_EVIDENCE_MSG, str)
        assert len(NO_EVIDENCE_MSG) > 10, "NO_EVIDENCE_MSG parece vacío."


# ---------------------------------------------------------------------------
# 5. API de chat_core: handle_query y build_memory
# ---------------------------------------------------------------------------

class TestChatCoreAPI:
    """chat_core expone las funciones públicas esperadas."""

    def test_handle_query_existe(self):
        from app.chat_core import handle_query
        assert callable(handle_query)

    def test_handle_query_firma(self):
        """handle_query acepta (user_input, vectordb, chat_history)."""
        from app.chat_core import handle_query
        sig = inspect.signature(handle_query)
        params = list(sig.parameters)
        assert "user_input"   in params, "handle_query falta 'user_input'"
        assert "vectordb"     in params, "handle_query falta 'vectordb'"
        assert "chat_history" in params, "handle_query falta 'chat_history'"

    def test_build_memory_importable(self):
        from app.chat_core import build_memory
        assert callable(build_memory)


# ---------------------------------------------------------------------------
# 6. Contratos de datos: los JSON de memoria tienen el schema real
# ---------------------------------------------------------------------------

class TestSchemaMemoria:
    """Los JSON de storage/memory/ tienen las claves correctas.

    Usa las claves reales del proyecto (user_name, current_focus, etc.).
    Todos los tests hacen skip si el archivo no existe — esto permite
    correr el test arquitectural en un entorno sin storage/ inicializado.
    """

    def _cargar(self, nombre: str):
        ruta = BASE_DIR / "storage" / nombre
        if not ruta.exists():
            pytest.skip(f"storage/{nombre} no existe")
        return json.loads(ruta.read_text(encoding="utf-8"))

    def test_profile_schema(self):
        data = self._cargar("profile.json")
        assert isinstance(data, dict)
        for clave in ("user_name", "user_level", "project_type"):
            assert clave in data, (
                f"profile.json falta '{clave}'. "
                f"Claves encontradas: {list(data.keys())}"
            )

    def test_workstate_schema(self):
        data = self._cargar("workstate.json")
        assert isinstance(data, dict)
        for clave in ("current_focus", "next_step", "last_completed"):
            assert clave in data, (
                f"workstate.json falta '{clave}'. "
                f"Claves encontradas: {list(data.keys())}"
            )

    def test_tasks_schema(self):
        data = self._cargar("tasks.json")
        assert isinstance(data, dict), "tasks.json debe ser dict con clave 'tasks'"
        assert "tasks" in data, "tasks.json debe tener clave 'tasks'"
        for i, t in enumerate(data.get("tasks", [])):
            for clave in ("id", "title", "status"):
                assert clave in t, f"tasks[{i}] falta '{clave}'"

    def test_project_facts_es_dict(self):
        data = self._cargar("project_facts.json")
        assert isinstance(data, dict), "project_facts.json debe ser un dict"
        assert len(data) > 0, "project_facts.json está vacío — ¿se inicializó?"

    def test_project_facts_encoding_utf8(self):
        """Verifica que project_facts.json no tiene tildes corruptas.

        Bug anterior: json.dump sin ensure_ascii=False generaba \\u00f3
        en vez de 'ó'. Este test detecta esa regresión.
        """
        ruta = BASE_DIR / "storage" / "project_facts.json"
        if not ruta.exists():
            pytest.skip("project_facts.json no existe")
        contenido = ruta.read_text(encoding="utf-8")
        assert "\\u00" not in contenido, (
            "project_facts.json tiene tildes corruptas (ej: \\u00f3 en vez de ó). "
            "Asegúrate de llamar json.dump con ensure_ascii=False."
        )


# ---------------------------------------------------------------------------
# 7. Inventario de documentación RAG
# ---------------------------------------------------------------------------

class TestInventarioDocumentacion:
    """El corpus de RAG tiene los documentos mínimos para cada tema."""

    TEMAS = {
        "LangChain RAG":      "data/docs/referencia/langchain-rag-concepto.md",
        "LangChain Retriever": "data/docs/referencia/langchain-retriever.md",
        "Text Splitters":     "data/docs/referencia/langchain-text-splitters.md",
        "Embeddings":         "data/docs/referencia/langchain-embeddings.md",
        "Chroma":             "data/docs/referencia/chroma-queries.md",
        "Ollama API":         "data/docs/referencia/ollama-api.md",
        "Memoria Agentes":    "data/docs/referencia/memoria_agentes_resumen.md",
    }

    @pytest.mark.parametrize("tema,archivo", TEMAS.items())
    def test_tema_tiene_documento(self, tema, archivo):
        ruta = BASE_DIR / archivo
        assert ruta.is_file(), f"Tema '{tema}' sin documento en RAG. Falta: {archivo}"
        assert ruta.stat().st_size > 200, (
            f"Documento '{tema}' existe pero tiene solo {ruta.stat().st_size} bytes."
        )
