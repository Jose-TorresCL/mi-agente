# Batería manual — Telegram / CLI

Ejecuta esta batería después de cualquier cambio en `router.py`, `chat_core.py`,
`intelligence.py`, `prompts.py` o `formatters.py`.

No requiere pytest. Es una checklist de uso real para correr mientras tienes
Telegram abierto o la CLI activa.

---

## Escenario 1 — Flujo de salida

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
- En CLI: el proceso termina. En Telegram: el bot responde la despedida y no procesa más mensajes de esa sesión.

**Resultado observado (completar al probar):**
- [ ] `chao` → _______
- [ ] `Adiós` → _______
- [ ] `cerrar sesión` → _______
- [ ] `nos vemos` → _______
- [ ] `exit` → _______

---

## Escenario 2 — Conceptos técnicos (RAG)

Mensajes a enviar:

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

**Resultado esperado:**
- Respuesta concreta basada en la documentación del proyecto (langchain-*.md, ADR-004, arquitectura_actual.md).
- NO repite el mismo bloque genérico para preguntas distintas.
- NO muestra el mensaje de identidad de Lautaro.
- Fuentes mostradas al final de cada respuesta.

**Resultado observado:**
- [ ] `qué es un embedding` → ¿Respuesta diferenciada? S/N
- [ ] `qué es un retriever` → ¿Respuesta diferenciada? S/N
- [ ] `cómo funciona Chroma` → ¿Respuesta diferenciada? S/N
- [ ] `qué es un vector store` → ¿Respuesta diferenciada? S/N
- [ ] ¿Alguna respuesta fue idéntica a otra? _______

---

## Escenario 3 — Gestión de tareas

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
- La tarea se crea con ID único (T-MMDDHHMMSS).
- Aparece en la lista de pendientes.
- Al marcar como completada, desaparece de pendientes.
- La segunda lista de tareas no la muestra.

**Resultado observado:**
- [ ] Creación OK S/N → ID generado: _______
- [ ] Aparece en lista S/N
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
