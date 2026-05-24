"""Utilidades de texto puras — sin dependencias internas del proyecto.

Este módulo existe para alojar funciones que son necesarias en
múltiples capas (router, memory_manager) sin crear ciclos de importación.

Regla: ningún módulo de app/ puede ser importado desde aquí.

Funciones:
    _normalize(text)  → minúsculas + sin tildes + espacios comprimidos.
                        Usada en Capa 1 del router y en detect_memory_intents.
"""
from __future__ import annotations

import re
import unicodedata


def _normalize(text: str) -> str:
    """Minúsculas + sin tildes + espacios comprimidos.

    Permite comparar strings del usuario con keywords del sistema
    sin importar tildes, mayúsculas o espacios múltiples.

    Ejemplo:
        _normalize('¿Qué  TAREAS  tengo?') == 'que tareas tengo?'
    """
    nfkd = unicodedata.normalize("NFD", text.lower())
    sin_tildes = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sin_tildes).strip()
