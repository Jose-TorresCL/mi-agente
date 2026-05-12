# Visión del agente — Norte del proyecto

> Este documento no es un plan rígido. Es una brújula.
> Cada etapa puede reordenarse, acelerarse o pausarse según lo que aprendas.
> Lo que no cambia: la dirección.

---

## La idea central

Un solo agente local que se separa por **modos o capas** según el tipo de tarea.
No múltiples agentes paralelos — un router que construye el contexto correcto
para cada situación y se lo entrega siempre al mismo modelo.

```
Consulta del usuario
       ↓
   [ROUTER]  ← decide el modo
       ↓
┌─────────────────────────────────────────┐
│  MODO: conversación  → contexto liviano │
│  MODO: rag           → recupera docs    │
│  MODO: código        → lee archivos     │
│  MODO: reflexión     → consolida hechos │
└─────────────────────────────────────────┘
       ↓
   [LLM]  ← genera la respuesta con el contexto del modo
```

Esto es esencialmente lo que hacen MemGPT y Cursor AI.
Tu router híbrido actual es la semilla de esta arquitectura.

---

## Etapas orientativas

### ✅ Etapa 1 — Base funcional (completada)
**Nivel:** Fundamental

- RAG con Chroma + LangChain
- Router híbrido (keyword + embedding)
- Memoria en 4 capas (conversación, perfil, episodios, reglas)
- Fidelity check contra alucinaciones
- Caché semántica
- Memory manager unificado
- Workstate: retoma el contexto al arrancar

---

### 🎯 Etapa 2 — Modo código (próxima)
**Nivel:** Intermedio

El agente puede leer archivos de su propio proyecto y razonar sobre ellos.

**Qué implica:**
- Una `Tool` en LangChain que hace `open(archivo).read()`
- El router detecta preguntas sobre código (`"¿qué hace app/router.py?"`, `"revisa este archivo"`)
- El LLM recibe el contenido del archivo como contexto adicional
- Las respuestas incluyen observaciones sobre el código, no solo sobre documentos

**Prerequisito recomendado:** modelo con buen razonamiento de código
(`qwen2.5-coder:7b` o `llama3.1:8b`)

---

### 🔭 Etapa 3 — Auto-mejora con diffs
**Nivel:** Avanzado

El agente propone cambios concretos al código en formato diff.
Tú revisas y apruebas. Se aplican con `git apply`.

**Qué implica:**
- El modo código evoluciona: ahora no solo lee sino que propone
- El agente genera bloques `diff` o `patch` válidos
- Flujo: propuesta → revisión humana → `git apply` → commit
- Nunca auto-aplica sin aprobación explícita

**Por qué el humano siempre revisa:**
El agente puede equivocarse. La revisión humana es la red de seguridad.

---

### 🌌 Etapa 4 — Memoria reflexiva
**Nivel:** Avanzado

El agente consolida aprendizajes propios sobre sí mismo.

**Ejemplos de lo que podría registrar:**
- `"Cuando pregunto sobre X, el retriever trae chunks de Y que no son relevantes"`
- `"El fidelity check bloquea respuestas correctas sobre temas cortos"`
- `"El usuario prefiere respuestas con ejemplos de código"`

Esto es lo que MemGPT llama *self-editing memory*.
Requiere la Etapa 3 como base — el agente necesita poder leer y modificar
sus propios archivos de memoria.

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

---

*Última actualización: 11/05/2026*
*Este archivo vive en el repo y se actualiza cuando la visión evoluciona.*
