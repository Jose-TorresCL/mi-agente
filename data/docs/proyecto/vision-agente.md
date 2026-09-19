# Visión del agente — Norte del proyecto

> Este documento no es un plan rígido. Es una brújula.
> Cada etapa puede reordenarse, acelerarse o pausarse según lo que aprendas.
> Lo que no cambia: la dirección.

*Última actualización: 19/09/2026*

---

## La idea central

Un solo asistente local que se organiza por **carriles y capas** según el tipo
de tarea. No múltiples agentes paralelos: un router selecciona la fuente y el
contexto adecuados, y el mismo modelo local responde o ejecuta una acción
controlada.

```text
Consulta del usuario
       ↓
   [ROUTER] ← keywords → embeddings → fallback RAG
       ↓
┌─────────────────────────────────────────────────────────────┐
│ rag         → documentos Chroma + experiencia episódica      │
│ memory      → JSON estructurado y recuperación selectiva     │
│ episode     → experience_index de sesiones                   │
│ tool_*      → acciones controladas de lectura/escritura      │
│ SYSTEM      → integración externa opcional, bloqueada         │
│ especiales  → identity, math, unsupported, exit              │
└─────────────────────────────────────────────────────────────┘
       ↓
 [LLM local vía Ollama] o respuesta/herramienta directa
       ↓
metrics.py → storage/logs/metrics.jsonl
```

El diseño separa intención, recuperación, decisión y efectos laterales. La
meta no es añadir autonomía sin control: es que Lautaro decida bien, actúe con
seguridad, recuerde selectivamente y permita retomar trabajo entre sesiones.

La integración `bot_trading` es una excepción controlada al núcleo local:
consulta datos externos de mercado mediante `subprocess`, está clasificada como
`RiskLevel.SYSTEM`, queda bloqueada por defecto y es estrictamente de solo
lectura. No ejecuta órdenes ni modifica balances.

---

## Etapas

### ✅ Etapa 1 — Base funcional y consolidación inicial

**Nivel:** Fundamental

- RAG local con Chroma y LangChain.
- Router híbrido: keywords → embeddings → fallback RAG.
- Memoria estructurada: perfil, hechos, estado de trabajo, tareas y episodios.
- Recuperación selectiva mediante `memory_manager` y `get_context_for()`.
- Caché semántica limitada al carril RAG; memoria es un carril terminal.
- Experience Index en Chroma para recuperar episodios relevantes.
- `fidelity_check` para reducir respuestas RAG sin soporte documental.
- Tools controladas para lectura de archivos y operaciones de memoria.
- Métricas por turno en `storage/logs/metrics.jsonl`.
- Suite automatizada para arquitectura, router, memoria, tools y evaluación.

---

### ✅ Etapa 2 — Acceso seguro al código propio

**Nivel:** Intermedio

El asistente puede inspeccionar su propio proyecto sin ejecutar acciones
arbitrarias sobre el sistema.

- `tool_list_files` para listar archivos permitidos.
- `tool_read_file` para leer archivos por ruta validada.
- Router con detección específica de consultas sobre archivos.
- Separación entre tools de lectura, escritura segura y herramientas `SYSTEM`.
- `tool_plan_retoma` para consultar el plan de retoma documental sin modificarlo.

---

### 🎯 Etapa 3 — Observabilidad y evaluación continua

**Nivel:** Intermedio

Tener evidencia para decidir si un cambio mejora o empeora el sistema.

- Logger de métricas por turno con versión de esquema y baseline.
- Dashboard `show_metrics.py` para distribución de carriles, tiempos, caché y fidelity.
- Evaluación repetible mediante `run_eval.py`.
- Baseline operativo `septiembre-13` para comparar cambios recientes sin mezclar
  telemetría histórica incompleta.
- Las métricas históricas se conservan como registro evolutivo; los análisis de
  calidad y rendimiento deben indicar qué baseline y qué registros usan.

**Objetivo actual:** medir antes y después de cada cambio de routing, memoria,
RAG, prompt o tool. No cambiar de modelo solo porque “suena mejor”.

---

### 🧱 Etapa 4 — Consolidación de memoria, router y tools

**Nivel:** Fundamental a Intermedio

Antes de ampliar capacidades, Lautaro debe ser predecible en los flujos que ya
usa todos los días.

- Refinar respuestas de memoria para tareas, foco, episodios y recomendaciones.
- Mantener el router robusto ante variantes de lenguaje y evitar que carriles
  específicos caigan a RAG sin datos estructurados.
- Definir y probar contratos claros para las tools.
- Mejorar trazabilidad: canal de origen, efectos laterales y resultados de tool.
- Mantener documentación, código y pruebas alineados.
- Aplicar cambios pequeños, reversibles y medibles.

---

### 🔭 Etapa 5 — Auto-mejora asistida con diffs

**Nivel:** Avanzado

Lautaro podrá proponer cambios concretos al código en formato diff, pero la
persona usuaria conserva la decisión y la ejecución.

- Flujo: observación → propuesta → revisión humana → diff → pruebas → commit.
- Los cambios deben incluir criterio de terminado y prueba mínima.
- Nunca auto-aplica cambios ni ejecuta acciones sensibles sin aprobación.
- Las métricas y la batería de evaluación sirven para comprobar si un cambio
  realmente mejora el comportamiento.

**Prerequisito:** las etapas de observabilidad y consolidación deben estar
suficientemente firmes.

---

### 🌌 Etapa 6 — Memoria reflexiva

**Nivel:** Avanzado

El asistente podrá extraer aprendizajes sobre su propio comportamiento a partir
de episodios, evaluación y métricas, sin modificar el código de manera
autónoma.

- Detectar patrones de routing, latencia, abstención y errores evitados.
- Proponer mejoras basadas en evidencia.
- Registrar observaciones verificables en memoria o documentación.
- Mantener revisión humana antes de convertir una observación en cambio de
  código o política.

---

## Principios que no cambian

1. **Local primero** — el razonamiento, la memoria, los índices y el RAG se
   ejecutan localmente con Ollama, Chroma y archivos del proyecto.

2. **Fronteras externas explícitas** — una integración externa, como
   `bot_trading`, debe estar aislada, documentada, con timeout, contrato de
   retorno y nivel de riesgo claro. El acceso a datos externos no convierte a
   Lautaro en un sistema de ejecución autónoma.

3. **Aprobación humana siempre** — Lautaro propone; la persona usuaria revisa,
   confirma y decide, especialmente ante escritura, rutas externas, credenciales
   o herramientas `SYSTEM`.

4. **Progresivo y seguro** — cada etapa construye sobre una base probada. Se
   prefieren mejoras pequeñas, reversibles y con pruebas antes que migraciones
   grandes.

5. **Simple antes que elegante** — si una solución de reglas, datos
   estructurados y tests resuelve el problema, no añadir complejidad de agentes,
   modelos o automatizaciones.

6. **Medir antes de concluir** — una mejora debe poder comprobarse mediante
   prueba mínima, evaluación repetible, métrica o evidencia observada.

---

## Límites actuales

- Lautaro no ejecuta órdenes de trading ni modifica balances.
- Las tools `SYSTEM` están bloqueadas hasta habilitación y confirmación
  explícitas.
- La memoria no sustituye documentación ni pruebas: recupera contexto, pero las
  decisiones de arquitectura deben quedar documentadas.
- El modelo local puede ser lento en consultas RAG largas; la arquitectura debe
  reducir llamadas innecesarias antes de proponer un cambio de modelo.
- La auto-mejora es asistida: generar propuestas no autoriza aplicarlas.

---

## Documentos relacionados

- [Arquitectura actual](arquitectura_actual.md)
- [Arquitectura de memoria](arquitectura-memoria.md)
- [Plan de robustecimiento](plan-robustecimiento.md)
- [Integración con bot_trading](integracion_bot_trading.md)
- [Índice de decisiones de arquitectura](decisiones_arquitectura.md)
- [ADRs](../adr/README.md)
- [Hardware y modelos](hardware-modelos.md)