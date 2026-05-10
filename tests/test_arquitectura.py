# tests/test_arquitectura.py
# Test arquitectural: verifica la estructura del proyecto, no el comportamiento.
# Responde: ¿el proyecto tiene todo lo que debe tener?
# Ejecutar: python -m pytest tests/test_arquitectura.py -v

import json
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Estructura de archivos y carpetas
# ---------------------------------------------------------------------------

class TestEstructuraCarpetas:
    """Verifica que las carpetas esenciales del proyecto existen."""

    CARPETAS_REQUERIDAS = [
        "app",
        "data/docs",
        "data/docs/referencia",
        "storage",
        "storage/memory",
        "tests",
    ]

    @pytest.mark.parametrize("carpeta", CARPETAS_REQUERIDAS)
    def test_carpeta_existe(self, carpeta):
        ruta = BASE_DIR / carpeta
        assert ruta.is_dir(), f"Carpeta requerida no encontrada: {carpeta}/"


class TestArchivosRequeridos:
    """Verifica que los archivos clave del proyecto existen."""

    ARCHIVOS_REQUERIDOS = [
        # Entry points
        "chat.py",
        "indexar_documentos.py",
        # Módulos del paquete app
        "app/__init__.py",
        # Memoria estructurada
        "storage/memory/profile.json",
        "storage/memory/projectfacts.json",
        "storage/memory/workstate.json",
        "storage/memory/tasks.json",
        # Docs de referencia mínimas
        "data/docs/referencia/langchain-rag-concepto.md",
        "data/docs/referencia/langchain-retriever.md",
        "data/docs/referencia/langchain-embeddings.md",
        "data/docs/referencia/langchain-text-splitters.md",
        "data/docs/referencia/paper-memgpt-resumen.md",
        "data/docs/referencia/paper-lightmem-resumen.md",
    ]

    @pytest.mark.parametrize("archivo", ARCHIVOS_REQUERIDOS)
    def test_archivo_existe(self, archivo):
        ruta = BASE_DIR / archivo
        assert ruta.is_file(), f"Archivo requerido no encontrado: {archivo}"


class TestArchivosNoVacios:
    """Verifica que los archivos de referencia tienen contenido real (> 500 bytes)."""

    DOCS_REFERENCIA = [
        "data/docs/referencia/langchain-rag-concepto.md",
        "data/docs/referencia/langchain-retriever.md",
        "data/docs/referencia/langchain-embeddings.md",
        "data/docs/referencia/langchain-text-splitters.md",
        "data/docs/referencia/paper-memgpt-resumen.md",
        "data/docs/referencia/paper-lightmem-resumen.md",
    ]

    @pytest.mark.parametrize("archivo", DOCS_REFERENCIA)
    def test_doc_no_esta_vacio(self, archivo):
        """Detecta el bug histórico donde los .md se descargaban con 14 bytes."""
        ruta = BASE_DIR / archivo
        if not ruta.exists():
            pytest.skip(f"{archivo} no existe")
        size = ruta.stat().st_size
        assert size > 500, (
            f"{archivo} tiene solo {size} bytes. "
            f"Parece que se descargó vacío (bug del WebBaseLoader)."
        )


# ---------------------------------------------------------------------------
# Módulos Python: import sin errores
# ---------------------------------------------------------------------------

class TestImportModulos:
    """Verifica que los módulos principales se importan sin errores de sintaxis."""

    MODULOS = [
        "app",
        "app.router",
    ]

    @pytest.mark.parametrize("modulo", MODULOS)
    def test_modulo_importable(self, modulo):
        try:
            __import__(modulo)
        except ImportError as e:
            pytest.fail(f"No se pudo importar '{modulo}': {e}")
        except SyntaxError as e:
            pytest.fail(f"Error de sintaxis en '{modulo}': {e}")


# ---------------------------------------------------------------------------
# Contratos de datos: los JSON de memoria tienen el schema correcto
# ---------------------------------------------------------------------------

class TestSchemaMemoria:
    """Verifica los contratos de datos de los JSON de memoria."""

    def _cargar(self, nombre):
        ruta = BASE_DIR / "storage" / "memory" / nombre
        if not ruta.exists():
            pytest.skip(f"{nombre} no existe")
        return json.loads(ruta.read_text(encoding="utf-8"))

    def test_profile_schema(self):
        data = self._cargar("profile.json")
        assert isinstance(data, dict)
        assert "nombre" in data, "profile.json debe tener 'nombre'"

    def test_workstate_schema(self):
        data = self._cargar("workstate.json")
        assert isinstance(data, dict)
        claves = ["foco", "siguiente", "ultimo"]
        faltantes = [c for c in claves if c not in data]
        assert not faltantes, f"workstate.json falta: {faltantes}"

    def test_tasks_schema(self):
        data = self._cargar("tasks.json")
        assert isinstance(data, list)
        for i, t in enumerate(data):
            assert "id" in t,          f"tasks[{i}] falta 'id'"
            assert "descripcion" in t, f"tasks[{i}] falta 'descripcion'"
            assert "estado" in t,      f"tasks[{i}] falta 'estado'"

    def test_memory_json_formato_langchain(self):
        """
        Regresón: memory.json debe tener el formato correcto de LangChain.
        Bug anterior: tenía formato {'messages': [...]} en vez de [...].
        """
        data = self._cargar("memory.json")
        assert isinstance(data, list), (
            "memory.json debe ser una LISTA, no un objeto. "
            "Formato correcto: [{\"type\": \"human\", \"data\": {\"content\": \"...\"}}]"
        )


# ---------------------------------------------------------------------------
# Inventario de documentación: los docs mínimos necesarios para RAG
# ---------------------------------------------------------------------------

class TestInventarioDocumentacion:
    """Verifica que el corpus de RAG tiene los documentos mínimos para cada tema."""

    TEMAS_MINIMOS = {
        "LangChain RAG": "data/docs/referencia/langchain-rag-concepto.md",
        "LangChain Retriever": "data/docs/referencia/langchain-retriever.md",
        "Text Splitters": "data/docs/referencia/langchain-text-splitters.md",
        "Embeddings": "data/docs/referencia/langchain-embeddings.md",
        "MemGPT": "data/docs/referencia/paper-memgpt-resumen.md",
        "LightMem": "data/docs/referencia/paper-lightmem-resumen.md",
        "Memoria Agentes": "data/docs/referencia/memoria_agentes_resumen.md",
        "Chroma": "data/docs/referencia/chroma-queries.md",
        "Ollama API": "data/docs/referencia/ollama-api.md",
    }

    @pytest.mark.parametrize("tema,archivo", TEMAS_MINIMOS.items())
    def test_tema_tiene_documento(self, tema, archivo):
        ruta = BASE_DIR / archivo
        assert ruta.is_file(), (
            f"Tema '{tema}' sin documento en RAG. "
            f"Falta: {archivo}"
        )
        assert ruta.stat().st_size > 200, (
            f"Documento de '{tema}' existe pero está casi vacío ({ruta.stat().st_size} bytes)."
        )
