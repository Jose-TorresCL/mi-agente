# Visión del agente — Norte del proyecto

> Este documento no es un plan rígido. Es una brújula.
> Cada etapa puede reordenarse, acelerarse o pausarse según lo que aprendas.
> Lo que no cambia: la dirección.

*Última actualización: 19/05/2026*

---

## La idea central

Un solo agente local que se separa por **modos o capas** según el tipo de tarea.
No múltiples agentes paralelos — un router que construye el contexto correcto
para cada situación y se lo entrega siempre al mismo modelo.

```
Consulta del usuario
       ↓
   [ROUTER]  ← 3 capas: keywords → embeddings → LLM fallback
       ↓
┌───────────────────────────────────────────┐
│  CARRIL: rag       → Chroma + experience_lookup  │
│  CARRIL: memory    → JSON estructurado (TERMINAL)  │
│  CARRIL: episode   → experience_index Chroma       │
│  CARRIL: tool_*    → acciones controladas          │
│  CARRIL: unsupport → respuesta directa, sin LLM    │
└───────────────────────────────────────────┘
       ↓
   [LLM]  ← llama3.2 vía Ollama
       ↓
   metrics.py → metrics.jsonl
```

Esto es esencialmente lo que hacen MemGPT y Cursor AI.
El router híbrido actual ya implementa esta arquitectura completamente.

---

## Etapas

### ✅ Etapa 1 — Base funcional (completada)
**Nivel:** Fundamental

- RAG con Chroma + LangChain (269 chunks, MMR, fidelity_check)
- Router híbrido 3 capas (keywords → embeddings → LLM fallback)
- Memoria en 5 capas (WORKING, SEMANTIC, EPISODIC ×2, RAM)
- MemoryType enum formal en `schemas.py`
- memory_manager como guardián único + get_context_for()
- Caché semántica (solo carril rag, TERMINAL para memory)
- 9 carriles de ejecución estables
- 67+ tests pasando (incluye test_architecture.py)
- Experience Index en Chroma + boost de calidad + señal s/n
- Métricas por turno en `storage/metrics.jsonl`

---

### ✅ Etapa 2 — Acceso al código propio (completada)
**Nivel:** Intermedio

El agente puede leer y listar archivos de su propio proyecto.

- `tool_list_files` — lista archivos del proyecto
- `tool_read_file` — lee contenido de cualquier archivo por ruta
- El router detecta preguntas sobre archivos y rutas
- Carriles `tool_list_files` y `tool_read_file` operativos

> **Nota:** La variante "proponer diffs" (auto-mejora) sigue siendo Etapa 3.

---

### 🎯 Etapa 3 — Observabilidad y evaluación (en curso — Fase 7)
**Nivel:** Intermedio

Tener números que digan si el sistema mejora o empeora con cada cambio.

- **7A ✅** — Logger de métricas por turno (`metrics.jsonl`)
- **7B 🔄** — `show_metrics.py`: tabla en terminal con tiempos y carriles
- **7C 🔲** — Batería RAG ampliada de 9 a 20 preguntas
- **7D 🔲** — Caché con aging: entradas > 7 días se recalculan

---

### 🔭 Etapa 4 — Auto-mejora con diffs
**Nivel:** Avanzado

El agente propone cambios concretos al código en formato diff.
Tú revisas y apruebas. Se aplican con `git apply`.

- El agente genera bloques `diff` o `patch` válidos
- Flujo: propuesta → revisión humana → `git apply` → commit
- Nunca auto-aplica sin aprobación explícita

**Prerequisito:** Etapa 3 completa (métricas para validar que un diff mejora).

---

### 🌌 Etapa 5 — Memoria reflexiva
**Nivel:** Avanzado

El agente consolida aprendizajes propios sobre sí mismo usando
*self-editing memory* (concepto de MemGPT).

- Detecta patrones en sus propias métricas
- Registra observaciones como hechos semánticos
- Requiere Etapa 4 como base

---

## Principios que no cambian

1. **Local primero** — ningún dato sale del equipo
2. **Aprobación humana siempre** — el agente propone, el humano decide
3. **Progresivo y seguro** — cada etapa construye sobre la anterior, nada se tira
4. **Simple antes que elegante** — si funciona con menos, no añadir más

---

## Hardware de referencia

ThinkPad · Intel Core i7 8th gen · 16 GB DDR4 · Sin GPU dedicada

Ver `docs/hardware-modelos.md` para la tabla de modelos compatibles.
