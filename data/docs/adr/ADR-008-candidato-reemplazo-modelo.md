# ADR-008 — Candidato a reemplazo de llama3.2: criterios y proceso de evaluación

**Estado:** 🟡 En evaluación  
**Fecha:** 2026-05  
**Autores:** Jose Torres + Asistente IA local

---

## Contexto

Desde el inicio del proyecto se usa `llama3.2` (3B parámetros) como modelo
principal. Esta elección fue válida: el modelo era estable, ya estaba descargado
y fue validado en las primeras fases del proyecto.

Sin embargo, el ecosistema de modelos open-source evolucionó significativamente
entre 2025 y 2026. Modelos nuevos disponibles en Ollama muestran mejoras
mediables en:

- Razonamiento encadenado (chain-of-thought)
- Generación de JSON estructurado para tool calling
- Comprensión de instrucciones en español
- Tradeoff calidad/velocidad en equipos CPU-only

Los candidatos evaluados en sesiones de análisis comparativo fueron:
`Qwen3 8B`, `Qwen2.5-Coder 7B`, `DeepSeek-R1 7B` y `llama3.1 8B`.

## Decisión provisional

**Se mantiene `llama3.2` como modelo de producción hasta completar un
benchmark mínimo reproducible dentro del proyecto.**

El principio rector es: **ningún cambio de modelo sin evidencia medida**.
Cambiar el modelo base sin benchmarks rompe la trazabilidad de las métricas
históricas en `metrics.jsonl` y hace imposible comparar si una mejora
o degradación fue por código o por modelo.

## Criterios de evaluación

Para que un modelo candidato reemplace a `llama3.2`, debe superar o igualar
los siguientes umbrales en el contexto de este proyecto:

| Métrica | Umbral mínimo | Cómo medirlo |
|---------|---------------|---------------|
| Exactitud de carril (router) | ≥ batería_20 actual (46/47) | `pytest tests/test_bateria_20.py` |
| Calidad de síntesis memory | Subjetiva: ≥ 4/5 en 10 preguntas | Evaluación manual |
| Latencia promedio (RAG) | ≤ +20% vs. llama3.2 actual | `show_metrics.py` |
| JSON válido en tool calling | 100% en 5 intentos | `pytest tests/test_bateria_9.py` |
| Timeouts en sesión de 15 turnos | 0 | Ejecución manual de chat.py |

## Candidatos priorizados

| Modelo | Tamaño | Rol sugerido | Estado |
|--------|--------|--------------|--------|
| `qwen3:8b` | ~5 GB | Reemplazo total o clasificador | 🔲 Sin probar |
| `llama3.1:8b` | ~5 GB | Reemplazo directo (misma familia) | 🔲 Sin probar |
| `qwen2.5-coder:7b` | ~4.5 GB | Carriles tool y código | 🔲 Sin probar |
| `deepseek-r1:7b` | ~4.5 GB | Razonamiento complejo | 🔲 Sin probar |
| `llama3.2` (actual) | 2 GB | Producción actual | ✅ Validado |

**Nota de hardware:** todos los modelos de 7B–8B requieren ~5 GB de RAM.
En el ThinkPad con 16 GB, esto es viable en CPU, pero la latencia
puede ser 2–3× mayor que con llama3.2 (3B). Ver ADR-007.

## Proceso de benchmark mínimo

Antes de cambiar `MODEL_NAME` en `config.py`, ejecutar:

```powershell
# 1. Descargar candidato sin borrar el actual
ollama pull qwen3:8b

# 2. Cambiar MODEL_NAME temporalmente en config.py
# MODEL_NAME = "qwen3:8b"

# 3. Correr batería de tests
pytest tests/test_bateria_20.py tests/test_bateria_9.py -v

# 4. Correr evaluador de calidad RAG
python run_eval.py

# 5. Revisar métricas de latencia
python show_metrics.py

# 6. Si los resultados son peores, revertir MODEL_NAME a llama3.2
```

## Alternativas consideradas

| Alternativa | Pros | Contras |
|-------------|------|---------|
| Cambiar a Qwen3 8B sin benchmark | Potencialmente mejor calidad | Rompe trazabilidad de métricas históricas |
| Mantener llama3.2 indefinidamente | Estabilidad garantizada | Puede quedar técnicamente obsoleto |
| Dos modelos: uno por carril | Especialización | Descartado en ADR-007 (swap penalty en CPU) |
| **Benchmark formal antes de cambiar** ✅ | Decisión basada en evidencia real | Requiere tiempo de evaluación (~1h) |

## Consecuencias

**Positivas:**
- El proceso de evaluación queda documentado y es reproducible.
- Cualquier cambio de modelo futuro tiene un ADR que lo justifica con datos.
- Se puede comparar la calidad antes/después con las mismas baterías de tests.

**Trade-offs:**
- El proceso de benchmark tarda ~1 hora si se hace bien.
- Mientras no se ejecute el benchmark, el proyecto puede quedarse con un
  modelo que ya no es el mejor disponible.

### Condición de cierre

Este ADR pasa de **En evaluación** a **Aceptado** cuando:
1. Se ejecuta el benchmark completo con al menos un candidato.
2. Se documenta el resultado en este archivo con fecha y métricas reales.
3. Se actualiza `MODEL_NAME` en `config.py` (o se confirma que llama3.2 sigue siendo la mejor opción).

## Archivos clave

- `app/config.py` — `MODEL_NAME` (línea a cambiar)
- `tests/test_bateria_20.py` — batería principal de evaluación
- `run_eval.py` — evaluador de calidad RAG
- `show_metrics.py` — dashboard de métricas históricas
- `docs/hardware-modelos.md` — restricciones de hardware
