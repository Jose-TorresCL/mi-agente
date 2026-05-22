# ADR-007 — Modelo único vs. dos modelos especializados en Ollama

**Estado:** ✅ Aceptado  
**Fecha:** 2026-05  
**Autores:** Jose Torres + Asistente IA local

---

## Contexto

Durante el análisis de `intelligence.py` se identificó que el archivo llama al LLM
de dos formas distintas: mediante LangChain (`build_chain`) para el carril RAG,
y mediante `requests.post` directo a Ollama para los carriles de memoria
(`_synthesize_memory_answer`) y cierre de sesión (`_decide_exit`).

Esto generó la pregunta: ¿conviene usar **dos modelos distintos**, asignando
uno liviano (`phi3:mini`) para tareas simples como síntesis de memoria
y uno más robusto (`llama3.2`) para RAG?

La intuición era atractiva: phi3:mini es más rápido y ocupa menos RAM,
lo que teóricamente liberaría recursos para que llama3.2 trabaje mejor
en las consultas RAG.

## Problema técnico identificado

El hardware de desarrollo es un Lenovo ThinkPad i7 8th gen con 16 GB DDR4
**sin GPU dedicada**. La inferencia se ejecuta completamente en CPU.

En este contexto, Ollama gestiona los modelos con las siguientes restricciones:

- Ollama mantiene un único modelo "caliente" en RAM por defecto.
- Cuando se llama a un segundo modelo, Ollama hace **swap**: descarga el primero
  y carga el segundo. Esto toma **3–5 segundos en frío** en CPU-only.
- Si ambos modelos caben en RAM simultáneamente, **la inferencia en CPU se divide
  entre los dos procesos**, lo que aumenta la latencia de cada respuesta.
- El beneficio de especialización no compensa la penalización de swap ni
  la fragmentación de CPU en un equipo sin aceleración de hardware.

## Decisión

**Se usa un único modelo para todos los carriles del agente.**

El modelo activo es `llama3.2` (3B parámetros, ~2 GB RAM), que ya estaba
validado en el proyecto y demostró estabilidad en todas las rutas del router.

`phi3:mini` se mantiene instalado pero **no se usa en producción**.
Puede activarse manualmente para pruebas comparativas puntuales.

## Alternativas consideradas

| Alternativa | Pros | Contras |
|-------------|------|---------|
| phi3:mini para memoria + llama3.2 para RAG | Especialización, phi3 más rápido en tareas simples | Swap 3–5s en cada alternancia; latencia peor en promedio |
| Ambos modelos en RAM simultáneamente | Sin swap entre llamadas | CPU dividida entre dos procesos; cada respuesta más lenta |
| Un único modelo para todo (llama3.2) ✅ | Siempre caliente, sin overhead de alternancia | Menos especialización por tarea |
| Migrar a modelo con cuantización GGUF más agresiva | Menor RAM, misma capacidad | Requiere benchmarking adicional; riesgo de degradar calidad |

## Consecuencias

**Positivas:**
- El modelo llama3.2 siempre está caliente en RAM: latencia consistente
  sin picos por carga de modelo.
- Configuración simple: un único `MODEL_NAME` en `config.py`.
- Cambiar de modelo en el futuro es un cambio de una sola línea.
- No hay riesgo de que una tarea simple compita con una tarea RAG por RAM.

**Trade-offs:**
- Las síntesis de memoria y los resúmenes episódicos usan el mismo modelo
  que las consultas RAG complejas, aunque no lo necesitan.
- Si en el futuro se dispone de hardware con GPU dedicada, esta decisión
  debería revisarse: en GPU el swap es casi instantáneo y el multi-modelo
  sí tiene sentido.

### Deuda técnica aceptada

- `_synthesize_memory_answer()` y `_decide_exit()` llaman al LLM con
  `requests.post` directo, sin pasar el historial de conversación.
  Esto significa que las respuestas de síntesis de memoria no tienen contexto
  del hilo actual. Es la causa principal de respuestas desconectadas en
  el carril `memory`. Solución futura: unificar ambos clientes LLM y
  pasar los últimos 2–3 turnos del `chat_history`.
- La separación entre cliente LangChain y cliente `requests` directo es
  una inconsistencia arquitectural que debería resolverse en una refactorización
  de `intelligence.py`.

### Condición de revisión

Esta decisión se revisa automáticamente si:
- Se incorpora una GPU dedicada al equipo de desarrollo.
- Se valida con benchmarks reales que un modelo alternativo (Qwen3, DeepSeek)
  supera a llama3.2 en métricas clave del proyecto (ver ADR-008).

## Archivos clave

- `app/config.py` — `MODEL_NAME` (única fuente de verdad del modelo activo)
- `app/intelligence.py` — dos clientes LLM: `build_chain` y `requests.post`
- `docs/hardware-modelos.md` — restricciones de hardware documentadas
