## Archivos principales del sistema

| Archivo | Rol |
|---------|-----|

| `indexacion.py` | Entrada para cargar documentos y construir Chroma |
| `chat.py` | Punto de entrada principal (delegación a `app/`) |
| `storage/chroma/` | Base vectorial RAG |
| `storage/memory.json` | Memoria conversacional reciente |
| `storage/profile.json` | Perfil y preferencias de usuario |
| `storage/project_facts.json` | Hechos estables del proyecto |
| `storage/tasks.json` | Tareas y pendientes |
| `storage/work_state.json` | Estado actual de trabajo |

## Base documental actual

Documentos fuente en Markdown que el agente consulta como conocimiento del proyecto:

- `estado_proyecto.md` (fases, objetivos, estado actual)
- `arquitectura_actual.md` (componentes técnicos, flujo)
- `memoria_agentes_resumen.md` (conceptos de memoria aplicada)

## Flujo actual del sistema

Usuario → chat.py → chat_ui.py → chat_core.py
↓
Router simple → RAG (Chroma) | Memoria (JSON) | Tool
↓
Ollama (llama3.2) → Respuesta

text

## Diferencia entre arquitectura y base documental

| Arquitectura | Base documental |
|--------------|-----------------|

| Componentes, scripts, módulos, flujo técnico | Textos que el agente consulta como conocimiento del proyecto |
| `app/memory_store.py`, `storage/tasks.json` | `estado_proyecto.md`, objetivos de fase 2 |
| Cómo funciona internamente | Qué sabe el agente sobre sí mismo |

## Estado de fase 2

**Implementado**:

- Modularización inicial (`chat`, `indexacion`).
- Memoria estructurada base (5 JSON + `memory_store.py`).
- Paquete `app/` funcional.

**Próximo**:

- Conectar memoria al chat.
- 4 tools básicas.
- Router simple.

## Objetivo de esta etapa (Fase 2)

Construir agente útil con memoria estructurada, tools básicas y routing simple, manteniendo arquitectura pequeña y extensible.

**No agregar todavía**:

- Multiagente complejo.
- Tools de alto riesgo (ejecución shell arbitraria).
- Planner sofisticado.
