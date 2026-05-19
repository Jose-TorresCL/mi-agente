# Plan de Robustecimiento — Fases R1 a R7

> Última actualización: 19/05/2026
> Estado general: **R1 ✅ COMPLETO | R2 ✅ COMPLETO (baseline numérico pendiente) | R3 ✅ COMPLETO | R4–R7 pendientes**

## Por qué existe este plan

El proyecto ya tiene una arquitectura madura: orquestación, RAG, memoria por
capas, router híbrido, tools, tests y observabilidad básica. El cuello de
botella ya no es "tener más features" sino hacer lo que existe más
**predecible, medible y mantenible**.

La analogía: la casa ya tiene todas las piezas. Antes de agregar otra
habitación, se revisan cañerías, electricidad y medidores.

> Principio rector: **no agregar nuevas skills ni cambiar de modelo hasta
> completar al menos R1–R3**. Sin baseline métrico, no se puede saber si
> un cambio mejora o empeora el sistema.

---

## Mapa de fases

| Fase | Título | Prioridad | Estado |
|---|---|---|---|
| R1 | Endurecer contratos internos | 🔴 Fundamental | ✅ COMPLETO |
| R2 | Observabilidad completa | 🔴 Fundamental | ✅ COMPLETO (baseline pendiente) |
| R3 | Evaluación real del sistema | 🟠 Intermedio | ✅ COMPLETO |
| R4 | Robustecer memoria por capas | 🔴→🟠 F/I | ✅ Parcial |
| R5 | Robustecer RAG antes de cambiar modelo | 🟠 Intermedio | ✅ Parcial |
| R6 | Tools seguras y previsibles | 🟠 Intermedio | 🔲 Pendiente |
| R7 | Preparar cambios futuros de modelo | 🟡 Avanzado | 🔓 DESBLOQUEADO |

---

## R1 — Endurecer contratos internos

**Prioridad**: 🔴 Fundamental
**Estado**: ✅ COMPLETO — cerrado 19/05/2026

### Qué se implementó

- Carril `memory` TERMINAL — nunca cae a RAG ni caché
- `unsupported` fuera del flujo LLM/Chroma
- `get_context_for(intent_type)` como interfaz clara entre router y memoria
- `DecisionResult` y `RagResult` formalizados en `schemas.py` (R1-A)
- `process_turn()` tipado `→ tuple[str, list]` (R1-B)
- `test_architecture.py` — análisis AST que bloquea imports cruzados (R1-C/D/E)
- `test_memory_route.py` — carril memory devuelve real, no cacheado
- `test_memory_layer.py` — `get_context_for()` devuelve solo la capa pedida

### Validación

```powershell
pytest tests/test_architecture.py -v
pytest tests/test_memory_route.py -v
pytest tests/test_memory_layer.py -v
# Esperado: todos verdes
```

---

## R2 — Observabilidad completa

**Prioridad**: 🔴 Fundamental
**Estado**: ✅ COMPLETO — infraestructura lista; baseline numérico se genera con uso real

### Qué se implementó

- `metrics.py` — logger por turno en `storage/metrics.jsonl`
- Campos: ruta, tiempo retrieval, tiempo LLM, tokens estimados, flag `cached`, `intent_type`, `docs_retrieved`
- `record_turn()` nunca lanza excepciones (errores van a WARNING)
- `show_metrics.py` — tabla ASCII en terminal con distribución de carriles, tiempos y cache hits (R2-A)
- `intent_type` registrado dentro del carril `memory` (R2-B)
- Número de docs recuperados guardado por consulta RAG (R2-C)
- Tasa "respuesta con evidencia" visible en `show_metrics.py` (R2-D)
- Aging del caché: entradas > 7 días se recalculan (R2-E)

### Métricas objetivo (a validar con uso real)

| Métrica | Objetivo |
|---|---|
| Tiempo retrieval Chroma | < 200ms |
| Tiempo LLM | < 8s en ThinkPad i7 8ª gen |
| % respuestas con evidencia documental | ≥ 75% |
| % consultas sin LLM (caché + keywords) | > 30% |
| % cache hits | visible en dashboard |

### Validación

```powershell
python show_metrics.py
# Esperado: tabla con tiempos por carril, % cache hit, top docs
```

---

## R3 — Evaluación real del sistema

**Prioridad**: 🟠 Intermedio
**Estado**: ✅ COMPLETO — cerrado 19/05/2026 con run_eval.py

### Qué se implementó

- `test_routing_matrix.py` — 27 casos, 9 tipos de carril × 3 ejemplos (R3-A/B)
- `test_bateria_20.py` — 20 preguntas con `expected_lane` y `expected_evidence_source` (R3-C)
- `run_eval.py` — script de reporte que genera número visible (R3-D)
  - Soporta `--verbose`, `--json`, `--fail-fast`
  - Salida: `X/27 routing matrix | Y/20 batería | TOTAL Z/47`
  - Imprime `SISTEMA HABILITADO PARA R7` cuando todo pasa

### Cómo correr

```powershell
python run_eval.py             # reporte en terminal
python run_eval.py --verbose   # cada caso detallado
python run_eval.py --json      # salida JSON para CI
```

### Criterio de "done" verificado

```
Routing Matrix (27 casos)   27/27
Batería 20 preguntas        20/20
────────────────────────────────
TOTAL : 47/47 — SISTEMA HABILITADO PARA R7
```

---

## R4 — Robustecer memoria por capas

**Prioridad**: 🔴→🟠 Fundamental a Intermedio
**Estado**: ✅ Parcial — capas existen y `MemoryType` está implementado, falta composición explícita

### Ya implementado ✅

- `MemoryType` enum en `schemas.py` (WORKING, SEMANTIC, EPISODIC, PROCEDURAL)
- `get_context_for(intent_type)` — selector por intención
- `episode_store.py` con `search_episodes()` y `experience_lookup()`
- Boost +0.15 para episodios exitosos

### Pendiente 🔲

| Tarea | Descripción | Archivo | Riesgo |
|---|---|---|---|
| R4-A | Definir comportamiento para preguntas que mezclan capas | `app/memory_manager.py` | Medio |
| R4-B | Componer contexto explícito para mezclas episode + work_state | `app/memory_context.py` | Medio |
| R4-C | Test: composición de capas no excede límite de tokens | `tests/test_memory_layer.py` | Bajo |

### Ejemplo de mezcla de capas (R4-A)

```
Pregunta: "¿qué aprendí la sesión pasada y cuál es el foco actual?"

Hoy: heurística (puede responder mal o mezclar)
Después de R4-A:
  ctx = get_episodic_context() + get_working_context()
  # composición explícita, no prompt gigante
```

---

## R5 — Robustecer RAG antes de cambiar modelo

**Prioridad**: 🟠 Intermedio
**Estado**: ✅ Parcial — MMR, fidelity_check y exclusiones ya implementados

### Ya implementado ✅

- MMR con `lambda_mult=0.6`, `fetch_k=20`
- `fidelity_check` con 3 reglas (sin docs, chunks vacíos, respuesta corta)
- Exclusión de documentos vivos del índice (estado_proyecto.md, roadmap.md)
- Detección de papers en retrieval
- 269 chunks desde documentos curados

### Pendiente 🔲

| Tarea | Descripción | Archivo | Riesgo |
|---|---|---|---|
| R5-A | Guardar qué docs fueron usados por respuesta | `app/rag_engine.py` + `metrics.py` | Bajo |
| R5-B | Reporte "top docs más recuperados" para detectar ruido | `show_metrics.py` | Bajo |
| R5-C | Evaluar retrieval con consultas fijas por categoría | `run_eval.py` | Bajo |
| R5-D | Revisar chunking solo si hay fallos repetidos detectados por R5-C | `indexacion.py` | Medio |

---

## R6 — Tools seguras y previsibles

**Prioridad**: 🟠 Intermedio
**Estado**: 🔲 Pendiente — `tool_registry.py` existe, falta clasificación por riesgo y contratos de retorno

### Pendiente 🔲

| Tarea | Descripción | Archivo | Riesgo |
|---|---|---|---|
| R6-A | Clasificar tools por riesgo (lectura / escritura segura / escritura crítica) | `app/tool_registry.py` | Bajo |
| R6-B | Estándar de retorno: `{ok, message, data, side_effect}` | `app/tools.py` | Medio |
| R6-C | Agregar tests de tool contract | `tests/test_tools.py` | Bajo |
| R6-D | Log de toda tool que modifique estado (con input + timestamp) | `app/tools.py` | Bajo |

### Clasificación de tools actual

| Tool | Riesgo | Tipo |
|---|---|---|
| `tool_list_files` | Bajo | Solo lectura |
| `tool_read_file` | Bajo | Solo lectura |
| `tool_save_fact` | Medio | Escritura segura |
| `tool_create_task` | Medio | Escritura segura |
| `tool_complete_task` | Medio | Escritura segura |
| `tool_update_work_state` | Medio | Escritura segura |

---

## R7 — Preparar cambios futuros de modelo

**Prioridad**: 🟡 Avanzado
**Estado**: 🔓 DESBLOQUEADO — R1–R3 completos desde 19/05/2026

### Prerequisito cumplido ✅

- ✅ Batería R3 pasando: `python run_eval.py` → 47/47
- ✅ `show_metrics.py` con infraestructura de baseline lista
- ✅ Aging de caché funcionando (R2-E)

### Pendiente 🔲

| Tarea | Descripción | Archivo | Riesgo |
|---|---|---|---|
| R7-A | Script de benchmark: latencia + calidad sobre batería fija | `benchmark.py` | Bajo |
| R7-B | Abstraer nombre del modelo como constante en `config.py` | `app/config.py` | Bajo |
| R7-C | Documentar proceso de comparación de modelos | `docs/proyecto/cambio-modelo.md` | Bajo |

### Cómo comparar modelos (cuando llegue el momento)

1. Correr `python run_eval.py --json > baseline_llama32.json` con modelo actual
2. Cambiar modelo en `config.py` (una línea)
3. Correr `python run_eval.py --json > baseline_nuevo.json`
4. Comparar routing + tiempos: el modelo nuevo solo gana si mejora ambos

### Error común

Probar otro modelo porque "suena mejor" sin baseline. Casi siempre
hace perder tiempo porque no se sabe si una mejora viene del modelo
o de la arquitectura.

---

## Orden recomendado — estado actualizado 19/05/2026

```
✅ R1 — Contratos internos
✅ R2 — Observabilidad (infraestructura lista, baseline con uso real)
✅ R3 — Evaluación 47 casos con run_eval.py
         ↓
R4-A/B  (composición de capas mixtas)     ← siguiente
R5-A/B  (auditabilidad RAG)               ← en paralelo con R4
R6-A/B  (tools seguras)
         ↓
R7      (comparar modelos con baseline)   ← DESBLOQUEADO
```

---

## Qué NO hacer durante este plan

- ❌ Cambiar de modelo de embeddings sin correr `run_eval.py` primero
- ❌ Migrar a SQLite antes de que episodios superen ~500 entradas
- ❌ Agregar multiagente antes de que un solo agente sea estable y medible
- ❌ Agregar nuevas skills de Fase 9+ antes de completar R4–R5
