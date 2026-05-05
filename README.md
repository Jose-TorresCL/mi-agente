# 🤖 mi-agente

Asistente de IA local con RAG (Retrieval-Augmented Generation), memoria conversacional y recuperación selectiva de documentos. Funciona completamente offline usando modelos locales a través de Ollama.

---

## ¿Qué hace?

- Responde preguntas basándose en documentos propios (`.md`, `.txt`, `.pdf`)
- Mantiene memoria de la conversación actual (memoria corta)
- Recupera solo los fragmentos relevantes de los documentos, no todo el contexto
- Muestra las fuentes que usó para responder
- Funciona 100% local: sin APIs externas, sin costos, sin internet

---

## Stack tecnológico

| Herramienta | Función |
|---|---|
| [Ollama](https://ollama.ai) | Ejecutar modelos de lenguaje localmente |
| [LangChain](https://langchain.com) | Orquestar el flujo RAG y la cadena de preguntas |
| [ChromaDB](https://trychroma.com) | Base de datos vectorial para los documentos indexados |
| Python 3.11 | Lenguaje principal del proyecto |

---

## Estructura del proyecto

```
mi-agente/
├── chat.py              # Interfaz de chat principal
├── indexacion.py        # Indexa documentos en ChromaDB
├── requirements.txt     # Dependencias del proyecto
└── data/
    └── docs/
        ├── proyecto/    # Documentación del propio proyecto
        └── referencia/  # Documentos de referencia (memoria, arquitectura)
```

> `storage/` (índices de ChromaDB) y `.venv/` (entorno virtual) se generan localmente y no están en el repositorio.

---

## Instalación

### Requisitos previos

- Python 3.11+
- [Ollama](https://ollama.ai) instalado y corriendo
- Modelo descargado, por ejemplo: `ollama pull llama3`

### Pasos

```bash
# 1. Clonar el repositorio
git clone https://github.com/Jose-TorresCL/mi-agente.git
cd mi-agente

# 2. Crear y activar entorno virtual
python -m venv .venv
# Windows:
.venv\Scripts\Activate.ps1

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Indexar los documentos
python indexacion.py

# 5. Iniciar el chat
python chat.py
```

---

## Uso

Una vez iniciado `chat.py`, puedes escribir preguntas directamente:

```
Tú: ¿Qué arquitectura tiene el agente?
Agente: [responde basándose en los documentos indexados]
Fuentes usadas: arquitectura_actual.md
```

Para salir, escribe `salir` o `exit`.

---

## Estado del proyecto

🚧 En desarrollo activo. Próximas mejoras:

- [ ] Memoria por capas (conversación, perfil, episodios, reglas)
- [ ] Recuperación selectiva real por tipo de memoria
- [ ] Separación de contexto corto y largo plazo

---

## Autor

**Jose Torres** — [@Jose-TorresCL](https://github.com/Jose-TorresCL)
