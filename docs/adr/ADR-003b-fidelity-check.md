# ADR-003: Fidelity check con umbral 0.55

**Estado:** Aceptado  
**Fecha:** 2026-05-20  
**Archivo principal:** `app/fidelity.py`

---

## Contexto

Un LLM local puede "alucinar": generar respuestas que suenan coherentes pero que no están respaldadas por los documentos recuperados (chunks de RAG). En un asistente de proyecto esto es especialmente peligroso — si el agente inventa información sobre el estado del código o las tareas, el usuario toma decisiones basadas en datos falsos.

Necesitábamos una capa que detectara cuándo la respuesta generada se aleja demasiado del contexto real recuperado.

---

## Decisión

Implementar un **fidelity check** que compara la respuesta generada contra los chunks recuperados usando similitud de embeddings (cosine similarity con `nomic-embed-text`):

```
respuesta_generada + chunks_recuperados
    → nomic-embed-text (embeddings)
        → cosine_similarity
            → score ∈ [0.0, 1.0]

si score >= 0.55 → respuesta aceptada
si score <  0.55 → respuesta rechazada / advertencia al usuario
```

El **umbral de 0.55** fue elegido empíricamente tras evaluar casos reales del proyecto:
- Scores > 0.55: la respuesta usa el contexto aunque lo parafrasee.
- Scores < 0.55: la respuesta introduce información nueva no presente en los chunks.

---

## Consecuencias

**Positivas:**
- Detecta alucinaciones obvias antes de mostrarlas al usuario.
- Usa el mismo modelo de embeddings que ya corre en el stack (`nomic-embed-text`), sin dependencias nuevas.
- El check es rápido (~50ms) comparado con el tiempo de generación del LLM.

**Negativas:**
- Un umbral fijo de 0.55 puede generar falsos positivos: respuestas correctas que parafrasean mucho el texto original pueden quedar por debajo del umbral.
- No detecta alucinaciones sutiles donde la respuesta mezcla información real con inventada.
- Requiere que Ollama esté activo (usa embeddings locales).

---

## Alternativas descartadas

| Alternativa | Por qué se descartó |
|---|---|
| Sin fidelity check | Alucinaciones llegan al usuario sin filtro. Inaceptable para un asistente de proyecto. |
| Umbral fijo de 0.70 | Demasiado estricto: rechaza respuestas válidas que parafrasean. |
| Umbral fijo de 0.40 | Demasiado permisivo: deja pasar alucinaciones evidentes. |
| NLI (Natural Language Inference) | Requiere un modelo clasificador adicional. Overhead innecesario en setup local. |

---

## Notas de implementación

- El umbral `0.55` está definido como constante en `app/fidelity.py` → `FIDELITY_THRESHOLD`.
- Si se quiere ajustar, cambiar solo esa constante y correr `pytest tests/test_lautaro.py::test_fidelidad`.
- El check se aplica solo en el carril `rag`. Los carriles `memory` y `tool_*` no lo necesitan porque no usan chunks recuperados.
