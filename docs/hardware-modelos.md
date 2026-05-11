# Modelos recomendados para este hardware

**Equipo:** ThinkPad · Intel Core i7 8th gen · 16 GB DDR4 · CPU-only (sin GPU dedicada)

> Regla de oro: el modelo entero debe caber en RAM libre.
> Con ~10-11 GB disponibles (descontando SO + apps), ese es el techo real.

---

## Tabla de modelos

| Modelo | RAM necesaria | Velocidad (CPU) | Para qué sirve | Estado |
|--------|--------------|-----------------|----------------|--------|
| `llama3.2` (3B) | ~2 GB | 15-22 tok/s | General, liviano | ✅ Instalado |
| `llama3.1:8b Q4` | ~5 GB | 10-15 tok/s | Mejor razonamiento, base sólida | 🔽 Recomendado |
| `qwen2.5:7b-instruct-q4_K_M` | ~4.5 GB | 12-18 tok/s | Mejor opción general 2026, mejor español | 🔽 Recomendado |
| `qwen2.5-coder:7b` | ~4.5 GB | 12-18 tok/s | Especializado en código — Etapa 2 | 🔭 Futuro |
| `deepseek-r1:8b` | ~5 GB | 8-12 tok/s | Razonamiento paso a paso, diffs — Etapa 3 | 🔭 Futuro |
| `phi4-mini` (3.8B) | ~2.5 GB | 15-20 tok/s | Alternativa liviana si se necesita velocidad | 🔽 Opcional |
| `nomic-embed-text` | ~0.3 GB | rápido | Embeddings RAG — no cambiar | ✅ Instalado |
| ❌ cualquier 13B+ | >9 GB | <5 tok/s | Fuera de rango para este equipo | 🚫 No viables |

---

## Modelo de embeddings — no tocar

`nomic-embed-text` es perfecto para este hardware:
liviano, rápido y produce embeddings de alta calidad para RAG en español.
Cambiar de modelo LLM no requiere cambiar el modelo de embeddings.

---

## Cómo probar un modelo nuevo sin riesgo

```bash
# 1. Bajar sin borrar el actual
ollama pull qwen2.5:7b-instruct-q4_K_M

# 2. Probar directamente en terminal
ollama run qwen2.5:7b-instruct-q4_K_M "¿qué es MMR en RAG?"

# 3. Si la respuesta es buena, cambiar en config
# Buscar en chat.py o config.py el string del modelo LLM y reemplazar

# 4. Volver al anterior si algo falla (gratis, todos quedan instalados)
ollama run llama3.2
```

---

## Consideraciones para el router dual (pendiente de evaluar)

Idea: usar un modelo liviano (ej. phi4-mini) solo para clasificar el modo,
y reservar el modelo principal para generar la respuesta.

**Por qué no se implementa todavía:**
- Con 16 GB RAM, tener dos modelos cargados simultáneamente es ajustado
- Ollama descarga un modelo al cargar otro → el swap cancela la ganancia de velocidad
- phi3:mini falla ~53% en outputs JSON estructurados (necesario para el router)
- El router actual en Python puro clasifica en <100 ms sin tocar ningún LLM

**Cuándo reevaluar:** cuando el hardware cambie (más RAM o GPU dedicada),
o cuando exista un modelo tiny (<1B) que sea confiable en clasificación JSON.

---

## Cuello de botella real

El tiempo de respuesta (2-5 min) viene del LLM generando tokens en CPU.
Las optimizaciones de mayor impacto, en orden:

1. **Streaming** — misma latencia total, pero el usuario ve tokens aparecer en ~3 seg
2. **Modelo con mejor throughput** — qwen2.5:7b genera ~12-18 tok/s vs ~15-22 de llama3.2, similar pero con más calidad
3. **Caché semántica** — preguntas repetidas o similares se resuelven en <1 seg (ya implementada)
4. **Fidelity check optimizado** — reducido de 6 a 2 embeds por consulta (ya implementado en commit perf)

---

*Última actualización: 11/05/2026*
