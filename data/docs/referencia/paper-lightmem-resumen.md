# Paper Curado — LightMem: Efficient Memory Management for LLM Agents

**Contexto**: LightMem es una línea de investigación enfocada en hacer la gestión de memoria para agentes LLM más eficiente y ligera que MemGPT, orientada a recursos limitados.
**Nivel**: Intermedio
**Relevancia para mi-agente**: ALTA — diseñado específicamente para entornos con recursos limitados (como tu laptop con 16 GB RAM corriendo Ollama local).

---

## ¿Por qué LightMem después de MemGPT?

MemGPT es poderoso pero complejo: requiere múltiples llamadas al LLM para gestionar la memoria, lo que lo hace lento y pesado para hardware modesto. LightMem propone un enfoque alternativo: **hacer lo mismo con menos overhead**.

**Principio central**: En lugar de que el LLM gestione su propia memoria (como hace MemGPT), LightMem usa un sistema externo liviano que decide qué recordar, cuándo comprimir y qué recuperar — sin consumir tokens del LLM para esas decisiones.

---

## Diferencia fundamental con MemGPT

| Aspecto | MemGPT | LightMem |
|---|---|---|
| ¿Quién gestiona la memoria? | El propio LLM (via tools) | Sistema externo (código Python) |
| Costo de gestión | Tokens del LLM | CPU mínima (sin LLM) |
| Complejidad | Alta | Baja-media |
| Latencia | Mayor (múltiples llamadas LLM) | Menor (gestión local) |
| Hardware requerido | GPU/API recomendada | Funciona bien en CPU/laptop |

---

## Arquitectura de LightMem

### Capa 1 — Short-Term Buffer (STB)
Buffer circular de los últimos N intercambios. No usa LLM para gestión — simplemente rota los mensajes más viejos.

```python
# Equivalente en mi-agente:
ConversationBufferWindowMemory(k=8)  # ya implementado
# Los últimos 8 turnos están siempre en contexto
```

### Capa 2 — Episodic Summary Store (ESS)
Cada N turnos, un proceso ligero (puede ser el mismo LLM con un prompt simple) comprime la conversación reciente en un "episodio" y lo guarda.

```python
# Pseudo-código de lo que sería en mi-agente:
def comprimir_episodio(mensajes_recientes):
    resumen = llm.invoke(f"Resume estos {len(mensajes_recientes)} mensajes en 3 puntos clave: {mensajes_recientes}")
    guardar_episodio(fecha=hoy, resumen=resumen)
```

### Capa 3 — Semantic Long-Term Store (SLTS)
Vectorstore con embeddings. Igual que Chroma en tu proyecto — busca por similitud semántica.

### Capa 4 — Structured Facts Store (SFS)
Pares clave-valor para hechos estables. No usa embeddings — búsqueda exacta por clave.

```python
# Equivalente en mi-agente:
projectfacts.json   # hechos del proyecto
profile.json        # datos del usuario
workstate.json      # estado de trabajo
```

---

## Comparación: LightMem vs mi-agente actual

| Capa LightMem | Equivalente en mi-agente | Estado |
|---|---|---|
| Short-Term Buffer | ConversationBufferWindowMemory(k=8) | ✅ Implementado |
| Structured Facts | profile.json, projectfacts.json, workstate.json | ✅ Implementado |
| Semantic Long-Term | Chroma vectorstore con docs de referencia | ✅ Implementado |
| Episodic Summary | ❌ No implementado aún | Pendiente (fase 2D-3) |

**Conclusión**: Mi arquitectura actual ya cubre 3 de las 4 capas de LightMem. Lo que falta es la compresión episódica.

---

## Estrategia de recuperación selectiva

LightMem propone un selector que decide qué capa consultar según la pregunta:

```
Pregunta recibida
       ↓
¿Es sobre algo de esta sesión?  → Short-Term Buffer
¿Es sobre hechos fijos del proyecto? → Structured Facts
¿Es sobre documentación técnica?    → Semantic Long-Term (Chroma)
¿Es sobre qué pasó en sesiones pasadas? → Episodic Summary
```

Este selector es lo que en mi-agente ya existe parcialmente como `inferDocTypes()` — detecta por palabras clave qué tipo de documento buscar en Chroma.

### Implementación sugerida del selector

```python
def seleccionar_fuente_memoria(pregunta: str) -> list[str]:
    q = pregunta.lower()
    fuentes = []
    
    # Hechos estructurados (exacto, sin LLM)
    if any(w in q for w in ["fase", "foco", "siguiente paso", "estado", "tarea"]):
        fuentes.append("structured_facts")
    
    # Historial reciente (en contexto, sin búsqueda)
    if any(w in q for w in ["antes dijiste", "hace un momento", "en esta sesión"]):
        fuentes.append("short_term")
    
    # Documentación técnica (Chroma)
    if any(w in q for w in ["cómo", "qué es", "documentación", "ejemplo", "implementar"]):
        fuentes.append("semantic_longterm")
    
    # Episodios pasados (si están implementados)
    if any(w in q for w in ["ayer", "semana pasada", "antes", "sesión anterior"]):
        fuentes.append("episodic")
    
    return fuentes if fuentes else ["semantic_longterm"]  # default a RAG
```

---

## Compresión episódica: cómo implementarla

Esta es la pieza que falta en mi-agente. LightMem propone hacerla **al final de cada sesión** o cada N turnos:

```python
# En chat.py, al recibir comando !guardar o al salir:
def comprimir_y_guardar_sesion(mensajes: list, max_tokens_resumen: int = 200):
    """
    Comprime los mensajes de la sesión actual en un episodio.
    Se llama al terminar la conversación o cada N turnos.
    """
    if len(mensajes) < 3:  # sesión muy corta, no vale la pena
        return
    
    texto = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in mensajes)
    
    prompt = f"""Resume esta conversación en máximo 5 puntos clave.
    Solo incluye: decisiones tomadas, problemas resueltos, hechos nuevos aprendidos.
    No incluyas preguntas y respuestas simples.
    
    Conversación:
    {texto}"""
    
    resumen = llm.invoke(prompt)
    
    # Guardar como episodio
    episodio = {
        "fecha": datetime.now().isoformat(),
        "resumen": resumen,
        "num_mensajes": len(mensajes)
    }
    
    episodios = cargar_episodios()  # lista de episodios pasados
    episodios.append(episodio)
    guardar_episodios(episodios)
```

---

## Cuándo implementar cada capa en mi-agente

| Prioridad | Capa | Cuándo | Dificultad |
|---|---|---|---|
| ✅ Hecho | STB + Facts + Chroma | Fase 2 | Baja |
| 🔲 Próximo | Selector de fuente mejorado | Fase 2D | Baja |
| 🔲 Siguiente | Compresión episódica | Fase 3 | Media |
| 🔲 Futuro | Episodios buscables en Chroma | Fase 3+ | Media |

---

## Ventajas de LightMem para hardware limitado

1. **Sin llamadas LLM extra**: la gestión de memoria no consume tokens adicionales.
2. **Latencia baja**: decisiones de qué recordar se hacen en Python puro.
3. **Predecible**: el sistema no depende de que el LLM "decida" cuándo guardar — eso lo hace código determinista.
4. **Escalable sin GPU**: funciona bien con `llama3.2` en CPU o GPU pequeña.

---

## Error común

**Confusión**: Pensar que LightMem es un framework que se instala (`pip install lightmem`).

**Realidad**: LightMem es una **arquitectura de referencia**, no una librería publicada. Sus principios se implementan manualmente — exactamente como lo estás haciendo con `memorystore.py` y Chroma. Ya estás siguiendo sus principios sin saberlo.

---

## Buenas prácticas derivadas

- Separar claramente qué fuente responde cada tipo de pregunta: no mezclar hechos estructurados con búsqueda semántica.
- La compresión episódica debe ser opt-in primero (comando `!guardar`) antes de hacerla automática.
- El selector de fuente debe ser simple y basado en reglas primero — no en otro LLM.
- Los episodios comprimidos son documentos más para Chroma: se indexan como cualquier otro `.md`.
