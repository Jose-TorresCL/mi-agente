# Fase 6 — Tareas detalladas

> Última actualización: 19/05/2026  
> Ejecutar en orden: 6A → 6B → 6C → 6D  
> No abrir Fase 7 sin completar al menos 6A y 6B.

---

## Resumen ejecutivo para el agente

Fase 6 cierra los últimos bordes arquitecturales del sistema:
el caché semántico no debe interceptar la memoria, la recuperación
de contexto debe ser selectiva por tipo de pregunta, el fidelity_check
debe rechazar casos borde conocidos, y los tests deben proteger
que las capas no se mezclen entre sí.

---

## 6A — Fix estructural del caché semántico

**Qué es**: el caché semántico hoy puede interceptar preguntas del
carril `memory` antes de que lleguen a `work_state.json` o a
`memory_manager`. Eso significa que una pregunta como "¿en qué fase
estamos?" puede devolver una respuesta cacheada de hace días.

**Por qué pasa**: el caché se consulta en un punto del flujo que
es anterior a la separación de carriles, o bien el carril `memory`
también pasa por la lógica de caché.

**Dónde buscar el problema**:
```powershell
Select-String -Path app/*.py -Pattern "cache_lookup"
Select-String -Path app/*.py -Pattern "semantic_cache"
```

**Fix esperado**: la consulta al caché semántico solo debe ocurrir
dentro del carril `rag` en `intelligence.py` o `rag_engine.py`.
El carril `memory` no debe llamar a `cache_lookup` en ningún punto.

**Criterio de done**:
- Test: pregunta de tipo `memory` (ej. "¿cuál es el foco actual?")
  devuelve el valor real de `work_state.json`, nunca una entrada cacheada.
- El caché no crece cuando el carril elegido es `memory`.

**Test mínimo**:
```python
def test_cache_no_intercepta_carril_memory():
    # Seed del caché con respuesta incorrecta
    # Hacer pregunta de memoria
    # Verificar que la respuesta viene de work_state, no del caché
    pass
```

---

## 6B — Recuperación selectiva real por tipo de memoria

**Qué es**: `memory_manager` expone hoy `get_full_context()`,
`get_working_context()`, `get_semantic_context()` y `get_episodic_context()`.
Pero el sistema no siempre elige el contexto más específico —
termina inyectando contexto completo aunque no sea necesario.

**Qué implementar**: una función `get_context_for(intent_type: str)`
que recibe el tipo de intención del router y devuelve solo la capa
de memoria relevante.

**Mapa de intenciones a tipos de memoria**:

| Intención del router | Contexto a recuperar |
|---|---|
| `work_state`, `tasks`, `focus` | `get_working_context()` |
| `project_info`, `architecture`, `rag` | `get_semantic_context()` |
| `episode`, `last_session`, `¿en qué quedamos?` | `get_episodic_context()` |
| `identity`, `greeting` | contexto mínimo (solo profile) |
| `tool_use` | `get_working_context()` + tareas abiertas |

**Cómo pensarlo simple**: hoy el agente lleva la mochila completa
siempre. Con este cambio, lleva solo lo que necesita para esa pregunta.

**Criterio de done**:
- Pregunta sobre tareas → contexto no incluye episodios anteriores.
- Pregunta sobre episodio anterior → contexto no incluye work_state completo.
- Test unitario: `get_context_for('work_state')` devuelve
  objeto que contiene tareas y foco, pero NO resumen episódico.

**Error a evitar**: no eliminar `get_full_context()` — se mantiene
como fallback para casos que el router no clasifique con certeza.

---

## 6C — fidelity_check endurecido

**Qué es**: el `fidelity_check` verifica si la respuesta del modelo
tiene soporte documental real. Hoy tiene 3 WARNs pendientes:
- No rechaza cuando `docs=[]` (lista vacía de documentos recuperados)
- No detecta respuestas demasiado cortas (menos de ~15 palabras)
- Umbral de palabras cortas no implementado

**Reglas a añadir**:

```python
# Regla 1: sin documentos → bloqueo directo
if not docs or len(docs) == 0:
    return FidelityResult(
        passed=False,
        reason="no_docs",
        message="No hay evidencia documental suficiente para responder."
    )

# Regla 2: respuesta demasiado corta → sospechosa
if len(answer.split()) < 15:
    return FidelityResult(
        passed=False,
        reason="short_answer",
        message="Respuesta muy corta. Considera reformular la pregunta."
    )
```

**Criterio de done**:
- Los 3 WARNs pendientes desaparecen de los logs.
- Test: `fidelity_check(docs=[], answer="cualquier cosa")` devuelve `passed=False`.
- Test: `fidelity_check(docs=[doc], answer="ok")` devuelve `passed=False`
  (respuesta de una sola palabra).

**Cómo afecta al usuario**: en vez de recibir una respuesta inventada,
el agente dice explícitamente que no tiene evidencia. Eso es mejor.

---

## 6D — Tests de arquitectura

**Qué es**: tests que verifican que ciertas capas NO dependen de otras.
Son tests de imports, no de lógica — pero protegen que el refactor
no se deshaga con el tiempo.

**Por qué importa**: si en 3 meses alguien (o tú mismo) añade un
import incorrecto entre capas, este test falla inmediatamente en vez
de descubrirlo 2 semanas después cuando algo raro pasa.

**Tests mínimos a implementar** en `tests/test_architecture.py`:

```python
import ast, pathlib

def get_imports(filepath):
    tree = ast.parse(pathlib.Path(filepath).read_text(encoding='utf-8'))
    return [node.names[0].name for node in ast.walk(tree)
            if isinstance(node, ast.Import)]

def test_chat_ui_no_importa_memory_store():
    imports = get_imports('app/chat_ui.py')
    assert 'app.memory_store' not in imports
    assert 'memory_store' not in imports

def test_router_no_importa_rag_engine():
    imports = get_imports('app/router.py')
    assert 'app.rag_engine' not in imports
    assert 'rag_engine' not in imports

def test_memory_manager_no_importa_chat_ui():
    imports = get_imports('app/memory_manager.py')
    assert 'app.chat_ui' not in imports
    assert 'chat_ui' not in imports
```

**Criterio de done**:
- `pytest tests/test_architecture.py` pasa en verde.
- Si en el futuro alguien añade un import prohibido, el test falla.

**Nivel de dificultad**: bajo — son tests de texto, no de lógica.
Pueden escribirse en 30 minutos.

---

## Orden de ejecución recomendado

```
6A  →  valida con test manual + test automático
6B  →  valida con test unitario de context routing
6C  →  valida que los 3 WARNs desaparecen del log
6D  →  valida con pytest tests/test_architecture.py
```

Cuando los 4 estén en verde: actualizar `estado_proyecto.md`
con Fase 6 como ✅ Completa y abrir Fase 7.

---

## Señal de que Fase 6 está completa

Pregúntale al agente estas 3 cosas y verifica:

1. `"¿En qué fase estamos?"` → responde con Fase 6 real, no desde caché.
2. `"¿Qué tareas hay abiertas?"` → contexto solo de working memory, sin episodios.
3. `"¿Qué es fidelity_check?"` → RAG con evidencia documental, sin WARNs en log.
