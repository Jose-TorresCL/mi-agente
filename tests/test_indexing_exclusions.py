"""Contrato de exclusiones del índice RAG: por nombre de archivo y por carpeta."""
from pathlib import Path
from app.indexing_core import _is_excluded


def test_excluye_por_carpeta():
    assert _is_excluded(Path("data/docs/historico/viejo.md"))
    assert _is_excluded(Path("data/docs/borradores/borrador.md"))
    assert _is_excluded(Path("data/docs/.pytest_cache/x.md"))


def test_no_excluye_docs_normales():
    assert not _is_excluded(Path("data/docs/proyecto/plan.md"))
    assert not _is_excluded(Path("data/docs/adr/ADR-001-router-hibrido.md"))


def test_no_excluye_nombre_parecido():
    # 'historico-final.md' es un archivo legítimo, no la carpeta 'historico/'
    assert not _is_excluded(Path("data/docs/proyecto/historico-final.md"))