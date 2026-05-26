# Batería manual — Telegram / CLI

**Versión 2026-05-25** — Actualizada con casos reales del log de Telegram.

Ejecuta esta batería después de cualquier cambio en `router.py`, `chat_core.py`,
`intelligence.py`, `prompts.py` o `formatters.py`.

No requiere pytest. Es una checklist de uso real para correr mientras tienes
Telegram abierto o la CLI activa.

---

## Escenario 1 — Flujo de salida (Exit)

**Propósito:** Verificar que frases de salida NO generan identidad de Lautaro.

Mensajes a enviar (uno por uno):

```
chao
```

```
Adiós
```

```
cerrar sesión
```

```
nos vemos
```

```
exit
```

**Resultado esperado en todos:**
- Mensaje de despedida corto (ej: "¡Hasta luego!").
- La sesión termina. NO aparece el bloque de identidad de Lautaro.
- En CLI: el proceso termina.
- En Telegram: el bot responde la despedida y no procesa más mensajes de esa sesión.

**Checklist:**
- [ ] `chao` → Respuesta: _______________ | ¿Tiene identidad? S/N
- [ ] `Adiós` → Respuesta: _______________ | ¿Tiene identidad? S/N
- [ ] `cerrar sesión` → Respuesta: _______________ | ¿Tiene identidad? S/N
- [ ] `nos vemos` → Respuesta: _______________ | ¿Tiene identidad? S/N
- [ ] `exit` → Respuesta: _______________ | ¿Tiene identidad? S/N

---

## Escenario 2 — Conceptos técnicos (RAG — Caso Real del Log)

**Propósito:** Verificar que preguntas sobre embeddings, retriever, Chroma van a RAG (docs),
NO a identity (respuesta fija de Lautaro).

**Log real observado (2026-05-24):**
```
User: "qué es un embedding"
Router: → rag (correcto, fue a embeddings y luego rag)
Response: [basada en langchain-*.md, NOT respuesta de identidad]
```

Mensajes a enviar (uno por uno):

```
qué es un embedding
```

```
qué es un retriever
```

```
cómo funciona Chroma
```

```
qué es un vector store
```

```
qué es LangChain
```

**Resultado esperado:**
- Cada respuesta es concreta, basada en la documentación del proyecto.
- NO repite la misma respuesta para preguntas distintas.
- NO muestra el mensaje de identidad de Lautaro (bloque "Soy un agente inteligente...").
- Fuentes/referencias mostradas al final (ej: "Basado en: docs/arquitectura-memoria.md").

**Checklist:**
- [ ] `qué es un embedding`
  - Respuesta: _________________________________
  - ¿Es técnica (basada en docs)? S/N
  - ¿Tiene identidad de Lautaro? S/N
  - Fuente mencionada: _____________

- [ ] `qué es un retriever`
  - Respuesta: _________________________________
  - ¿Diferente de la anterior? S/N
  - ¿Tiene identidad? S/N
  - Fuente mencionada: _____________

- [ ] `cómo funciona Chroma`
  - Respuesta: _________________________________
  - ¿Tiene identidad? S/N
  - Fuente mencionada: _____________

- [ ] `qué es un vector store`
  - Respuesta: _________________________________
  - ¿Tiene identidad? S/N

- [ ] `qué es LangChain`
  - Respuesta: _________________________________
  - ¿Tiene identidad? S/N

---

## Escenario 3 — Identidad del Agente (Boundary Check)

**Propósito:** Verificar que preguntas sobre Lautaro SÍ generan identidad,
y que no se mezcla con conceptos técnicos.

Mensajes a enviar:

```
quién eres
```

```
qué puedes hacer
```

```
para qué sirves
```

**Resultado esperado:**
- Respuesta con bloque de identidad de Lautaro (ej: "Soy un agente inteligente...").
- Describe capacidades concretas (crear tareas, guardar hechos, etc.).
- NO contiene información técnica sobre embeddings o Chroma.

**Checklist:**
- [ ] `quién eres` → Muestra identidad de Lautaro? S/N
- [ ] `qué puedes hacer` → Describe capacidades? S/N
- [ ] `para qué sirves` → Responde en primera persona (Lautaro)? S/N

---

## Escenario 4 — Gestión de tareas

**Propósito:** Verificar que el carril 'tool_create_task' y memoria funcionan end-to-end.

Mensajes a enviar:

```
crea una tarea: revisar la batería manual
```

```
tareas pendientes
```

```
marca como completada la tarea de revisar la batería manual
```

```
tareas
```

**Resultado esperado:**
- La tarea se crea con ID único (ej: T-MMDDHHMMSS).
- Aparece en la lista de pendientes.
- Al marcar como completada, desaparece de pendientes.
- La segunda lista de tareas no la muestra.

**Checklist:**
- [ ] Creación OK? S/N → ID generado: ___________
- [ ] Aparece en lista? S/N
- [ ] Marca como completada OK? S/N
- [ ] Desaparece de pendientes? S/N

---

## Escenario 5 — Gestión del estado de trabajo

**Propósito:** Verificar que memory:work_state se guarda y recupera.

Mensajes a enviar:

```
estoy trabajando en optimizar el router
```

```
cuál es mi foco actual
```

```
qué estoy haciendo ahora
```

**Resultado esperado:**
- Primera pregunta: se guarda silenciosamente.
- Segunda y tercera: recuperan el texto guardado.
- No hay duplicación ni pérdida de contexto.

**Checklist:**
- [ ] ¿Se guardó el estado sin error? S/N
- [ ] ¿Recupera el estado correcto? S/N
- [ ] ¿Las respuestas son consistentes? S/N

---

## Escenario 6 — Guardar un hecho del proyecto

**Propósito:** Verificar 'tool_save_fact' y recuperación.

Mensajes a enviar:

```
guarda esto: el router tiene 3 capas de decisión
```

```
hechos del proyecto
```

**Resultado esperado:**
- Primer mensaje: confirmación "✅ Hecho guardado".
- Segundo: lista incluye el hecho guardado.

**Checklist:**
- [ ] ¿Se guardó el hecho? S/N → Confirmación: ________________
- [ ] ¿Aparece en 'hechos del proyecto'? S/N

---

## Nota de Depuración

Si algún test falla:

1. **Exit falla (muestra identidad):**
   - Revisar `_EXIT_WORDS` en `app/router.py`
   - Ejecutar: `pytest tests/test_exit_flow.py -v`

2. **Conceptos técnicos van a identity:**
   - Revisar `RAG_HINTS` en `app/router.py` (Capa 1)
   - Revisar `storage/intent_index/` (Capa 2 embeddings)
   - Ejecutar: `pytest tests/test_router_basic_concepts.py -v`

3. **Tareas no se guardan:**
   - Revisar `storage/tasks.json`
   - Ejecutar: `python -c "from app.tools import *; print('tools OK')"`

4. **Latencia en Telegram:**
   - Revisar logs: `tail -f storage/logs/agent.log`
   - Metrics: `python show_metrics.py`
- [ ] Marcada como completada OK S/N
- [ ] Desaparece de la lista S/N

---

## Escenario 4 — Memoria y estado de trabajo

```
en qué estamos trabajando
```
```
cuál es mi foco actual
```
```
qué aprendimos la sesión anterior
```

**Resultado esperado:**
- `en qué estamos trabajando` → devuelve `work_state.md` (foco, siguiente paso, bloqueos).
- `cuál es mi foco actual` → igual, del estado de trabajo.
- `qué aprendimos la sesión anterior` → episodios de sesiones anteriores desde `episode_store`.

**Resultado observado:**
- [ ] work_state devuelto OK S/N
- [ ] episodios devueltos OK S/N → ¿hay episodios disponibles? S/N

---

## Escenario 5 — Identidad (NO debe dispararse por error)

```
quién eres
```
```
qué puedes hacer
```

**Resultado esperado:**
- Bloque de identidad de Lautaro (esto SÍ es correcto aquí).
- Solo debe aparecer cuando el usuario lo pide explícitamente.

**Resultado observado:**
- [ ] Identidad aparece correctamente al preguntar S/N
- [ ] ¿Apareció identidad en algún escenario donde NO debía? S/N → ¿Cuál? _______

---

## Notas de la sesión de prueba

Fecha: _______
Versión/commit: _______
Canal: [ ] CLI  [ ] Telegram
Modelo Ollama: _______

Observaciones:

---

## Historial de ejecuciones

| Fecha | Canal | Modelo | Escenario 1 | Escenario 2 | Escenario 3 | Escenario 4 | Notas |
|-------|-------|--------|:-----------:|:-----------:|:-----------:|:-----------:| ----- |
| 2026-05-25 | Telegram | llama3 | Bugs exit | RAG genérico | OK | OK | observado en producción |
