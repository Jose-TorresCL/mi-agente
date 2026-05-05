# Estado del proyecto

## Objetivo general

Construir un asistente local con Ollama, LangChain y Chroma para responder preguntas usando recuperación de contexto desde documentos del proyecto.

## Objetivo de esta etapa

Dejar firme la base de conocimiento antes de agregar tools, memoria híbrida o más complejidad al sistema.

## Estado actual

- La indexación ya funciona.
- `chat.py` ya arranca y permite hacer preguntas al asistente.
- El asistente ya recupera contexto desde Chroma.
- La base documental fue mejorada para que las respuestas dependan menos de inferencias generales y más de evidencia explícita.
- El RAG todavía necesita mejorar precisión y grounding.
- La memoria conversacional existe, pero no debe reemplazar una buena recuperación documental.

## Qué ya está firme

- La diferencia entre arquitectura y base documental ya está definida.
- El asistente ya distingue mejor documentos fuente, arquitectura y conceptos de memoria.
- La indexación ya usa chunks más adecuados para Markdown.
- El sistema ya responde mejor preguntas literales sobre el proyecto.

## Problemas detectados

- Algunas respuestas siguen siendo demasiado generales.
- En ciertas preguntas el sistema mezcla arquitectura, documentos fuente y conceptos de memoria.
- Hay preguntas donde la respuesta correcta sería abstenerse, pero el sistema antes tendía a completar con conocimiento general.
- En preguntas cruzadas, el asistente a veces se abstiene aunque sí hay evidencia repartida entre varias fuentes.
- La base documental todavía es breve para responder preguntas conceptuales más finas.

## Próximos pasos

1. Mejorar documentos fuente.
2. Mejorar chunking.
3. Mejorar recuperación.
4. Ajustar el criterio para preguntas cruzadas.
5. Más adelante incorporar memoria híbrida.

## Criterio para avanzar de fase

Se puede avanzar a la siguiente fase cuando el asistente:

- responda bien preguntas literales sobre el proyecto,
- distinga conceptos cercanos sin mezclar categorías,
- una evidencia de más de una fuente cuando la relación sea clara,
- y diga claramente cuando no tiene suficiente evidencia en el contexto recuperado.

## Criterio de respuesta

- Si existe una respuesta breve y directa respaldada por el contexto, el asistente debe responderla.
- Si la pregunta requiere combinar fragmentos de más de una fuente, puede hacerlo solo cuando la relación entre ellos sea clara y esté apoyada por los documentos recuperados.
- Si el contexto trae piezas compatibles pero fragmentadas, el asistente debe sintetizarlas de forma breve, fiel y directa.
- Si la pregunta pide una estructura específica, debe respetarla exactamente.
- Si no hay evidencia suficiente, debe abstenerse sin completar con conocimiento general.

## Relación entre RAG y memoria híbrida

En esta etapa, el foco principal está en mejorar el RAG.
La memoria híbrida es una evolución posterior y no debe reemplazar la recuperación documental.
Primero se consolidan documentos fuente, chunking y recuperación; después se incorpora memoria persistente.