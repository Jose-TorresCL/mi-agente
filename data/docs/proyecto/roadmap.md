# Roadmap del proyecto

Última actualización: 10/05/2026  
Fase actual: Fase 5 — Refactor modular y consolidación arquitectural

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

## Prioridades actuales

### 🔴 1. Enriquecer el vector store

**Qué es**: Actualizar los documentos en `data/docs/` para que el RAG
tenga conocimiento real del estado actual del proyecto.

**Por qué ahora**: Sin documentos actualizados, todas las preguntas
documentales al agente se responden con información de Fase 4 o
anterior. Es el techo más bajo del sistema hoy.

**Cómo medirlo**: El agente responde correctamente a:
- "¿qué hace rag_engine.py?" → respuesta correcta con Fase 5
- "¿en qué fase estamos?" → responde Fase 5
- "¿qué es memory_context.py?" → lo describe bien

**Acción concreta**:
```
Actualizar:   data/docs/proyecto/arquitectura_actual.md
              data/docs/proyecto/estado_proyecto.md
Agregar:      data/docs/proyecto/decisiones_arquitectura.md
              data/docs/proyecto/roadmap.md
Luego:        python indexacion.py
```

---

### 🟠 2. memory_manager.py — guardián de la capa de memoria

**Qué es**: Un módulo que centraliza toda lectura y escritura de
memoria estructurada. Ningún otro módulo toca los JSON directamente.

**Por qué ahora**: Hoy `tools.py` escribe directo a JSON. Eso crea
una fuga entre la capa de inteligencia y la capa de memoria. Es la
única fuga arquitectural real que queda.

**Interfaz objetivo**:
```python
memory_manager.get_context()       # ensambla contexto para el prompt
memory_manager.update_state(...)   # actualiza work_state
memory_manager.save_fact(...)      # guarda en project_facts
memory_manager.save_episode(...)   # guarda resumen de sesión
```

**Test arquitectural**: Si cambias cómo se guarda `work_state`,
¿tienes que tocar `chat_ui.py`? Si la respuesta es sí, las capas
siguen pegadas.

---

### 🟡 3. Tests por capa aislada

**Qué es**: Tests que validan una capa sin depender de las otras.

**Por qué**: Los 67 tests actuales validan comportamiento integrado.
Tests por capa validan que los bordes entre capas son reales.

**Tests mínimos**:
- `test_memory_layer.py`: cambiar work_state no toca chat_ui
- `test_intelligence_layer.py`: router clasifica correctamente sin LLM
- `test_rag_engine.py`: RAG retorna respuesta con evidencia real

---

### 🟡 4. Batería de evaluación fija

**Qué es**: 9 preguntas estándar ejecutables con un script que
mide si el sistema responde correctamente.

**Por qué**: Sin evaluación fija no sabes si un cambio mejoró o
empeoró el comportamiento real.

**Preguntas mínimas**:
1. "¿qué tareas tengo pendientes?" → memory
2. "¿qué hace router.py?" → rag
3. "anota que el modelo es llama3.2" → tool_save_fact
4. "¿en qué fase estamos?" → rag
5. "crea una tarea: actualizar docs" → tool_create_task
6. "¿qué hace memory_context.py?" → rag
7. "¿cuál es mi foco actual?" → memory
8. "lista los archivos del proyecto" → tool_list_files
9. "¿cómo funciona el router?" → rag

---

### 🟢 5. Recuperación selectiva de contexto

**Qué es**: Elegir qué tipo de memoria es relevante para cada pregunta,
en lugar de inyectar siempre toda la memoria disponible.

**Mapa de tipos de memoria**:

| Tipo | Cuándo recuperar |
|---|---|
| Working memory | Preguntas sobre foco actual o estado |
| Semántica | Preguntas sobre el proyecto, arquitectura, decisiones |
| Episódica | Preguntas sobre sesiones anteriores, "¿en qué quedamos?" |
| Procedimental | Se activa automáticamente vía router y prompts |

**Por qué es futuro**: Requiere que `memory_manager.py` exista
primero y que los 4 tipos estén bien separados en el código.

---

## Test arquitectural de referencia

Dos preguntas para saber si la arquitectura mejora:

1. Si cambias cómo se guarda `work_state.json`, ¿tienes que tocar
   `chat_ui.py`? → Si sí, las capas siguen pegadas.

2. Si mañana cambias JSON por SQLite, ¿puede sobrevivir `router.py`
   sin enterarse? → Ese debería ser el objetivo.

---

## Métricas de progreso arquitectural

| Métrica | Hoy | Objetivo |
|---|---|---|
| Imports cruzados entre capas | Algunos | Cero |
| Módulos que escriben JSON directo | tools.py | Solo memory_manager |
| Archivos tocados por cada cambio de memoria | 3-4 | 1 |
| Tests por capa aislada | 0 | 3 mínimos |

---

## Historia de fases

| Fase | Foco principal | Estado |
|---|---|---|
| Fase 1 | RAG básico + indexación | ✅ Completa |
| Fase 2 | Memoria estructurada + tools + router simple | ✅ Completa |
| Fase 3A | Router híbrido keywords + LLM | ✅ Completa |
| Fase 3B | Clasificador embeddings + intent_index | ✅ Completa |
| Fase 4 | Caché, fidelity check, episodios, anti-alucinación | ✅ Completa |
| Fase 5 | Refactor modular, 3 capas limpias, 67 tests | 🔄 En curso |
| Fase 6 | memory_manager + recuperación selectiva | 🔲 Pendiente |
