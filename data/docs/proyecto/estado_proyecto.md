# Estado del proyecto

## Objetivo general

Construir un asistente local con Ollama, LangChain y Chroma para responder preguntas usando recuperación de contexto desde documentos del proyecto.

## Objetivo de esta etapa

Dejar firme la base de conocimiento antes de agregar tools, memoria híbrida o más complejidad al sistema.

## Estado actual

- La indexación ya funciona.
- `chat.py` ya arranca y permite hacer preguntas al asistente.
- El asistente ya recupera contexto desde Chroma.
- El RAG todavía necesita mejorar precisión y grounding.
- La memoria conversacional existe, pero no debe reemplazar una buena recuperación documental.

## Problemas detectados

- Algunas respuestas siguen siendo demasiado generales.
- En ciertas preguntas el sistema mezcla arquitectura, documentos fuente y conceptos de memoria.
- Hay preguntas donde la respuesta correcta sería abstenerse, pero el sistema antes tendía a completar con conocimiento general.
- La base documental actual todavía es muy breve para responder preguntas conceptuales más finas.

## Próximos pasos

1. Mejorar documentos fuente.
2. Mejorar chunking.
3. Mejorar recuperación.
4. Más adelante crear memoria híbrida.

## Criterio para avanzar

Se puede avanzar a una siguiente fase cuando el asistente:

- responda bien preguntas literales sobre el proyecto,
- distinga conceptos cercanos sin mezclar categorías,
- y diga claramente cuando no tiene suficiente evidencia en el contexto recuperado.

## Relación entre RAG y memoria híbrida

En esta etapa, el foco principal está en mejorar el RAG.
La memoria híbrida es una evolución posterior y no debe reemplazar la recuperación documental.
Primero se consolidan documentos fuente, chunking y recuperación; después se incorpora memoria persistente.

## Criterio de respuesta cuando hay evidencia repartida

Si una pregunta requiere unir evidencia de más de una fuente, el asistente puede combinar fragmentos del contexto siempre que la relación sea clara y esté apoyada por los documentos recuperados.
Si la relación no está explícita o sigue siendo ambigua, debe abstenerse.
