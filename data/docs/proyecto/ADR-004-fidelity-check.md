# ADR-004 — Fidelity check en mi-agente

**Estado:** Aceptado / Implementado  
**Fecha:** 2026-08-05  
**Archivo principal:** `app/fidelity_check.py`

---

## Contexto

En el flujo RAG de mi-agente, la respuesta generada por el LLM puede parecer válida aunque no esté realmente soportada por los documentos recuperados. Eso es especialmente delicado cuando el sistema responde sobre hechos, números, estados o decisiones concretas.

Para reducir alucinaciones silenciosas, se incorporó un paso de verificación posterior a la generación: `fidelity_check`. Su rol no es reemplazar la respuesta del LLM, sino actuar como guardrail documental antes de entregar el resultado al usuario.

El estado actual del módulo incluye:
- verificación semántica entre la respuesta y los chunks recuperados;
- verificación de claims numéricos contra el texto fuente literal;
- bypass para preguntas triviales, respuestas cortas con evidencia real y casos sin contexto recuperado;
- logging de éxitos, bloqueos y casos inciertos en `storage/logs/`;
- una API estable basada en `verify_fidelity(answer, source_docs, question="") -> tuple[bool, float]`.

La implementación actual se encuentra en `app/fidelity_check.py` y se integra desde `app/intelligence.py` como paso de control después de la generación RAG.

---

## Alternativas consideradas

| Alternativa | Ventajas | Inconvenientes |
|---|---|---|
| No usar fidelity check | Menos latencia y menor complejidad | Mayor riesgo de responder con información no respaldada por los docs |
| Fidelity check estrictamente por NLI o LLM | Más semántico en algunos casos | Requiere más recursos, más latencia y mayor dependencia del modelo |
| Fidelity check solo numérico | Simple y barato | No cubre alucinaciones semánticas ni respuestas con información no literal |
| Fidelity check híbrido (semántico + numérico + reglas de borde) | Equilibra robustez y costo | Requiere más mantenimiento y más casos de prueba |

---

## Pruebas realizadas

### 1. Test de contención
Se revisó el flujo de carga del modelo y la interacción entre generación y embeding post-respuesta. La decisión de centralizar el cliente LLM en `app/llm_client.py` con `keep_alive=-1`, `reasoning=False` y un singleton compartido reduce la presión sobre Ollama y evita que la verificación de fidelidad compita innecesariamente con la generación del modelo.

### 2. Test de margen de limpieza
Se evaluó la estabilidad del flujo cuando Ollama tarda en liberar recursos tras una generación. Para ello se aumentaron los márgenes de timeout y reintentos en el embeding de fidelidad y en la caché semántica, evitando que una respuesta correcta se bloquee por un problema transitorio de disponibilidad o latencia del modelo.

### 3. Investigación de `OLLAMA_NUM_PARALLEL`
Se investigó si ajustar `OLLAMA_NUM_PARALLEL` podía mejorar la contención o la estabilidad del sistema. La conclusión inicial es que no es el primer ajuste a priorizar: el problema más visible estaba en la coordinación entre generación, embeddings y tiempo de liberación del modelo. Por eso se priorizó una estrategia más conservadora: singleton del cliente, `reasoning=False`, timeouts amplios y reintentos, en vez de cambiar el paralelismo global de Ollama sin evidencia clara de beneficio.

### 4. Verificación ejecutada
Se corrieron las pruebas relevantes de fidelity check y el resultado fue:
- `11 passed` en `tests/test_fidelity_contract.py`, `tests/test_fidelity_warn1.py`, `tests/test_fidelity_per_chunk.py` y `tests/test_fidelity_numeric_variants.py`.

---

## Decisión

Se mantiene `fidelity_check` como un guardrail posterior a la respuesta RAG, pero con un diseño pragmático y tolerante:

1. Se usa verificación semántica y numérica, no solo una de ellas.
2. Se priorizan reglas de seguridad para casos borde:
   - sin chunks recuperados;
   - chunks vacíos o sin contenido útil;
   - respuestas cortas sin evidencia real;
   - números que no aparecen literalmente en los documentos fuente.
3. Se evita bloquear al usuario en situaciones inciertas: si la verificación no puede completarse por problemas de embeddings o disponibilidad del modelo, el sistema registra un caso incierto y no rompe la experiencia principal.
4. Se centraliza la configuración del cliente LLM para reducir regresiones y mantener los parámetros de inferencia consistentes.

Esta decisión busca un equilibrio entre robustez y estabilidad operativa en un entorno local con recursos limitados.

---

## Próximos pasos

- Añadir pruebas de integración más explícitas para los escenarios de contención y margen de limpieza.
- Evaluar de forma controlada si `OLLAMA_NUM_PARALLEL` merece un ajuste adicional en un entorno con carga real.
- Considerar exponer el modo de emergencia (`bypass` vs `uncertain`) como configuración ajustable.
- Revisar si el umbral dinámico de fidelidad debe seguir afinándose según tipos de pregunta o longitud de contexto.
- Documentar mejor los casos de uso donde `fidelity_check` debe bloquear vs. solo advertir.
