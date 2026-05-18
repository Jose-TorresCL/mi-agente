# ADR-005 — Modos del agente, tool de código, carril unsupported y calidad documental

**Fecha**: 17/05/2026
**Estado**: Parcialmente implementado (carril unsupported en router; tool de código y modos en diseño)
**Autores**: Jose Torres + Lautaro (asistente IA local)
**ADRs relacionados**: ADR-001 (router híbrido), ADR-003 (memory_manager), ADR-004 (RAG calidad)

---

## Contexto

Durante la sesión del 17/05/2026 surgieron cuatro decisiones de diseño interrelacionadas:

1. El agente respondía preguntas métricas ("¿cuántas líneas tiene el proyecto?") con
   inventos o errores porque el LLM no tiene acceso al sistema de archivos. No existía
   un carril que reconociera este límite y respondiera honestamente.

2. La opción de bajar a phi3:mini para reducir latencia se evaluó y descartó. El costo
   en razonamiento técnico, español y análisis de código es demasiado alto para la visión
   de largo plazo del agente. La alternativa correcta es separar roles entre modelos.

3. La visión de largo plazo es un agente que lee su propio código, entiende su arquitectura
   y propone mejoras — sin necesidad de múltiples instancias paralelas, sino mediante una
   arquitectura de modos que varía el contexto inyectado según el tipo de tarea.

4. Se realizó una auditoría de los 23 documentos indexados en Chroma. Se incorporaron
   además dos nuevos papers académicos (`paper-lightmem-resumen.md` y `paper-slm-first-resumen.md`)
   que refuerzan las decisiones de arquitectura de memoria y selección de modelos.

---

## Decisiones

### Decisión 1 — Carril `unsupported` para consultas métricas del sistema de archivos

**Problema**:
El router no interceptaba preguntas como "¿cuántos archivos hay?", "¿cuántas líneas tiene X?",
"¿cuánto pesa la carpeta?". Estas preguntas requieren ejecutar comandos del sistema operativo,
capacidad que el LLM no posee.

**Solución implementada en `router.py`**:
```python
TOOL_UNSUPPORTED_KEYWORDS = [
    "cuántos archivos", "cuantos archivos",
    "cuántas líneas", "cuantas lineas",
    "cuántas carpetas", "cuantas carpetas",
    "cuánto pesa", "cuanto pesa",
    "tamaño del proyecto", "tamaño de la carpeta",
    "líneas de código", "lineas de codigo",
]

# En _route_by_keywords(), ANTES de RAG_HINTS:
if any(k in q for k in TOOL_UNSUPPORTED_KEYWORDS):
    return "unsupported"
```

**Respuesta honesta** (función `_handle_unsupported()`):
En vez de inventar, el agente entrega los comandos exactos de PowerShell y Git Bash
para que el usuario obtenga el dato real en su terminal.

**Por qué no usar un tool de shell**:
Ejecutar comandos de sistema de archivos desde el agente introduce riesgos de seguridad
no triviales. La solución conservadora es reconocer el límite y empoderar al usuario con
el comando exacto. Se puede reconsiderar en una etapa posterior con sandboxing explícito.

**Pendiente**: conectar el carril en `intelligence.py` con un `elif lane == "unsupported"`
que llame a `_handle_unsupported()`.

---

### Decisión 2 — Separación de modelos: clasificador liviano + generador principal

**Problema**:
La latencia percibida es alta. La opción obvia sería bajar a phi3:mini, pero el costo
en calidad de razonamiento, español y análisis de código es demasiado alto para la
visión de largo plazo del agente.

**Decisión**:
Mantener llama3.2 (o llama3.1:8b como upgrade futuro) como modelo generador principal.
Usar phi3:mini **únicamente** como clasificador de carriles en las capas 1 y 2 del router.

**Arquitectura propuesta**:
```
Consulta del usuario
      ↓
  phi3:mini  ← clasifica el carril (rápido, ~3-5 seg, ~2B parámetros)
      ↓
llama3.2    ← genera la respuesta con el contexto correcto del carril
```

**Por qué no phi3:mini para todo**:
phi3:mini pierde calidad en razonamiento técnico complejo, contextos > 4k tokens, síntesis
de múltiples documentos, español natural y análisis de código propio. Exactamente las
capacidades que el agente necesitará en su siguiente etapa de desarrollo.

**Por qué llama3.1:8b como upgrade**:
Es el salto natural desde llama3.2 dentro del mismo ecosistema — mejor razonamiento,
mismo soporte de Ollama, sin cambio de arquitectura.

**Dependencia**: requiere que Ollama tenga ambos modelos disponibles localmente y que
se mida el uso de RAM antes de activar en producción.

---

### Decisión 3 — Arquitectura de modos del agente (diseño)

**Motivación**:
La visión es un agente que en el futuro pueda leer su propio código, entender su
arquitectura, proponer mejoras y conectarse con herramientas externas. Crear un agente
separado por capacidad sería inmanejable. La alternativa es un único agente con
**modos de operación** que varían el contexto inyectado y las herramientas disponibles.

**Modos definidos**:

| Modo | Carril router | Contexto inyectado | Herramientas disponibles |
|---|---|---|---|
| `conversacion` | `memoria`, `general` | perfil + workstate | ninguna |
| `rag` | `rag` | chunks Chroma + perfil mínimo | retriever |
| `estado` | `estado` | workstate + tareas | ninguna |
| `codigo` | `codigo` (nuevo) | archivo(s) leídos + arquitectura | lector de archivos |
| `reflexion` | `reflexion` (futuro) | memoria episódica + hechos | consolidador |
| `unsupported` | `unsupported` | ninguno | ninguna (respuesta fija) |

**Tool de lectura de código** (modo `codigo`):
```python
def read_project_file(relative_path: str) -> str:
    """Lee un archivo del proyecto y lo retorna como string."""
    base = Path("app/")
    target = (base / relative_path).resolve()
    if not str(target).startswith(str(base.resolve())):
        return "Error: ruta fuera del proyecto."
    return target.read_text(encoding="utf-8")
```

La herramienta incluye validación de ruta para evitar lecturas fuera del directorio `app/`.
El agente recibe el contenido en el contexto y puede razonar sobre él, identificar problemas
y proponer cambios en formato `diff`.

**Flujo del modo código**:
```
Usuario: "¿qué hace intelligence.py?"
      ↓ router detecta carril "codigo"
      ↓ tool lee app/intelligence.py
      ↓ contexto = contenido del archivo + arquitectura_actual.md
      ↓ LLM razona y responde / propone mejora
      ↓ (futuro) usuario aprueba → git apply del diff
```

---

### Decisión 4 — Auditoría documental y expansión de la base de conocimiento

**Contexto**:
Se auditaron los 23 documentos indexados en Chroma evaluando cuatro criterios:
densidad informativa, especificidad al proyecto, estabilidad en el tiempo y granularidad
para chunks. Cada criterio se puntuó de 0 a 10.

**Resultados del ranking**:

| # | Documento | Score | Categoría |
|---|---|---|---|
| 1-2 | ADR-002, ADR-004 | 8.8 | 🟢 Elite |
| 3 | arquitectura_actual.md | 8.5 | 🟢 Elite |
| 4 | paper-memgpt-resumen.md | 8.2 | 🟢 Alto |
| 5-7 | arquitectura-memoria, ADR-001, ADR-003 | 8.0 | 🟢 Alto |
| 8-13 | chroma-queries, papers, retriever | 7.0–7.8 | 🟢 Bueno |
| 14-18 | langchain docs, ollama-api | 6.2–6.8 | 🟡 Aceptable |
| 19-21 | visión, estado_proyecto, roadmap | 5.5 | 🟡 Riesgo |
| 22-23 | hardware-modelos, chroma-introduccion | 5.0 | 🔴 Problema |

**Documentos problemáticos identificados**:
- `estado_proyecto.md` y `roadmap.md`: estabilidad 2–3/10. Describen el estado actual
  y fases futuras que ya pueden haber cambiado. Si el RAG los recupera, el agente puede
  responder con información obsoleta. Acción: moverlos fuera del índice o añadir header
  `⚠️ Última actualización: YYYY-MM-DD` para que el LLM los contextualice.
- `chroma-introduccion.md` y `hardware-modelos.md`: muy pequeños y genéricos. Los chunks
  que producen son casi inútiles porque no aportan información que el LLM no tenga ya.
- `ollama-api.md` (55 KB): es el documento más grande por lejos, casi el doble de todos
  los demás juntos. Con `chunk_size=500` genera ~110 chunks, muchos sin contexto suficiente.
  Acción: usar `chunk_size=800` o superior para este archivo.

**Papers incorporados en esta sesión**:
Se agregaron dos nuevos papers que refuerzan decisiones de arquitectura ya tomadas:
- `paper-lightmem-resumen.md` (7.5 KB, score 7.8): valida la arquitectura de memoria
  liviana en capas implementada en ADR-002.
- `paper-slm-first-resumen.md` (3.7 KB, score 7.2): fundamenta la decisión de mantener
  un SLM (Small Language Model) como clasificador y un modelo más capaz como generador,
  que es exactamente la arquitectura propuesta en la Decisión 2 de este ADR.

---

## Consecuencias

### Positivas
- El carril `unsupported` elimina respuestas inventadas para preguntas métricas de forma
  inmediata, sin riesgo de regresión.
- La separación phi3:mini / llama3.2 reduce latencia de clasificación sin sacrificar
  calidad generativa — la solución correcta frente a "bajar todo a un modelo pequeño".
- La arquitectura de modos es el camino natural hacia el agente auto-reflexivo. No requiere
  refactorizaciones radicales: solo añadir carriles y herramientas progresivamente.
- La auditoría documental identifica por primera vez qué documentos dañan la calidad del
  RAG (obsoletos, genéricos o mal chunkeados) y establece una base para mantener el índice.

### A vigilar
- El modo `codigo` solo debe activarse con rutas explícitas del usuario, nunca inferidas.
  Un agente que lee archivos arbitrarios sin confirmación es un riesgo de privacidad.
- La separación de modelos puede aumentar el uso de RAM al tener dos modelos cargados
  simultáneamente. Medir antes de activar en producción.
- `estado_proyecto.md` y `roadmap.md` deben actualizarse o excluirse del índice antes de
  la próxima sesión de uso intensivo del RAG.
- Los modos `reflexion` y auto-mejora con diffs son capacidades avanzadas — implementar
  solo cuando los modos base estén probados y estables.

---

## Orden de implementación recomendado

1. Conectar carril `unsupported` en `intelligence.py` → 1 función + 1 elif, sin riesgo
2. Limpiar índice: excluir o versionar `estado_proyecto.md` y `roadmap.md`
3. Ajustar `chunk_size` de `ollama-api.md` a 800+
4. Implementar tool `read_project_file` con validación de ruta → base del modo código
5. Añadir carril `codigo` al router con keywords específicas ("muéstrame", "qué hace", "lee")
6. Integrar phi3:mini como clasificador en Capa 1/2 → medir latencia antes y después
7. Modo `reflexion` y auto-mejora con diffs → etapa avanzada, requiere 1-6 estables
