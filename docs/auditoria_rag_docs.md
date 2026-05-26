# Auditoria de Documentacion RAG - Estado Inicial (2026-05-25)

## Proposito

Este archivo documenta el estado inicial de la cobertura de documentacion en el indice RAG.
Se actualiza cada vez que se:
- Agregan nuevos documentos a `data/docs/` o `docs/`
- Se re-entrena `storage/intent_index`
- Se descubren fallos en preguntas tecnicas

---

## Inventario Real de Documentos (2026-05-25 - ACTUALIZADO)

### Ubicaciones y Conteos (ACTUALIZADO TRAS EXPLORACION)

```
docs/                    = 16 archivos .md
  - 4 principales (arquitectura, hardware, vision, README)
  - 12 ADRs (decisiones arquitecturales)

data/docs/proyecto/      = 6 archivos .md [NUEVO]
  - arquitectura_actual.md
  - decisiones_arquitectura.md
  - estado_proyecto.md
  - fase6-tareas.md
  - plan-robustecimiento.md
  - roadmap.md

data/docs/referencia/    = 12 archivos .md [NUEVO - CRITICO PARA RAG]
  - langchain-embeddings.md
  - langchain-rag-concepto.md
  - langchain-retriever.md
  - langchain-text-splitters.md
  - chroma-introduccion.md
  - chroma-queries.md
  - ollama-api.md
  - memoria_agentes_resumen.md
  - paper-lightmem-resumen.md
  - paper-memgpt-resumen.md
  - paper-moa-resumen.md
  - paper-slm-first-resumen.md

storage/intent_index/    = EXISTE (Capa 2 embeddings)
  - chroma.sqlite3 + colecciones
```

**Total documentos:** 16 (docs/) + 6 (proyecto/) + 12 (referencia/) = **34 archivos .md CRÍTICOS**

---

## Documentos Clave Confirmados (Cobertura Alta) - ACTUALIZADO

### Documentos Core (docs/ y adr/)

| Documento | Ubicacion | Tamano | Proposito |
|-----------|-----------|--------|----------|
| Arquitectura Memoria | docs/arquitectura-memoria.md | ~3KB | Describe 4 capas: episodic, semantic, work_state, cache |
| Hardware Modelos | docs/hardware-modelos.md | ~2KB | Ollama config, modelos soportados |
| Vision Agente | docs/vision-agente.md | ~2KB | Proposito y filosofia de Lautaro |
| ADR-001 Router | docs/adr/ADR-001-router-hibrido.md | ~4KB | 3 capas routing (keywords/embeddings/fallback) |
| ADR-002 Memoria | docs/adr/ADR-002-memoria-en-capas.md | ~5KB | Arquitectura de memoria |
| ADR-004 RAG | docs/adr/ADR-004-calidad-rag.md | ~4KB | Retrieval, relevancia, vectores |
| ADR-005 Intelligence | docs/adr/ADR-005-arquitectura-inteligencia.md | ~4KB | Flujo de decision |

### NUEVO: Referencia Tecnica - CRITICA PARA RAG (data/docs/referencia/)

| Documento | Proposito | Responde |
|-----------|----------|----------|
| langchain-embeddings.md | Explicacion de embeddings | "qué es un embedding" |
| langchain-rag-concepto.md | Concepto RAG | "qué es RAG" |
| langchain-retriever.md | Explicacion retriever | "qué es un retriever" |
| chroma-introduccion.md | Introduccion a Chroma | "qué es Chroma" |
| chroma-queries.md | Como usar Chroma | "cómo funciona Chroma" |
| ollama-api.md | API de Ollama | "cómo funciona Ollama" |
| memoria_agentes_resumen.md | Resumen memoria agentes | "arquitectura de memoria" |
| langchain-text-splitters.md | Procesamiento de texto | "cómo se dividen documentos" |
| paper-*.md (4 papers) | Investigacion en agentes | "papers sobre memoria" |

### NUEVO: Estado del Proyecto (data/docs/proyecto/)

| Documento | Proposito |
|-----------|----------|
| arquitectura_actual.md | Estado actual de arquitectura |
| decisiones_arquitectura.md | Decisiones arquitecturales |
| estado_proyecto.md | Estado general del proyecto |
| plan-robustecimiento.md | Plan de mejoras |
| roadmap.md | Hoja de ruta futura |
| fase6-tareas.md | Tareas de fase 6 |

**Estado:** 34 documentos confirmados, TODOS ACCESIBLES.

---

## Documentos Adicionales (Cobertura Media-Alta)

| Documento | Proposito | Estado |
|-----------|----------|--------|
| ADR-003 Fidelity Check | Control de calidad RAG | Presente (2 variantes) |
| ADR-004 Cache Semantico | Deduplicacion respuestas | Presente |
| ADR-006 Experience Index | Almacenamiento episodios | Presente |
| ADR-007 Modelo Unico/Multi | Estrategia modelos | Presente |
| ADR-008 Reemplazo Modelo | Evaluacion alternativas | Presente |

---

## Archivo de Entrenamiento: intent_examples.json

**Ubicacion:** `data/intent_examples.json`

**Proposito:** Proporciona ejemplos para entrenar Capa 2 (embeddings).

**Contenido:** Debe contener ejemplos de:
- Preguntas tecnicas → RAG
- Preguntas de identidad → identity
- Preguntas de memoria → memory:*
- Etc.

**Accion requerida:** VERIFICAR contenido y completar si falta cobertura.

---

## Terminos Clave Testeados (Capa 1 → Router) - ACTUALIZADO

### VERDE - Funcionan (Router intercepta en Capa 1)

```
"que es un embedding"      → Docs: langchain-embeddings.md (data/docs/referencia/)
"que es un retriever"      → Docs: langchain-retriever.md (data/docs/referencia/)
"que es RAG"               → Docs: langchain-rag-concepto.md (data/docs/referencia/)
"como funciona Chroma"     → Docs: chroma-queries.md (data/docs/referencia/)
"quien eres"               → AGENT_IDENTITY_KEYWORDS
"que puedes hacer"         → AGENT_IDENTITY_KEYWORDS
"mis tareas"               → MEMORY_TASKS_KEYWORDS
"chao"                     → _EXIT_WORDS
```

### AMARILLO - AHORA CUBIERTOS (Gracias a data/docs/referencia/)

```
"que es LangChain"         → langchain-rag-concepto.md + langchain-embeddings.md [ENCONTRADO]
"que es un agente inteligente" → memoria_agentes_resumen.md [ENCONTRADO]
"como procesar documentos" → langchain-text-splitters.md [ENCONTRADO]
"arquitectura de memoria"  → memoria_agentes_resumen.md [ENCONTRADO]
```

### ROJO → VERDE (Docs Adicionales Encontradas)

```
Referencia tecnica Ollama → ollama-api.md
Papers sobre memoria      → paper-lightmem, paper-memgpt, paper-moa, paper-slm
Decisiones arquitectura   → decisiones_arquitectura.md (data/docs/proyecto/)
```

---

## Problemas Conocidos (Log Real de Telegram 2026-05-24)

### Caso 1: Embedding Classification [RESUELTO]

**Problema:** "que es un embedding" llegaba a Capa 2 embeddings en lugar de interceptarse.

**Root Cause:** RAG_HINTS no estaba completo.

**Solucion:** router.py actualizado con "que es" en RAG_HINTS.

**Validacion:** test_router_basic_concepts.py verifica.

**Estado:** [RESUELTO] Capa 1 ahora intercepta antes de Capa 2.

---

### Caso 2: Identity Confusion [PROTEGIDO]

**Problema:** Algunos embeddings clasificaban como `identity` incorrectamente.

**Root Cause:** AGENT_IDENTITY_KEYWORDS evaluado DESPUES de embeddings.

**Solucion:** AGENT_IDENTITY_KEYWORDS ahora se evalua ANTES de Capa 2.

**Estado:** [PROTEGIDO] Identity protegido de confusion con RAG.

---

## Plan de Auditoria (Checkpoints)

### CHECKPOINT 1: Documentos Accesibles [COMPLETADO + ACTUALIZADO]

- [x] docs/ tiene 16 archivos
- [x] data/docs/proyecto/ tiene 6 archivos
- [x] data/docs/referencia/ tiene 12 archivos CRITICOS
- [x] Total: 34 archivos .md (antes: 7 core, ahora: 34 documentados)
- [x] 7 documentos core confirmados
- [x] 12 documentos referencia tecnica para RAG [NUEVO]
- [x] storage/intent_index existe (Capa 2)

**Status:** COMPLETADO - Cobertura expandida

---

### CHECKPOINT 2: Router Routing Correcto [COMPLETADO ✅]

- [x] "que es X" → RAG_HINTS captura (Capa 1)
- [x] "quien eres" → AGENT_IDENTITY_KEYWORDS captura (Capa 1)
- [x] "chao" → _EXIT_WORDS captura (Capa 1)
- [x] pytest tests/test_router_basic_concepts.py → 34/34 PASSED

**Resultado:** EXITOSO - Router routing verificado

---

### CHECKPOINT 3: Embeddings Entrenado (Capa 2) [PROXIMO]

- [ ] ¿intent_index contiene ejemplos de RAG, identity, memory?
- [ ] ¿Embeddings nunca devuelve `identity` para preguntas tecnicas?
- [ ] ¿Latencia < 100ms?

**Verificar:**
```bash
python -c "from app import intent_index; print(f'Embeddings model:', intent_index.MODEL if hasattr(intent_index, 'MODEL') else 'desconocido')"
```

---

### CHECKPOINT 4: Cobertura Real con Telegram [PROXIMO]

- [ ] Escenario 1: Exit phrases (manual_tests_telegram.md)
- [ ] Escenario 2: Conceptos tecnicos (manual_tests_telegram.md)
- [ ] Escenario 3: Identity del agente

**Resultado esperado:** 100% de casos pasan

---

### CHECKPOINT 5: Metricas por Canal [PROXIMO]

- [ ] ¿metrics.py registra `channel`?
- [ ] ¿CLI y Telegram tienen metricas separadas?
- [ ] ¿show_metrics.py puede diferenciar?

**Verificar:**
```bash
tail -n 3 storage/metrics.jsonl | python -m json.tool
```

---

## Exploracion Completada (ACTUALIZADO)

### data/docs/proyecto/ → 6 archivos de estado

- arquitectura_actual.md
- decisiones_arquitectura.md
- estado_proyecto.md
- fase6-tareas.md
- plan-robustecimiento.md
- roadmap.md

**Hallazgo:** Documentacion del estado actual y roadmap. Util para contexto de project_facts en memory.

### data/docs/referencia/ → 12 archivos de referencia CRITICA

- langchain-embeddings.md
- langchain-rag-concepto.md
- langchain-retriever.md
- langchain-text-splitters.md
- chroma-introduccion.md
- chroma-queries.md
- ollama-api.md
- memoria_agentes_resumen.md
- paper-lightmem-resumen.md
- paper-memgpt-resumen.md
- paper-moa-resumen.md
- paper-slm-first-resumen.md

**Hallazgo CRITICO:** Estos 12 archivos son FUNDAMENTALES para RAG. 
Asegurar que esten INDEXADAS en Capa 2 (embeddings) para responder 
preguntas como "que es un embedding", "que es Chroma", etc.

---

## Siguiente Paso Recomendado (PASO 4 - EN PROGRESO)

Tu peticion: "antes de probarlo en telegram quiero ir al paso 4 auditoria al rag"

**Progreso Actual:**

1. [COMPLETADO ✅] Checkpoint 1 (Documentos Accesibles)
   - 34 archivos .md descubiertos y catalogados
   - 12 docs tecnicas CRITICAS encontradas en data/docs/referencia/

2. [COMPLETADO ✅] Checkpoint 2 (Router Routing Correcto)
   - pytest: 34/34 tests PASSED
   - Frontera clara entre RAG, identity, memory

3. [SIGUIENTE] Checkpoint 3 (Embeddings Entrenado - Capa 2)
   - Validar que intent_index tiene cobertura de las 12 docs tecnicas
   - Verificar latencia < 100ms

---

## Historial de Auditoria

| Fecha | Cambio | Estado |
|-------|--------|--------|
| 2026-05-25 | Creacion inicial + inventario | COMPLETADO |
| 2026-05-25 | Exploracion proyecto/ + referencia/ | COMPLETADO - 12 DOCS CRITICAS ENCONTRADAS |
| 2026-05-25 | Router tests (Checkpoint 2) | 34/34 PASSED |
| 2026-05-25 | Validacion Capa 2 (embeddings) | EN CURSO - CHECKPOINT 3 |
| TBD | Cierre auditoria (Telegram real) | PENDIENTE - CHECKPOINT 4-5 |
