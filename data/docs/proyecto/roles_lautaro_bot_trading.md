# Roles: Lautaro y bot_trading

## Lautaro (mi-agente)
- Asistente IA local con memoria por capas (perfil, workstate, tareas, episodios).
- Usa RAG con Chroma para recuperar contexto técnico.
- Tiene un router con tests en verde que decide cuándo usar tools externas.

## bot_trading
- Proyecto independiente especializado en análisis de mercado y decisiones de trading (paper/live).
- Corre en su propio entorno virtual y repositorio.
- Expone un script que devuelve un JSON estable con análisis y resumen de sesión.

## Integración
- Lautaro llama a bot_trading a través de `tool_analizar_mercado`.
- La tool ejecuta un script del bot usando `subprocess` y recibe un JSON.
- Lautaro interpreta ese JSON, lo explica en lenguaje natural y puede guardar episodios de consulta de mercado.