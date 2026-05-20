# ADR-002: Separación R1 — acceso a memoria vía memory_manager

**Estado:** Aceptado  
**Fecha:** 2026-05-20  
**Archivos principales:** `app/memory_manager.py`, `app/memory_store.py`

---

## Contexto

El proyecto tiene varios módulos que necesitan leer y escribir datos de memoria del usuario (perfil, estado de trabajo, tareas, hechos del proyecto, episodios). En versiones anteriores, algunos módulos importaban `memory_store` directamente para leer/escribir JSON.

Esto creaba un problema: cualquier módulo podía modificar los archivos de memoria sin pasar por validaciones, lo que generaba bugs difíciles de rastrear (schemas incorrectos, campos faltantes, corrupción silenciosa).

Además, `router.py` importaba Chroma directamente para el intent_index, mezclando responsabilidades.

---

## Decisión

Establecer una **regla de acceso única (R1)**:

> `memory_store` solo puede ser accedido por `memory_manager`. Ningún otro módulo importa `memory_store` directamente.

El flujo correcto es:
```
cualquier módulo
    → memory_manager  (API pública: get_profile, save_fact, etc.)
        → memory_store  (lectura/escritura JSON)
            → storage/*.json
```

Separación adicional aplicada al mismo tiempo:
- `router.py` no importa Chroma. El singleton de Chroma para el intent_index vive exclusivamente en `app/intent_index.py`.
- `router.py` solo llama `intent_index.get_intent_db()` — función pura sin dependencia directa de Chroma.

---

## Consecuencias

**Positivas:**
- Un solo lugar para validar y transformar datos de memoria antes de escribirlos.
- Si cambia el schema de un archivo JSON, solo se modifica `memory_manager`, no todos los módulos.
- `router.py` es testeable sin inicializar Chroma (los tests de carril no necesitan base vectorial).
- Errores de schema se detectan en un punto centralizado.

**Negativas:**
- Añade una capa de indirección. Leer el código requiere seguir: módulo → memory_manager → memory_store.
- `memory_manager` puede crecer si se agregan muchos tipos de memoria nuevos.

---

## Alternativas descartadas

| Alternativa | Por qué se descartó |
|---|---|
| Acceso directo a memory_store desde cualquier módulo | Genera bugs de schema difíciles de rastrear. Ya ocurrió (Fix workstate.json). |
| Base de datos SQL en vez de JSON | Overhead innecesario para el volumen actual. JSON es suficiente y más simple. |
| Un solo archivo de memoria | Mezcla datos heterogéneos, dificulta backups selectivos y debugging. |

---

## Notas de implementación

- Los archivos JSON viven en `storage/`: `profile.json`, `workstate.json`, `tasks.json`, `project_facts.json`, `episodes.json`.
- Si un archivo no existe al arrancar, `memory_manager` lo crea con schema vacío válido.
- El fix R1-E de la sesión 2026-05-19 corrigió el import directo de Chroma en `router.py`.
