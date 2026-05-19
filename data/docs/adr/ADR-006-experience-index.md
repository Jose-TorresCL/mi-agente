# ADR-006 — Experience Index y feedback loop de calidad episódica

**Fecha:** 19/05/2026 (Fases 8A–8C)  
**Estado:** ✅ IMPLEMENTADO  
**Autor:** Jose Torres + Lautaro  
**ADRs relacionados:** ADR-002 (capas de memoria), ADR-004 (calidad RAG), ADR-005 (carriles)

---

## Contexto

Tras implementar la memoria episódica (ADR-002), los episodios se guardaban
en `episodic_memory.json` como texto plano. Esto funcionaba para mostrar el
último episodio, pero tenía dos límites importantes:

1. **Búsqueda solo por posición**: solo se podía recuperar el episodio más
   reciente. No había forma de encontrar episodios relevantes por *tema*.

2. **Sin distinción de calidad**: un episodio donde el agente falló se
   recuperaba con el mismo peso que uno donde solucionó el problema.

El proyecto tenía ya Chroma funcionando para RAG. Reutilizar la misma
infraestructura para indexar episodios era natural y sin costo adicional.

---

## Decisión 1 — Índice Chroma separado para episodios (Fase 8A)

**Por qué un índice separado** (no mezclado con el RAG de documentos):
- Los documentos del proyecto son estáticos; los episodios son dinámicos.
- Mezclarlos contaminaría el RAG con texto conversacional informal.
- Un índice separado permite limpiar, reconstruir o migrar episodios sin
  tocar el índice documental.

```
storage/
  chroma/              ← documentos del proyecto (estático)
  intent_index/        ← ejemplos de intención para el router
  experience_index/    ← episodios de sesión (dinámico) [8A]
```

**Flujo de indexación**:
```
Fin de sesión
    ↓
save_episode() → episodic_memory.json
    ↓
pregunta s/n (¿fue exitosa esta sesión?)
    ↓
indexacion.py (o indexacion.py --only-episodes)
    ↓
experience_index en Chroma con metadato exitoso=True/False
```

---

## Decisión 2 — experience_lookup en carril RAG (Fase 8B)

Cuando el carril elegido es `rag`, `intelligence.py` llama a
`experience_lookup(query, score_threshold=0.80)` antes de construir el prompt.

Si encuentra un episodio relevante con score ≥ 0.80, lo inyecta como
`context_prefix` al inicio del contexto RAG:

```python
# intelligence.py — _decide_rag()
experience = experience_lookup(user_input, score_threshold=0.80)
if experience:
    context_text = f"[Experiencia previa relevante]\n{experience}\n\n" + context_text
```

**Consecuencia**: respuestas RAG pueden incluir aprendizajes de sesiones
pasadas sin necesidad de fine-tuning.

---

## Decisión 3 — Señal de calidad y boost +0.15 (Fase 8C)

**Problema**: no todos los episodios son igualmente útiles. Un episodio
donde el agente cometió errores no debería recuperarse igual que uno exitoso.

**Solución**: al cerrar cada sesión, el sistema pregunta:
```
¿Esta sesión fue exitosa? [s/n]
```
La respuesta se guarda como metadato `exitoso: bool` en el episodio.

En `search_episodes()`, los episodios con `exitoso=True` reciben boost:
```python
final_score = base_score + 0.15 if episode["exitoso"] else base_score
```

Episodios con `exitoso=False` se filtran si hay alternativos con score ≥ 0.65.

---

## Alternativas descartadas

| Alternativa | Razón del descarte |
|---|---|
| Fine-tuning sobre episodios | Inviable en hardware local sin GPU dedicada |
| Historial completo como contexto | Excede ventana del LLM rápidamente |
| SQLite desde ya | Overhead prematuro — JSON+Chroma es suficiente hasta ~500 episodios |
| Índice mezclado con RAG documental | Contamina búsquedas documentales con texto conversacional |

---

## Consecuencias

- El agente puede responder “¿en qué quedamos la sesión del martes?” con
  búsqueda semántica real, no solo el último episodio.
- La señal de calidad crea un **feedback loop**: sesiones exitosas tienen
  más peso en recuperaciones futuras.
- La inyección de experiencias previas desactiva el caché para esa respuesta
  específica (evita respuestas obsoletas).
- Cuando episodios superen ~500, migrar a SQLite con embeddings en Chroma.

## Archivos clave

- `app/episode_store.py` — save_episode(), search_episodes(), experience_lookup()
- `storage/experience_index/` — índice Chroma de episodios
- `storage/episodic_memory.json` — episodios en JSON (fuente de verdad)
- `indexacion.py` — indexa episodios post-sesión
