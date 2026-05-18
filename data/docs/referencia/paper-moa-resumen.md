# Mixture of Agents (MoA) — Resumen adaptado a mi-agente

> Paper de referencia: "Mixture-of-Agents Enhances Large Language Model Capabilities" (ICLR 2025 Spotlight)
> Nivel: Intermedio — la versión aplicable a hardware limitado es el loop de auto-refinamiento.

---

## Qué propone el paper original

MoA propone usar **múltiples modelos en capas**:

```
Capa 1 (Proponentes): [Modelo A] [Modelo B] [Modelo C]  ← generan respuestas independientes
                           ↓           ↓          ↓
Capa 2 (Agregador):          [Modelo D]                 ← sintetiza la mejor respuesta
```

El insight central es la **"collaborativeness"**: un LLM mejora su respuesta cuando ve la respuesta de otro modelo primero, aunque ese otro sea más pequeño. No porque el modelo pequeño sea bueno, sino porque actúa como borrador que activa el razonamiento del modelo grande.

Con modelos open-source en paralelo, el paper logró superar a GPT-4 Omni en benchmarks estándar.

---

## Por qué el MoA clásico NO aplica a mi hardware

El paper fue diseñado para GPUs independientes o APIs concurrentes. En mi entorno (CPU compartida, RAM limitada):

| Problema | Causa real | Efecto observado |
|---|---|---|
| Cargar phi3:mini + llama3.2 simultáneamente | Cada modelo ocupa RAM por separado | Ambos modelos compiten por memoria, ninguno rinde bien |
| Ejecución secuencial obligatoria | Ollama en CPU no paraleliza modelos | Tiempo total = tiempo_phi + tiempo_llama (siempre más lento) |
| Calidad del borrador phi3:mini | 3.8B parámetros con recursos reducidos | El borrador malo confunde más al LLM grande que ayuda |

Esto fue validado empíricamente en las pruebas del proyecto: agregar phi3:mini no mejoró tiempos ni calidad.

---

## La versión aplicable: loop de auto-refinamiento

El principio de fondo de MoA — **ver un borrador mejora la respuesta final** — se puede aplicar con un solo modelo usando dos llamadas con instrucciones distintas:

```python
# Paso 1: llama3.2 genera respuesta con prompt normal (ya existe)
respuesta_draft = llm.invoke(prompt_normal)

# Paso 2: fidelity_check verifica contra los documentos (ya existe)
is_faithful = fidelity_check(respuesta_draft, source_docs)

# NUEVO (MoA adaptado): si falló, regenerar con prompt más estricto
if not is_faithful:
    respuesta_final = llm.invoke(prompt_estricto_con_draft_como_contexto)
else:
    respuesta_final = respuesta_draft
```

El mismo llama3.2 actúa primero como **proponente** y luego como **refinador**. Sin costo de memoria adicional, sin modelo extra.

---

## Conexión con la arquitectura actual

Este patrón es la evolución directa de `fidelity_check` en `intelligence.py`:

```
Sistema actual (lineal):
  router → LLM → fidelity_check → si falla: bloquea respuesta

Sistema con MoA adaptado (cíclico):
  router → LLM draft → fidelity_check → si falla: LLM refina → respuesta final
```

La diferencia clave: en vez de devolver "no tengo evidencia suficiente", el sistema intenta **regenerar con instrucción más estricta** antes de rendirse. Esto es exactamente lo que propone Self-RAG (Tarea 9 del roadmap).

---

## Prompt estricto de refinamiento

Cuando fidelity falla, el segundo prompt incluye:

1. La respuesta draft anterior (para que el modelo la vea como contexto).
2. Una instrucción explícita: *"La respuesta anterior no estaba suficientemente respaldada por los documentos. Genera una nueva respuesta usando SOLO información que aparezca literalmente en el contexto. Si no tienes evidencia suficiente, dilo directamente."*
3. Los mismos documentos fuente recuperados.

---

## Lo que NO aplica aún

- **Múltiples modelos en paralelo**: requiere GPU dedicada con ≥16GB VRAM o acceso a APIs externas.
- **Capa de agregador separada**: solo tiene sentido cuando hay 3+ proponentes reales generando respuestas distintas.
- **Fine-tuning del agregador**: investigación activa, no implementable con Ollama local aún.

---

## Cuándo volver a este paper

- Cuando Self-RAG (Tarea 9) esté implementado: MoA y Self-RAG son complementarios.
- Cuando el hardware mejore (GPU dedicada o NPU integrado).
- Cuando consideres integrar APIs externas como fallback del LLM local.

---

## Resumen ejecutivo para Lautaro

> MoA en su versión original requiere múltiples modelos en paralelo, lo que no es viable con mi hardware. La versión aplicable es el loop de auto-refinamiento: fidelity_check detecta respuestas sin evidencia, y en vez de bloquear, el mismo llama3.2 regenera con instrucción más estricta. Este patrón es la base teórica de Self-RAG (Tarea 9).
