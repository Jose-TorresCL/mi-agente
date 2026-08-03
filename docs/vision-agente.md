# Visión del agente — Norte del proyecto

> Este documento no es un plan técnico. Es la razón de existir del proyecto.
> Lo que construyes hoy es la semilla. Este documento describe el árbol. [file:133]

---

## La idea grande

La mayoría de los asistentes de IA modernos requieren conexión a internet,
APIs de pago y hardware especializado. Eso los hace inaccesibles para
la mayoría de las personas. [file:133][web:191]

Este proyecto demuestra que no tiene que ser así.

Un asistente local, que corre en un ThinkPad sin GPU, que aprende de
cada conversación, que recuerda quién eres y en qué trabajas, que mejora
con el tiempo — sin mandar un solo byte fuera del equipo. [file:133][web:202]

---

## La arquitectura que lo hace posible

Un solo agente. Un solo modelo local. Un router que adapta el contexto
según el tipo de tarea — en lugar de modelos especializados separados. [file:131][file:133]

```text
Consulta del usuario
       ↓
   [ROUTER]  ← entiende la intención (keywords + embeddings + LLM)
       ↓
   [CONTEXTO]  ← construye solo lo necesario a partir de RAG + memoria
       ↓
   [LLM local]  ← responde con lo que sabe + lo que recuerda
       ↓
   [MEMORIA]  ← guarda lo que aprendió (estructurada + episódica)
```

Esto es esencialmente lo que hacen sistemas como MemGPT o Cursor AI:
un solo modelo con modos de memoria diferenciados. La diferencia aquí
es que todo funciona en tu máquina, con tus documentos, sin costo
de infraestructura externa. [file:133][web:191][web:198]

---

## La dirección: autonomía progresiva

El agente no nace autónomo. Gana autonomía en etapas,
siempre con el humano como árbitro final. [file:133]

**Hoy** — Responde, recuerda, recupera documentos relevantes, mantiene
estado de trabajo, completa tareas y registra episodios de sesión. [file:131][file:133]

**Mañana** — Lee su propio código, entiende cómo está construido y ayuda
a mantener la arquitectura alineada con los ADRs. [file:132]

**Después** — Propone mejoras concretas (diffs), el humano revisa y aprueba,
y las métricas permiten saber si la mejora realmente ayuda. [file:133]

**El horizonte** — Aprende de sus propios errores, consolida patrones
a partir de sus métricas y episodios, mejora sus respuestas sin que nadie
se lo pida explícitamente. [web:198]

Cada etapa amplía lo anterior. Nada se tira: se consolida antes de expandir.

---

## El norte que no cambia

Cuatro principios que actúan como filtro para cualquier decisión futura: [file:133]

1. **Local primero** — ningún dato sale del equipo, nunca. [file:133][web:202]
2. **Aprobación humana siempre** — el agente propone, el humano decide.
3. **Progresivo y seguro** — cada mejora construye sobre la anterior, sin destruir lo que funciona.
4. **Accesible por diseño** — si no corre en hardware modesto, no sirve.

---

## Por qué importa más allá del proyecto

Un asistente así — local, barato, que aprende — podría ser
útil para muchas personas que hoy no tienen acceso a estas herramientas. [web:191][web:200]

Ese es el horizonte real: no solo un proyecto personal,
sino una demostración de que la IA útil no requiere infraestructura costosa. [web:200]

---

## Estado actual al 08/2026

Hoy el agente ya cuenta con:

- Router híbrido de 3 capas (keywords, embeddings, LLM fallback) con carriles definidos para RAG, memoria, episodios, tools, exit y unsupported. [file:131][file:133]
- Memoria en capas: trabajo (`work_state`), semántica (`project_facts` y perfil), episódica (JSON de sesiones) y episodios indexados en Chroma (`experience_index`), con `MemoryType` formal. [file:131][file:132]
- Experience Index con señal de calidad (exitoso s/n) y boost en búsqueda semántica para reutilizar sesiones productivas. [file:131][file:133][web:198]
- Fidelity check y caché semántica para mejorar calidad y consistencia de las respuestas en carril RAG. [file:131]
- Tools operativas que leen/escriben memoria estructurada (`tool_create_task`, `tool_complete_task`, `tool_update_work_state`, `tool_save_fact`) con contrato `ToolResult` y clasificación de riesgo (`READ`, `WRITE`, `SYSTEM`). [file:131]
- `tool_registry.py` como router de tools que interpreta texto libre, aplica reglas de seguridad y evita que tools de riesgo `SYSTEM` (como el bot de trading) se ejecuten sin confirmación explícita. [file:131]

Todo esto se mantiene dentro de los principios del norte:
100% local, aprobación humana siempre y foco en hardware modesto. [file:133][web:202]

---

*Última actualización conceptual: 03/08/2026*  
*Revisado con estado técnico al: 08/2026* [file:131][file:133]