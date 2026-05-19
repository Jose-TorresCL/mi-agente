# Plan de Robustecimiento — Fases R1 a R7

> Última actualización: 19/05/2026  
> Estado general: **R1 parcial ✅, R2 en curso 🔄, R3–R7 pendientes**

## Por qué existe este plan

El proyecto ya tiene una arquitectura madura: orquestación, RAG, memoria por
capas, router híbrido, tools, tests y observabilidad básica. El cuello de
botella ya no es “tener más features” sino hacer lo que existe más
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
| R1 | Endurecer contratos internos | 🔴 Fundamental | ✅ Parcial |
| R2 | Observabilidad completa | 🔴 Fundamental | 🔄 En curso |
| R3 | Evaluación real del sistema | 🟠 Intermedio | 🔲 Pendiente |
| R4 | Robustecer memoria por capas | 🔴→🟠 F/I | ✅ Parcial |
| R5 | Robustecer RAG antes de cambiar modelo | 🟠 Intermedio | ✅ Parcial |
| R6 | Tools seguras y previsibles | 🟠 Intermedio | 🔲 Pendiente |
| R7 | Preparar cambios futuros de modelo | 🟡 Avanzado | 🔲 Pendiente |

---

## R1 — Endurecer contratos internos

**Prioridad**: 🔴 Fundamental  
**Estado**: ✅ Parcial — invariantes de capas ya protegidos, faltan contratos de retorno

### Qué es

Cerrar invariantes entre módulos: quién puede llamar a quién, qué retorna
cada capa y qué fallbacks están permitidos.

### Ya implementado ✅

- Carril `memory` TERMINAL — nunca cae a RAG ni caché
- `unsupported` fuera del flujo LLM/Chroma
- `get_context_for(intent_type)` como interfaz clara entre router y memoria
- `test_architecture.py` — análisis AST que bloquea imports cruzados
- `test_memory_route.py` — carril memory devuelve real, no cacheado
- `test_memory_layer.py` — `get_context_for()` devuelve solo la capa pedida

### Pendiente 🔲

| Tarea | Descripción | Archivo | Riesgo |
|---|---|---|---|
| R1-A | Formalizar `DecisionResult` en `schemas.py` | `app/schemas.py` | Bajo |
| R1-B | Tipar `process_turn()` y retornos de `_decide_*` | `app/intelligence.py` | Bajo |
| R1-C | Test: `intelligence.py` no importa detalles de storage | `tests/test_architecture.py` | Bajo |
| R1-D | Test: `tools.py` no toca `memory_store` directo | `tests/test_architecture.py` | Bajo |
| R1-E | Test: `router.py` no usa Chroma directo | `tests/test_architecture.py` | Bajo |

### Error común

Creer que esto “no agrega nada visible”. En realidad es lo que evita que el
proyecto se vuelva frágil cuando se agregue una skill nueva.

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
**Estado**: 🔄 En curso — Fase 7A completa, 7B–7D pendientes

### Qué es

Medir qué carril se eligió, cuánto tardó retrieval, cuánto tardó el LLM,
cuánto vino de caché y cómo está envejeciendo la caché.

### Ya implementado ✅

- `metrics.py` — logger por turno en `storage/metrics.jsonl`
- Campos: ruta, tiempo retrieval, tiempo LLM, tokens estimados, flag `cached`
- `record_turn()` nunca lanza excepciones (errores van a WARNING)

### Pendiente 🔲 (Fases 7B–7D)

| Tarea | Descripción | Archivo | Riesgo |
|---|---|---|---|
| R2-A (7B) | `show_metrics.py` — tabla ASCII en terminal | `show_metrics.py` | Bajo |
| R2-B | Registrar `intent_type` dentro del carril `memory` | `app/metrics.py` | Bajo |
| R2-C | Guardar número de docs recuperados por consulta RAG | `app/rag_engine.py` + `metrics.py` | Bajo |
| R2-D | Medir tasa “respuesta con evidencia” vs “sin evidencia” | `show_metrics.py` | Bajo |
| R2-E (7D) | Aging del caché: entradas > 7 días se recalculan | `app/semantic_cache.py` | Medio |

### Métricas objetivo

| Métrica | Objetivo |
|---|---|
| Tiempo retrieval Chroma | < 200ms |
| Tiempo LLM | < 8s en ThinkPad i7 8ª gen |
| % respuestas con evidencia documental | ≥ 75% |
| % consultas sin LLM (caché + keywords) | > 30% |
| % cache hits | visible en dashboard |

### Error común

Medir solo latencia total. En un agente hay que separar al menos:
router / retrieval / LLM / caché / tools.

### Validación

```powershell
python show_metrics.py
# Esperado: tabla con tiempos por carril, % cache hit, top docs
```

---

## R3 — Evaluación real del sistema

**Prioridad**: 🟠 Intermedio  
**Estado**: 🔲 Pendiente — batería de 9 preguntas existe, falta estructura de 3 niveles

### Qué es

Convertir la batería de tests en una evaluación de **comportamiento del
agente**, no solo de funciones aisladas. Separar tres niveles:

1. **Routing**: ¿eligió el carril correcto?
2. **Contexto**: ¿trajo la capa correcta de memoria o docs relevantes?
3. **Respuesta**: ¿contestó bien y con evidencia?

### Pendiente 🔲 (Fase 7C ampliada)

| Tarea | Descripción | Archivo | Riesgo |
|---|---|---|---|
| R3-A | Ampliar batería de 9 a 20 preguntas | `tests/eval_battery.py` | Bajo |
| R3-B | Agregar `expected_lane` a cada caso | `tests/eval_battery.py` | Bajo |
| R3-C | Agregar `expected_evidence_source` a cada caso | `tests/eval_battery.py` | Bajo |
| R3-D | Script de reporte: X/20 routing correcto, Y/20 con evidencia | `run_eval.py` | Bajo |

### Matriz de casos por tipo

| Tipo | Ejemplos de pregunta | Carril esperado |
|---|---|---|
| `profile` | "¿Cómo me llamo?" | memory |
| `work_state` | "¿En qué estamos ahora?" | memory |
| `tasks` | "¿Qué tareas hay abiertas?" | memory |
| `episode` | "¿Qué hicimos la sesión pasada?" | episode |
| `rag-doc` | "¿Qué hace intelligence.py?" | rag |
| `rag-paper` | "¿Qué es SLM-First?" | rag |
| `unsupported` | "¿Cuál es la capital de Francia?" | unsupported |
| `tool` | "Crea una tarea: revisar tests" | tool_create_task |
| `exit` | "salir" | exit |

### Error común

Contar un test como “pasó” solo porque devolvió algo. En agentes importa
qué carril tomó y de dónde salió la respuesta.

### Validación

```powershell
python run_eval.py
# Salida esperada:
# 20/20 routing correcto
# 17/20 con evidencia correcta
#  3/20 fallback aceptable
```

---

## R4 — Robustecer memoria por capas

**Prioridad**: 🔴→🟠 Fundamental a Intermedio  
**Estado**: ✅ Parcial — capas existen y `MemoryType` está implementado, falta composición explícita

### Qué es

Hacer que las capas de memoria no solo existan en datos sino que se
comporten distinto en runtime de forma estable.

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
Despues de R4-A:
  ctx = get_episodic_context() + get_working_context()
  # composición explícita, no prompt gigante
```

### Error común

Resolver mezcla de memorias con prompts gigantes en vez de componer
contexto estructurado antes del LLM.

---

## R5 — Robustecer RAG antes de cambiar modelo

**Prioridad**: 🟠 Intermedio  
**Estado**: ✅ Parcial — MMR, fidelity_check y exclusiones ya implementados

### Qué es

Asegurar que el RAG sea confiable, auditable y limpio antes de cambiar
de modelo de embeddings o de generación.

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
| R5-B | Reporte “top docs más recuperados” para detectar ruido | `show_metrics.py` | Bajo |
| R5-C | Evaluar retrieval con consultas fijas por categoría | `run_eval.py` | Bajo |
| R5-D | Revisar chunking solo si hay fallos repetidos detectados por R5-C | `indexacion.py` | Medio |

### Error común

Cambiar de embedding o de modelo cuando el problema real está en
indexación, filtros o selección de contexto.

---

## R6 — Tools seguras y previsibles

**Prioridad**: 🟠 Intermedio  
**Estado**: 🔲 Pendiente — `tool_registry.py` existe, falta clasificación por riesgo y contratos de retorno

### Qué es

Asegurar que las tools no rompan invariantes ni mezclen lógica de
negocio con acceso a disco.

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

### Seguridad

Cualquier tool que modifique estado debe:
- Loguear con timestamp e input
- Validar input antes de escribir
- Nunca borrar silenciosamente
- Poder auditarse desde `metrics.jsonl`

---

## R7 — Preparar cambios futuros de modelo

**Prioridad**: 🟡 Avanzado  
**Estado**: 🔲 Pendiente — no iniciar hasta R1–R3 completos

### Qué es

Dejar listo el sistema para comparar modelos sin reescribir el proyecto.

### Prerequisito obligatorio

Antes de considerar otro modelo local o una nueva skill:
1. Tener batería R3 pasando (20/20 routing + evidencia)
2. Tener `show_metrics.py` con baseline registrado
3. Tener aging de caché funcionando (R2-E)

### Pendiente 🔲

| Tarea | Descripción | Archivo | Riesgo |
|---|---|---|---|
| R7-A | Script de benchmark: latencia + calidad sobre batería fija | `benchmark.py` | Bajo |
| R7-B | Abstraer nombre del modelo como constante en `config.py` | `app/config.py` | Bajo |
| R7-C | Documentar proceso de comparación de modelos | `docs/proyecto/cambio-modelo.md` | Bajo |

### Orden de aprendizaje previo requerido

1. Chunks + embeddings + retriever (Fase 1–3) ✅
2. Memoria por capas (Fase 5D–8D) ✅
3. Evaluación con batería fija (R3) 🔲
4. Métricas baseline (R2) 🔄
5. Recién entonces: comparación de modelos

### Error común

Probar otro modelo porque “suena mejor” sin baseline. Casi siempre
hace perder tiempo porque no se sabe si una mejora viene del modelo
o de la arquitectura.

---

## Orden recomendado de ejecución

```
R2 (7B: show_metrics.py)       ← primera tarea práctica
    ↓
R1 (R1-A a R1-E: contratos)    ← en paralelo con R2, sin riesgo
    ↓
R3 (evaluación 20 casos)       ← requiere R2 para medir bien
    ↓
R4-B (composición de capas)    ← requiere R3 para saber si mejora
R5-A/B (auditabilidad RAG)     ← en paralelo con R4
R6-A/B (tools seguras)         ← no urgente, pero antes de R7
    ↓
R7 (comparar modelos)          ← solo cuando R1–R3 estén completos
```

---

## Qué NO hacer durante este plan

- ❌ Agregar nuevas skills de Fase 9+ antes de completar R1–R3
- ❌ Cambiar de modelo de embeddings sin baseline de R3
- ❌ Migrar a SQLite antes de que episodios superen ~500 entradas
- ❌ Agregar multiagente antes de que un solo agente sea estable y medible
