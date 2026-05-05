# Arquitectura actual

## Propósito

Este archivo describe cómo está armado hoy el asistente local y qué rol cumple cada componente técnico.

## Componentes principales

- **Ollama**: ejecuta el modelo de lenguaje local.
- **nomic-embed-text**: genera embeddings para indexación y búsqueda semántica.
- **Chroma**: guarda la base vectorial persistida.
- **LangChain**: orquesta el chat, la recuperación y la integración entre componentes.

## Archivos principales del sistema

- **indexacion.py**: carga documentos, los divide en chunks y construye el índice vectorial.
- **chat.py**: consulta el índice, envía contexto al modelo y muestra la respuesta al usuario.
- **storage/chroma**: contiene la base vectorial persistida.
- **storage/memory.json**: guarda la memoria conversacional actual.

## Base documental actual

La base documental actual del asistente, en esta etapa, está formada por estos documentos fuente en Markdown:

- `estado_proyecto.md`
- `arquitectura_actual.md`
- `memoria_agentes_resumen.md`

## Diferencia entre arquitectura y base documental

- La **arquitectura** describe componentes, scripts, almacenamiento y flujo técnico.
- La **base documental** contiene los textos que el asistente consulta como conocimiento del proyecto.

## Objetivo de esta etapa

El objetivo técnico actual no es agregar más complejidad, sino dejar firme la base de conocimiento y mejorar la calidad del RAG antes de sumar tools o memoria híbrida.
