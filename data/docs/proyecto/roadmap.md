# Roadmap del proyecto

> ⚠️ **Documento vivo** — última actualización: 17/05/2026  
> Las fases completadas son registro histórico permanente.  
> Solo la sección "Prioridades actuales" describe el estado real hoy.

Fase actual: **Fase 6 — Memory Manager y recuperación selectiva**

---

## Principio de priorización

> Antes de agregar, consolida.
> Antes de crecer, limpia las fronteras.

Cada prioridad se clasifica como:
- 🔴 Crítico — bloquea el crecimiento sano del sistema
- 🟠 Importante — mejora significativa sin riesgo alto
- 🟡 Útil — genera valor sin urgencia
- 🟢 Futuro — deseable cuando las bases estén firmes

---

## Prioridades actuales (Fase 6)

### 🔴 1. Fix estructural del caché semántico

**Qué es**: El caché semántico está actuando como cortocircuito global
que se activa antes de que el carril `memory` llegue a su lógica real.
El caché solo debe existir en el carril `rag`, nunca en `memory`.

**Por qué ahora**: Sin este fix, el agente puede responder con entradas
cacheadas obsoletas incluso para preguntas de estado actual.

**Cómo medirlo**: Preguntar "¿en qué fase estamos?" siempre devuelve
el estado real desde `work_state.json`, nunca desde el caché.

---

### 🟠 2. Recuperación selectiva de contexto

**Qué es**: Elegir qué tipo de memoria es relevante para cada pregunta,
en lugar de inyectar siempre toda la memoria disponible.

**Por qué ahora**: `memory_manager.py` ya existe. Este es el siguiente
paso natural para que la recuperación sea inteligente.

**Mapa de tipos de memoria**:

| Tipo | Cuándo recuperar |
|---|---|
| Working memory | Preguntas sobre foco actual o estado |
| Semántica | Preguntas sobre proyecto, arquitectura, decisiones |
| Episódica | Preguntas sobre sesiones anteriores, "¿en qué quedamos?" |
| Procedimental | Se activa automáticamente vía router y prompts |

---

### 🟡 3. Tests por capa aislada

**Qué es**: Tests que validan una capa sin depender de las otras.

**Tests mínimos**:
- `test_memory_layer.py`: cambiar work_state no toca chat_ui
- `test_intelligence_layer.py`: router clasifica sin LLM
- `test_rag_engine.py`: RAG retorna respuesta con evidencia real

---

### 🟡 4. Distinción formal de 4 tipos de memoria en código

**Qué es**: Implementar interfaces separadas para working, semántica,
episódica y procedimental dentro de `memory_manager.py`.

**Por qué**: Hoy `memory_manager` es un guardián que centraliza —
el siguiente nivel es que distinga activamente qué tipo de memoria
corresponde a cada operación.

---

## Test arquitectural de referencia

Dos preguntas para saber si la arquitectura mejora:

1. Si cambias cómo se guarda `work_state.json`, ¿tienes que tocar
   `chat_ui.py`? → Si sí, las capas siguen pegadas.

2. Si mañana cambias JSON por SQLite, ¿puede sobrevivir `router.py`
   sin enterarse? → Ese debería ser el objetivo.

---

## Métricas de progreso arquitectural

| Métrica | Hoy (17/05) | Objetivo |
|---|---|---|
| Imports cruzados entre capas | Mínimos | Cero |
| Módulos que escriben JSON directo | Solo memory_manager | Solo memory_manager |
| Archivos tocados por cambio de memoria | 1–2 | 1 |
| Tests por capa aislada | 0 | 3 mínimos |
| Docs de baja calidad en el índice | 0 (excluidos) | 0 |

---

## Historia de fases

| Fase | Foco principal | Estado |
|---|---|---|
| Fase 1 | RAG básico + indexación | ✅ Completa |
| Fase 2 | Memoria estructurada + tools + router simple | ✅ Completa |
| Fase 3A | Router híbrido keywords + LLM | ✅ Completa |
| Fase 3B | Clasificador embeddings + intent_index | ✅ Completa |
| Fase 4 | Caché, fidelity check, episodios, anti-alucinación | ✅ Completa |
| Fase 5 | Refactor modular, 3 capas limpias, memory_manager, 67+ tests | ✅ Completa |
| Fase 6 | Fix caché + recuperación selectiva + tests por capa | 🔄 En curso |
| Fase 7 | 4 tipos de memoria con interfaces separadas | 🔲 Pendiente |
