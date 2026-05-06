# Arquitectura actual

## Propósito

Este archivo describe cómo está armado hoy el asistente local, qué rol cumple cada componente y cómo se relacionan RAG, memoria estructurada y tools dentro del flujo del sistema.

## Componentes principales

- **Ollama**: ejecuta localmente el modelo de lenguaje.
- **llama3.2**: modelo principal para generar respuestas.
- **nomic-embed-text**: genera embeddings para indexación y recuperación semántica.
- **Chroma**: guarda la base vectorial persistida del proyecto.
- **LangChain**: orquesta chat, recuperación, memoria y flujo general.
- **JSON persistente en `storage/`**: almacena memoria estructurada y estado del proyecto.

## Archivos principales del sistema

| Archivo | Rol |
|---------|-----|
| `indexacion.py` | Entrada para cargar documentos, dividirlos en chunks y construir Chroma |
| `chat.py` | Punto de entrada principal del asistente |
| `app/chat_core.py` | Lógica principal del chat y coordinación del flujo |
| `app/chat_ui.py` | Interfaz de consola y presentación |
| `app/indexing_core.py` | Lógica reutilizable de indexación |
| `app/router.py` | Decide si una consulta debe ir a RAG, memoria o tools |
| `app/tools.py` | Tools básicas de lectura segura de archivos y utilidades asociadas |
| `app/memory_store.py` | Lectura y escritura segura de memoria estructurada |
| `app/session_state.py` | Vista resumida del estado actual del proyecto |
| `app/prompts.py` | Instrucciones y plantillas que guían el comportamiento |
| `storage/chroma/` | Base vectorial persistida para RAG |
| `storage/memory.json` | Memoria conversacional reciente |
| `storage/profile.json` | Perfil y preferencias del usuario |
| `storage/project_facts.json` | Hechos estables del proyecto |
| `storage/tasks.json` | Tareas y pendientes |
| `storage/work_state.json` | Estado actual de trabajo |

## Base documental actual

Documentos fuente en Markdown que el agente consulta como conocimiento del proyecto:

- `estado_proyecto.md`: fases, objetivos, estado actual y próximos pasos.
- `arquitectura_actual.md`: componentes técnicos y flujo del sistema.
- `memoria_agentes_resumen.md`: conceptos de memoria aplicados al proyecto.

## Flujo actual del sistema

```text
Usuario
  ↓
chat.py
  ↓
app/chat_ui.py
  ↓
app/chat_core.py
  ↓
app/router.py
  ↓
┌───────────────┬──────────────────────┬──────────────────────┐
│ RAG           │ Memoria estructurada │ Tools                │
│ (Chroma/docs) │ (JSON en storage/)   │ (lectura segura)     │
└───────────────┴──────────────────────┴──────────────────────┘
  ↓
Ollama (llama3.2)
  ↓
Respuesta
```

## Diferencia entre arquitectura y base documental

| Arquitectura | Base documental |
|--------------|-----------------|
| Componentes, scripts, módulos, almacenamiento y flujo técnico | Textos que el agente consulta como conocimiento del proyecto |
| `app/memory_store.py`, `app/router.py`, `storage/tasks.json` | `estado_proyecto.md`, `arquitectura_actual.md`, `memoria_agentes_resumen.md` |
| Explica cómo funciona internamente el sistema | Explica qué sabe el agente sobre el proyecto |

## Estado técnico de fase 2

**Implementado**:

- Modularización inicial del proyecto.
- RAG básico funcional con Chroma.
- Memoria estructurada base en JSON.
- Módulos principales dentro de `app/`.
- Router simple funcional.
- Tools básicas de lectura segura.
- Lectura controlada de archivos en `app/`, `data/docs/` y `storage/`.

**Pendiente**:

- Integrar mejor memoria estructurada al flujo de respuesta.
- Agregar tools de escritura segura.
- Actualizar automáticamente el estado de trabajo.
- Refinar recuperación selectiva entre capas.
- Reducir dependencia futura de memoria conversacional deprecada.

## Objetivo técnico de esta etapa

Consolidar una arquitectura pequeña, entendible y extensible que combine:

- RAG para conocimiento estable,
- memoria estructurada para estado persistente,
- tools para acciones concretas,
- y routing simple para elegir la capa adecuada.

## Límites actuales de diseño

En esta etapa todavía **no** conviene agregar:

- multiagente complejo,
- planner sofisticado,
- tools de alto riesgo como shell arbitraria,
- automatizaciones pesadas,
- ni memoria indiscriminada basada en reenviar siempre todo el historial.

La prioridad sigue siendo mantener una arquitectura local, pequeña, segura y fácil de mantener.