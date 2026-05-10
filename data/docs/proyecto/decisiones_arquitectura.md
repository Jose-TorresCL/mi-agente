# Decisiones de arquitectura — ADRs

Este documento registra las decisiones de diseño del proyecto,
por qué se tomaron y qué alternativas se descartaron.
Sirve como memoria procedimental del sistema: explica el *porqué*
de cómo está construido.

---

## ADR-001 — Separación en 3 capas

**Fecha**: 10/05/2026  
**Decisión**: Organizar el sistema en 3 capas con dirección
unidireccional de dependencias:

```
Conversación → Inteligencia → Memoria
```

**Por qué**: Mezclar "hablar", "pensar" y "recordar" en el mismo
lugar hace frágil al agente cuando crece. La separación permite
evolucionar cada capa sin romper las otras.

**Regla operativa**:
- La conversación puede llamar a la inteligencia
- La inteligencia puede usar la memoria
- La memoria NO debe importar nada de la capa de conversación
- El router NO escribe JSON directamente

**Alternativa descartada**: Todo en `chat_core.py`. Descartado porque
cada mejora nueva rompía otra cosa.

---

## ADR-002 — Router híbrido 3 capas

**Fecha**: 06/05/2026  
**Decisión**: El router usa tres capas en cascada:
1. Keywords (0ms) — clasificación sin modelo
2. Embeddings con nomic-embed-text (~50ms) — similitud semántica
3. LLM fallback (~3-8s) — solo para frases nuevas o ambiguas

**Por qué**: El LLM fallback solo tarda 3-8s, pero si se usa para
todo degrada la experiencia. Keywords cubre ~80% de las frases
cotidianas gratis. Embeddings cubre otro ~18% en ~50ms.

**Alternativa descartada**: Solo LLM para clasificar. Descartado
por latencia y costo en cada consulta.

---

## ADR-003 — Chroma para RAG y para intent_index por separado

**Fecha**: 06/05/2026  
**Decisión**: Dos colecciones Chroma independientes:
- `storage/chroma/` — documentos del proyecto (RAG)
- `storage/intent_index/` — ejemplos de intención (router Capa 2)

**Por qué**: Mezclarlas en una sola colección contaminaría los
resultados de búsqueda. Una pregunta documental no debe competir
con un ejemplo de intención en el mismo índice.

---

## ADR-004 — Memoria en 4 tipos diferenciados

**Fecha**: 10/05/2026  
**Decisión**: La capa de memoria del agente distingue 4 tipos:

| Tipo | Archivo | Para qué |
|---|---|---|
| Working / operacional | `work_state.json` | Foco actual, próximo paso |
| Semántica | `project_facts.json`, `profile.json` | Lo que el agente "sabe" establemente |
| Episódica | `episodic_memory.json` | Lo que pasó en sesiones anteriores |
| Procedimental | `router.py`, `prompts.py` | Cómo se comporta el agente |

**Por qué**: No todo recuerdo cumple la misma función. Mezclarlos
en un solo "JSON de memoria" hace que la recuperación sea genérica
e imprecisa.

**Pendiente**: `memory_manager.py` como guardián formal que aplique
estas reglas al leer y escribir.

---

## ADR-005 — config.py como fuente única de constantes

**Fecha**: 08/05/2026  
**Decisión**: Todas las constantes del sistema (modelo, URL, umbrales,
rutas) viven en `app/config.py`. Ningún módulo hardcodea valores.

**Por qué**: Antes de `config.py`, el mismo string `"llama3.2"` o
`"http://localhost:11434"` aparecía en múltiples archivos. Un cambio
de modelo requería editar 4 archivos distintos.

---

## ADR-006 — tool_registry.py como despachador central

**Fecha**: 08/05/2026  
**Decisión**: Todas las tools pasan por `tool_registry.py` como
punto único de despacho. Ningún módulo llama a una tool directamente.

**Por qué**: Sin registro centralizado, agregar una tool nueva requería
editar el router, el chat_core y la tool misma. Con el registry, solo
hay que registrar la tool en un lugar.

---

## ADR-007 — rag_engine.py como módulo independiente

**Fecha**: 08/05/2026  
**Decisión**: El RAG vive en `app/rag_engine.py`, separado de
`chat_core.py`. Incluye caché semántica y fidelity check internamente.

**Por qué**: Antes, la lógica de retrieval estaba entremezclada con
la orquestación del chat. Eso hacía imposible testear el RAG de
forma aislada o mejorar su umbral sin arriesgar el flujo general.

---

## ADR-008 — Modular monolith como estrategia de escalado

**Fecha**: 10/05/2026  
**Decisión**: El proyecto crece como modular monolith: una sola app,
un solo repo, despliegue simple, pero módulos bien separados con
fronteras explícitas.

**Por qué**: Microservicios agregarían complejidad de red, orquestación
y despliegue que no conviene para un asistente local personal en
etapa de aprendizaje.

**Cuándo revisitar**: Si el sistema necesita ejecutar componentes en
máquinas distintas, o si el modelo de lenguaje debe ser intercambiable
en caliente, se puede extraer `rag_engine` o `memory_manager` como
servicio independiente.
