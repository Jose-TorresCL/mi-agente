# 🤖 mi-agente

Asistente de IA local con arquitectura modular: RAG, memoria en capas,
router híbrido de intenciones y sistema de métricas. Funciona 100% offline
usando modelos locales a través de Ollama.

---

## ¿Qué hace?

- Clasifica cada consulta por intención (9 carriles) antes de responder
- Recupera documentos relevantes con RAG + caché semántica anti-repetición
- Mantiene memoria en 4 capas: trabajo, episódica, semántica y larga duración
- Verifica calidad de respuesta antes de entregarla (fidelity check)
- Ejecuta herramientas propias: guardar hechos, crear tareas, consultar estado
- Registra métricas por turno: latencia, carril usado, tokens, calidad RAG
- Funciona 100% local: sin APIs externas, sin costos, sin internet

---

## Stack tecnológico

| Herramienta | Función |
|---|---|
| [Ollama](https://ollama.ai) | Ejecutar modelos de lenguaje localmente |
| [LangChain](https://langchain.com) | Orquestar el flujo RAG y las herramientas |
| [ChromaDB](https://trychroma.com) | Base de datos vectorial (RAG + caché semántica) |
| Python 3.11 | Lenguaje principal del proyecto |

---

## Estructura del proyecto

```
mi-agente/
├── chat.py                    # Punto de entrada — inicia la sesión
├── run_eval.py                # Evaluador de calidad de respuestas
├── show_metrics.py            # Dashboard de métricas por sesión
├── build_intent_index.py      # Construye el índice de intenciones
├── indexacion.py              # Indexa documentos en ChromaDB
├── requirements.txt           # Dependencias
│
├── app/                       # Módulos del asistente
│   ├── intelligence.py        # Orquestador principal (9 carriles)
│   ├── router.py              # Router híbrido 3 capas
│   ├── rag_engine.py          # Motor RAG
│   ├── memory_manager.py      # Guardián único de lectura/escritura de memoria
│   ├── memory_store.py        # Persistencia de las 4 capas
│   ├── memory_context.py      # Recuperación selectiva por tipo de memoria
│   ├── episode_store.py       # Almacén de episodios y experiencias
│   ├── fidelity_check.py      # Verificación de calidad de respuesta
│   ├── semantic_cache.py      # Caché semántica de consultas
│   ├── tools.py               # Herramientas ejecutables por el agente
│   ├── tool_registry.py       # Registro de herramientas disponibles
│   ├── tool_helpers.py        # Utilidades para ejecución de herramientas
│   ├── schemas.py             # Tipos, enums y estructuras de datos
│   ├── metrics.py             # Registro de métricas por turno
│   ├── chat_core.py           # Lógica core del chat
│   ├── chat_ui.py             # Interfaz de usuario en terminal
│   ├── session_state.py       # Estado de sesión activa
│   ├── prompts.py             # Plantillas de prompts
│   └── config.py              # Configuración centralizada
│
├── docs/                      # Documentación del proyecto
│   ├── adr/                   # Decisiones de arquitectura (ADR-001 a ADR-006)
│   ├── vision-agente.md       # Visión y hoja de ruta
│   ├── arquitectura-memoria.md # Detalle de las 4 capas de memoria
│   └── hardware-modelos.md    # Hardware y modelos recomendados
│
├── data/                      # Documentos a indexar
└── tests/                     # Tests del proyecto
```

> `storage/` (ChromaDB e índices) y `.venv/` se generan localmente
> y no están en el repositorio.

---

## Instalación

### Requisitos previos

- Python 3.11+
- [Ollama](https://ollama.ai) instalado y corriendo
- Modelo recomendado: `ollama pull llama3.2`
- Modelo de embeddings: `ollama pull nomic-embed-text`

### Pasos

```bash
# 1. Clonar el repositorio
git clone https://github.com/Jose-TorresCL/mi-agente.git
cd mi-agente

# 2. Crear y activar entorno virtual
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Indexar documentos
python indexacion.py

# 5. Construir índice de intenciones
python build_intent_index.py

# 6. Iniciar el chat
python chat.py
```

---

## Uso

```
Tú: ¿Qué hace el módulo router.py?
Agente: [responde basándose en documentos indexados + memoria]

Tú: recuerda que prefiero respuestas con ejemplos
Agente: [guarda el hecho en memoria larga duración]

Tú: salir
Agente: [resume la sesión y guarda el episodio automáticamente]
```

Comandos disponibles dentro del chat: `salir`, `exit`

---

## Métricas y evaluación

```bash
# Ver métricas de las últimas sesiones
python show_metrics.py

# Ver drift de calidad (últimos 7 días vs 7 anteriores)
python show_metrics.py --drift

# Correr evaluación de calidad
python run_eval.py
```

---

## Documentación

| Documento | Contenido |
|---|---|
| [ADR-001](docs/adr/ADR-001-router-hibrido.md) | Router híbrido 3 capas |
| [ADR-002](docs/adr/ADR-002-memoria-en-capas.md) | Memoria en capas y tipos formales |
| [ADR-003](docs/adr/ADR-003-memory-manager.md) | memory_manager como guardián único |
| [ADR-004](docs/adr/ADR-004-calidad-rag.md) | Calidad RAG: caché, fidelity y exclusiones |
| [ADR-005](docs/adr/ADR-005-arquitectura-inteligencia.md) | Carriles de decisión e intelligence.py |
| [ADR-006](docs/adr/ADR-006-experience-index.md) | Experience index y feedback loop |
| [Visión](docs/vision-agente.md) | Hoja de ruta del proyecto |
| [Arquitectura de memoria](docs/arquitectura-memoria.md) | Detalle de las 4 capas |
| [Hardware y modelos](docs/hardware-modelos.md) | Modelos compatibles con el hardware |

---

## Estado del proyecto

✅ Fases 1-8 completadas — base funcional, memoria, router, inteligencia, herramientas
✅ R1 — Sistema de métricas por turno
✅ R2 — Dashboard de métricas con análisis de drift
✅ R3 — Caché semántica + mejoras fidelity
✅ R4 — Recuperación selectiva de memoria por tipo

🔭 Próximo: pruebas integrales + definir siguiente dirección

---

## Autor

**Jose Torres** — [@Jose-TorresCL](https://github.com/Jose-TorresCL)
