# SLM-First Architecture — Resumen para mi-agente

> Paper de referencia: "Small Language Models are the Future of Agentic AI" (2025)
> Nivel: Fundamental — describe exactamente lo que ya tienes construido.

---

## Qué propone

La tesis central es que los sistemas de IA agentiva más eficientes **no son un LLM grande haciendo todo**, sino una composición de modelos pequeños especializados donde el LLM grande se invoca selectiva y escasamente.

El paper lo llama arquitectura **"Lego-like"**:
- Los SLMs (Small Language Models) son el **default** — manejan la mayoría de las consultas.
- Los LLMs grandes son la **excepción** — solo se invocan cuando el SLM no puede resolver.
- Se escala **hacia afuera** (más agentes pequeños especializados) en vez de **hacia arriba** (un modelo más grande).

El principio clave: el costo computacional de cada respuesta debe ser proporcional a la dificultad real de la consulta.

---

## Conexión con mi proyecto

El router híbrido de mi-agente **ya implementa SLM-First sin saberlo**:

```
Capa 1 — Keywords (0ms, 0 tokens)
  → Consultas simples: 'chao', 'lista archivos', 'lee router.py'
  → Equivale al SLM conceptual: regla determinista, gratis.

Capa 2 — Intent Index / Embeddings (~200ms)
  → Consultas de intención conocida: 'cómo va el proyecto', 'siguiente paso'
  → Equivale al SLM real: modelo de embeddings pequeño (nomic-embed-text).

Capa 3 — LLM llama3.2 (3-8s, costo alto)
  → Solo cuando capas 1 y 2 no clasifican con certeza.
  → Equivale al LLM grande: se invoca escasamente.
```

Esta arquitectura reduce el uso del LLM a una fracción del total de consultas, que es exactamente el objetivo de SLM-First.

---

## Patrón implementable ahora

### Expansión natural del router actual

El paper sugiere que el SLM de clasificación puede también **generar respuestas simples**, no solo clasificar. En mi proyecto, esto significa:

- Consultas de memoria estructurada (`work_state`, `project_facts`) → respuesta directa desde JSON sin invocar el LLM.
- El LLM solo entra cuando la consulta necesita síntesis, razonamiento o recuperación documental.

Esto ya está parcialmente implementado en el carril `memory` de `intelligence.py`.

### Métrica de eficiencia SLM-First

Una forma de medir si el sistema está cumpliendo el principio:

```
Eficiencia = (consultas resueltas sin LLM) / (total de consultas)
```

Objetivo saludable: > 60% de las consultas resueltas en Capa 1 o Capa 2.
Se puede medir agregando un contador en el log del router.

---

## Lo que NO aplica aún

- **Múltiples SLMs especializados en paralelo**: requiere hardware con GPU dedicada o múltiples procesos independientes. No viable con CPU compartida y RAM limitada.
- **Fine-tuning del SLM de clasificación**: el paper propone entrenar el modelo pequeño con datos del dominio. Para mi-agente, el intent index (Chroma + embeddings) cumple este rol sin fine-tuning.
- **Orquestación dinámica con RL**: se cubre en papers más avanzados (ver paper-moa-resumen.md).

---

## Cuándo volver a este paper

- Cuando el router empiece a tener más de 10 carriles y el LLM fallback sea frecuente.
- Cuando consideres agregar un segundo modelo local (phi3:mini, gemma:2b) como clasificador dedicado.
- Cuando midas que > 40% de las consultas están llegando al LLM sin necesidad real.

---

## Resumen ejecutivo para Lautaro

> Mi router híbrido de 3 capas implementa el patrón SLM-First: las capas de keywords y embeddings filtran la mayoría de las consultas, reservando el LLM para los casos que realmente lo necesitan. La métrica de salud es qué porcentaje de consultas se resuelven sin invocar llama3.2.
