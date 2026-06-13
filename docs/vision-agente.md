# Visión del agente — Norte del proyecto

> Este documento no es un plan técnico. Es la razón de existir del proyecto.
> Lo que construyes hoy es la semilla. Este documento describe el árbol.

---

## La idea grande

La mayoría de los asistentes de IA modernos requieren conexión a internet,
APIs de pago y hardware especializado. Eso los hace inaccesibles para
el 90% de las personas en el mundo.

Este proyecto demuestra que no tiene que ser así.

Un asistente local, que corre en un ThinkPad sin GPU, que aprende de
cada conversación, que recuerda quién eres y en qué trabajas, que mejora
con el tiempo — sin mandar un solo byte fuera del equipo.

---

## La arquitectura que lo hace posible

Un solo agente. Un solo modelo. Un router que adapta el contexto
según el tipo de tarea — en lugar de modelos especializados separados.

```
Consulta del usuario
       ↓
   [ROUTER]  ← entiende la intención
       ↓
   [CONTEXTO]  ← construye solo lo necesario
       ↓
   [LLM local]  ← responde con lo que sabe + lo que recuerda
       ↓
   [MEMORIA]  ← guarda lo que aprendió
```

Esto no es nuevo — es lo que hacen sistemas como MemGPT o Cursor AI.
La diferencia: funciona en tu máquina, con tus documentos, sin costo.

---

## La dirección: autonomía progresiva

El agente no nace autónomo. Gana autonomía en etapas,
siempre con el humano como árbitro final.

**Hoy** — Responde, recuerda, recupera documentos relevantes.

**Mañana** — Lee su propio código. Entiende cómo está construido.

**Después** — Propone mejoras concretas. El humano revisa y aprueba.

**El horizonte** — Aprende de sus propios errores. Consolida patrones.
Mejora sus respuestas sin que nadie se lo pida.

Cada etapa amplía lo anterior. Nada se tira.

---

## El norte que no cambia

Cuatro principios que actúan como filtro para cualquier decisión futura:

1. **Local primero** — ningún dato sale del equipo, nunca
2. **Aprobación humana siempre** — el agente propone, el humano decide
3. **Progresivo y seguro** — cada mejora construye sobre la anterior
4. **Accesible por diseño** — si no corre en hardware modesto, no sirve

---

## Por qué importa más allá del proyecto

Un asistente así — local, barato, que aprende — podría ser
útil para millones de personas que hoy no tienen acceso a estas herramientas.

Ese es el horizonte real: no solo un proyecto personal,
sino una demostración de que la IA útil no requiere infraestructura costosa.

---

## Estado actual al 06/2026

Hoy el agente ya cuenta con:

- Router híbrido de 3 capas (keywords, embeddings, fallback RAG) con 16 carriles bien definidos.
- Memoria en 4 capas (trabajo, semántica, episódica y procedural) con contratos formales.
- Experience index con decay temporal para resumir y reutilizar episodios pasados.
- Fidelity check y caché semántica para mejorar la calidad y consistencia de las respuestas.

Todo esto se mantiene dentro de los principios del norte: 100% local,
aprobación humana siempre y foco en hardware modesto.

---

*Última actualización conceptual: 19/05/2026*
*Revisado con estado técnico al: 06/2026*
