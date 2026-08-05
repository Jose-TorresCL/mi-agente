"""Configuración central del proyecto mi-agente.

Importar desde aquí en todos los módulos que necesiten estas constantes.
Nunca hardcodear MODEL_NAME, OLLAMA_URL ni MAX_TURNS en otros archivos.
"""

MODEL_NAME  = "llama3.2:latest"
OLLAMA_URL  = "http://localhost:11434"
MAX_TURNS   = 8
CHROMA_DIR  = "storage/chroma"
STORAGE_DIR = "storage"
