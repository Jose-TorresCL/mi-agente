# Memoria en agentes

## Idea general

La memoria mejora a un agente porque le permite usar contexto previo y hechos persistentes de forma más útil que una conversación aislada.

## Tipos de memoria

- **Memoria de corto plazo**: conversación reciente o contexto inmediato de la sesión actual.
- **Memoria de largo plazo**: hechos estables, preferencias o conocimiento persistente que conviene conservar entre sesiones.

## Diferencia práctica entre RAG y memoria

- **RAG**: recupera información desde documentos externos para responder una pregunta con contexto relevante.
- **Memoria**: conserva información útil del historial o de hechos persistentes para reutilizarla después.

## Aplicación al proyecto

En este proyecto, primero se debe mejorar el RAG.
Eso implica mejorar documentos fuente, chunking y recuperación.
Después conviene agregar memoria híbrida con hechos persistentes.
La memoria no debe mezclarse sin criterio con todos los documentos del proyecto.

## Qué sería memoria híbrida aquí

En este proyecto, memoria híbrida significa combinar:

- memoria de conversación reciente,
- hechos persistentes del usuario o del proyecto,
- y recuperación selectiva, en vez de reenviar siempre todo el historial.

## Respuesta correcta vs respuesta grounded

- Una **respuesta correcta** es una respuesta que coincide con el contenido real del proyecto.
- Una **respuesta grounded** es una respuesta correcta que además está apoyada explícitamente en evidencia del contexto recuperado.

## Comportamiento ideal cuando falta evidencia

Si el contexto recuperado no alcanza para responder, el asistente debe decir claramente que no tiene suficiente evidencia en el contexto recuperado y no debe inventar ni completar con teoría general.
