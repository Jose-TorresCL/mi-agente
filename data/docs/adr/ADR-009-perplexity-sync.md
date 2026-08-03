# ADR-009 — Sincronización de documentación (feat/perplexity-sync)

**Estado:** Aceptado  
**Fecha:** 2026-06-11  
**Rama:** feat/perplexity-sync  
**Autor:** Jose-TorresCL

---

## Contexto

Tras la auditoría de documentación realizada sobre la rama `feat/perplexity-sync`,
se identificó que múltiples módulos del proyecto carecían de docstrings de módulo,
cabeceras de uso, comentarios de diseño y ADRs que reflejaran las decisiones tomadas
durante el desarrollo de la Fase 2. El código funcionaba correctamente pero era
difícil de leer, mantener o extender sin contexto adicional.

La rama `feat/perplexity-sync` incorpora mejoras de memoria, fidelity check y
routing que no estaban documentadas en los ADRs existentes (ADR-001 a ADR-008).

---

## Decisión

Aplicar documentación en dos fases, priorizando módulos críticos antes que soporte:

**Fase 1 (crítica — en rama):**  
`intelligence.py`, `router.py`, `memory_manager.py`, `fidelity_check.py`

**Fase 2 (soporte — este ADR):**  
`reemplazar_langchain_docs.py`, `telegram_interface.py`, `app/prompts.py`,
`app/memory_context.py`; creación de ADR-009.

Criterios adoptados para cada archivo:
- Docstring de módulo con: responsabilidad, fuentes/destinos, prerequisitos y uso.
- Docstrings de funciones con: Args, Returns y decisiones de diseño no obvias.
- Comentarios inline solo donde la lógica no es autoexplicativa.
- Sin duplicar información que ya esté en el código (DRY para documentación).

---

## Alternativas descartadas

### A. Documentar solo con comentarios `#` inline
Descartado: los comentarios inline no son descubribles desde el exterior del módulo
(no aparecen en `help()`, IDEs ni generadores de docs). Los docstrings son la
forma estándar en Python para documentación navegable.

### B. Generar documentación automática con herramientas (Sphinx, pdoc)
Descartado para esta fase: el proyecto es local y pequeño. La documentación
automática agrega complejidad de setup sin beneficio inmediato. Se revisa en
Fase 3 si el equipo crece.

### C. Documentar todos los archivos en un solo commit masivo
Descartado: un commit masivo mezcla cambios de código con documentación y dificulta
el `git bisect`. Se prefirió un commit por fase para mantener historial limpio.

---

## Consecuencias

### Positivas
- Cualquier desarrollador puede entender el rol de cada módulo leyendo su docstring.
- `reemplazar_langchain_docs.py` ahora documenta explícitamente que requiere red y
  que es destructivo (sobreescribe archivos), evitando ejecuciones accidentales.
- `telegram_interface.py` documenta `TELEGRAM_TOKEN` como variable de entorno
  requerida y el modelo de aislamiento de sesiones por user_id.
- `app/prompts.py` documenta el *por qué* de cada regla en los prompts, haciendo
  que futuros cambios sean conscientes del trade-off (groundedness vs. recall,
  brevedad vs. completitud).
- `app/memory_context.py` documenta explícitamente las 5 fuentes que combina
  `build_memory_context()` y la decisión de contexto selectivo por carril.

### Negativas / Riesgos
- Los docstrings añaden ~200 líneas al repositorio sin cambiar comportamiento.
  Riesgo menor: si el código cambia sin actualizar los docstrings, la documentación
  queda desincronizada. Mitigación: regla de PR — ningún módulo modificado llega
  a main sin docstring actualizado en sus funciones cambiadas.

---

## Decisiones específicas de feat/perplexity-sync documentadas en otros ADRs

| Decisión | ADR de referencia |
|---|---|
| Router híbrido (keywords + embeddings) | ADR-001 |
| Memoria en capas (profile, facts, work_state, tasks, episodios) | ADR-002 |
| Fidelity check con modos numeric/semantic | ADR-003 |
| Caché semántica con TTL | ADR-004 |
| Arquitectura de intelligence.py (carriles) | ADR-005 |
| Experience index con decay temporal | ADR-006 |
| Modelo único vs. multi-modelo | ADR-007 |
| Candidato de reemplazo de modelo | ADR-008 |

---

## Notas de implementación

- La herramienta `interrogate` puede verificar cobertura de docstrings:
  ```bash
  pip install interrogate
  interrogate app/ --fail-under 70 --verbose
  ```
- Umbral inicial: 70%. Meta a 4 semanas: 85%.
- Los archivos en `storage/` y `data/` no requieren docstrings (no son módulos Python).
