# Batería de evaluación RAG: caché semántica y fidelity_check

Este archivo reúne preguntas de prueba para validar el comportamiento de la caché semántica y del guardrail de fidelidad sobre documentos Markdown ya indexados en el proyecto.

## Grupo A — Caché semántica

1. ¿Qué es la caché semántica en mi-agente y para qué sirve?
2. ¿Dónde se aplica la caché semántica en el flujo actual del sistema?
3. ¿Cuál es el umbral de similitud usado para considerar un hit de caché semántica?
4. ¿Cómo se relaciona la caché semántica con el intent index y por qué su umbral es más alto?

## Grupo B — Fidelity check

5. ¿Qué hace fidelity_check cuando una respuesta no tiene documentos de soporte?
6. ¿Qué tipo de errores numéricos busca fidelity_check?
7. ¿Cuál es la diferencia entre un bloqueo y una advertencia en fidelity_check?
8. ¿Qué ocurre si los embeddings quedan ocupados y no se puede completar la verificación de fidelidad?

## Grupo C — Casos numéricos y documentos específicos

9. ¿Qué modelo LLM recomendado aparece en hardware-modelos.md para este hardware?
10. ¿Qué boost reciben los episodios exitosos en experience_index?
11. ¿Cuántos chunks curados se mencionan como base del índice en los documentos de proyecto?
12. ¿Cuántos archivos se excluyeron del índice por ser obsoletos, genéricos o de baja calidad?
