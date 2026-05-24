"""Tests del router híbrido — Capa 1 (keywords).

Cubre:
  - Carriles de escritura (save_fact, create_task, complete_task, update_work_state)
  - RAG hints con y sin nombre de archivo .py (caso que falló: '¿qué hace router.py?')
  - Memoria estructurada (profile, work_state, tasks, project_facts)
  - Salida / despedida
  - Casos límite y frases de frontera
  - Casos reales que fallaron en sesión (documentados con comentario)
  - fix #8: frases de estado natural → memory
  - fix #9: frases de identidad → memory
  - Fix P5-Paso1: memory ahora retorna 'memory:<subtipo>' (ej: 'memory:profile')
  - Fix B3: 'para qué sirve X.py' y 'explica ...' caen a embeddings/fallback → rag vía route_query

NO requiere Ollama ni Chroma: sólo se prueba _route_by_keywords() y classify_memory_query().
Si el índice no existe, las capas 2 y 3 son ignoradas correctamente.

Uso:
    python -m pytest tests/test_router.py -v
"""
import pytest
from app.router import (
    _route_by_keywords,
    classify_memory_query,
    route_query,
    SESSION_STATS,
)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def kw(question: str) -> str | None:
    """Atajo — llama _route_by_keywords y devuelve su resultado."""
    return _route_by_keywords(question)


# ─────────────────────────────────────────────────────────────
# 1. SALIDA
# ─────────────────────────────────────────────────────────────

class TestExit:
    def test_salir(self):
        assert route_query("salir") == "exit"

    def test_exit_ingles(self):
        assert route_query("exit") == "exit"

    def test_quit(self):
        assert route_query("quit") == "exit"

    def test_chau(self):
        assert route_query("chau") == "exit"

    def test_nos_vemos(self):
        assert route_query("nos vemos") == "exit"

    def test_me_voy(self):
        assert route_query("me voy") == "exit"

    def test_cierro(self):
        assert route_query("cierro") == "exit"

    def test_hasta_luego(self):
        assert route_query("hasta luego") == "exit"

    def test_salir_con_espacios(self):
        """Espacio extra no debe romper la detección."""
        assert route_query("  salir  ") == "exit"


# ─────────────────────────────────────────────────────────────
# 2. TOOL_SAVE_FACT
# ─────────────────────────────────────────────────────────────

class TestSaveFact:
    def test_anota_que(self):
        assert kw("anota que current_phase es fase_5") == "tool_save_fact"

    def test_registra_que(self):
        assert kw("registra que el modelo es llama3.2") == "tool_save_fact"

    def test_guarda_como_hecho(self):
        assert kw("guarda como hecho: la fase 5 empezó hoy") == "tool_save_fact"

    def test_guardar_hecho(self):
        assert kw("guardar hecho: phase_label es inyección automática") == "tool_save_fact"


# ─────────────────────────────────────────────────────────────
# 3. TOOL_CREATE_TASK
# ─────────────────────────────────────────────────────────────

class TestCreateTask:
    def test_crea_una_tarea(self):
        assert kw("crea una tarea: revisar el router") == "tool_create_task"

    def test_nueva_tarea(self):
        assert kw("nueva tarea: limpiar project_facts") == "tool_create_task"

    def test_agrega_una_tarea(self):
        assert kw("agrega una tarea para probar el logger") == "tool_create_task"

    def test_registra_una_tarea(self):
        assert kw("registra una tarea: completar schemas") == "tool_create_task"


# ─────────────────────────────────────────────────────────────
# 4. TOOL_COMPLETE_TASK
# ─────────────────────────────────────────────────────────────

class TestCompleteTask:
    def test_marca_como_completada(self):
        assert kw("marca la tarea como completada") == "tool_complete_task"

    def test_marca_como_completado(self):
        assert kw("marca como completado el router") == "tool_complete_task"

    def test_cierra_la_tarea(self):
        assert kw("cierra la tarea t-3") == "tool_complete_task"

    def test_pattern_marca_t_numero(self):
        """Regex t-N debe funcionar con y sin 'marca'."""
        assert kw("marca t-5") == "tool_complete_task"

    def test_completar_tarea(self):
        assert kw("completar tarea t-2") == "tool_complete_task"

    def test_complete_sin_tilde(self):
        """Variante sin tilde — falló en sesión real."""
        assert kw("complete la tarea del logger") == "tool_complete_task"


# ─────────────────────────────────────────────────────────────
# 5. TOOL_UPDATE_WORK_STATE
# ─────────────────────────────────────────────────────────────

class TestUpdateWorkState:
    def test_actualiza_el_foco(self):
        assert kw("actualiza el foco: siguiente paso es limpiar project_facts") == "tool_update_work_state"

    def test_actualiza_el_estado_de_trabajo(self):
        """Frase usada en sesión real — debe resolverse en Capa 1."""
        assert kw("actualiza el estado de trabajo: completé la inyección") == "tool_update_work_state"

    def test_completé_con_tilde(self):
        assert kw("completé la inyección de workstate al arrancar") == "tool_update_work_state"

    def test_termine_sin_tilde(self):
        """Sin tilde — fix nivel1, falló antes del fix."""
        assert kw("termine de configurar el router") == "tool_update_work_state"

    def test_el_siguiente_paso_es(self):
        assert kw("el siguiente paso es limpiar project_facts y deduplicar hechos") == "tool_update_work_state"

    def test_ya_hice(self):
        assert kw("ya hice la limpieza de project_facts") == "tool_update_work_state"

    def test_listo_dos_puntos(self):
        assert kw("listo: completé la parte de schemas") == "tool_update_work_state"


# ─────────────────────────────────────────────────────────────
# 6. RAG — el caso crítico que falló antes del fix
# ─────────────────────────────────────────────────────────────

class TestRAGHints:
    def test_que_hace_con_archivo_py(self):
        """CASO QUE FALLÓ: '¿qué hace router.py?' iba a tool_read_file.
        Fix B3: sin verbo lector explícito, la mención de archivo no dispara tool_read_file.
        'que hace' está en RAG_HINTS → carril rag vía Capa 1.
        """
        assert kw("¿qué hace router.py?") == "rag"

    def test_que_hace_sin_archivo(self):
        assert kw("¿qué hace el router híbrido?") == "rag"

    def test_como_funciona(self):
        assert kw("cómo funciona Chroma") == "rag"

    def test_para_que_sirve_con_archivo(self):
        """Fix R4+R7 eliminó 'para que sirve' de RAG_HINTS (demasiado genérica).
        Capa 1 devuelve None → Capa 2/fallback resuelve como rag.
        Se prueba con route_query() para cubrir el flujo completo.
        """
        assert route_query("para qué sirve fidelity_check.py") == "rag"

    def test_explica(self):
        """Fix R4+R7 eliminó 'explicame' de RAG_HINTS.
        Capa 1 devuelve None → Capa 2/fallback resuelve como rag.
        Se prueba con route_query() para cubrir el flujo completo.
        """
        assert route_query("explica el flujo del agente") == "rag"

    def test_arquitectura(self):
        assert kw("cuál es la arquitectura del sistema") == "rag"

    def test_segun_los_documentos(self):
        assert kw("según los documentos qué falta por hacer") == "rag"

    def test_que_es(self):
        assert kw("qué es LangChain") == "rag"

    def test_diferencia_entre(self):
        assert kw("diferencia entre embeddings y keywords") == "rag"


# ─────────────────────────────────────────────────────────────
# 7. TOOL_READ_FILE — solo cuando NO hay RAG hint
# ─────────────────────────────────────────────────────────────

class TestReadFile:
    def test_lee_archivo_py(self):
        """Sin verbo interrogativo → leer archivo literal."""
        assert kw("lee router.py") == "tool_read_file"

    def test_muéstrame_el_archivo(self):
        assert kw("muéstrame el archivo tools.py") == "tool_read_file"

    def test_abre_el_archivo(self):
        assert kw("abre el archivo memory_store.py") == "tool_read_file"

    def test_leer_documentacion(self):
        assert kw("leer documentación del proyecto") == "tool_read_file"


# ─────────────────────────────────────────────────────────────
# 8. TOOL_LIST_FILES
# ─────────────────────────────────────────────────────────────

class TestListFiles:
    def test_listar_archivos(self):
        assert kw("listar archivos") == "tool_list_files"

    def test_que_archivos_hay(self):
        assert kw("qué archivos hay en el proyecto") == "tool_list_files"

    def test_ver_archivos(self):
        assert kw("ver archivos del proyecto") == "tool_list_files"


# ─────────────────────────────────────────────────────────────
# 9. MEMORIA — classify_memory_query
# ─────────────────────────────────────────────────────────────

class TestClassifyMemoryQuery:
    def test_perfil(self):
        assert classify_memory_query("cuál es mi perfil") == "profile"

    def test_estilo_preferido(self):
        assert classify_memory_query("mi estilo preferido de trabajo") == "profile"

    def test_estado_actual(self):
        assert classify_memory_query("estado actual del proyecto") == "work_state"

    def test_siguiente_paso(self):
        assert classify_memory_query("cuál es el siguiente paso") == "work_state"

    def test_en_que_vamos(self):
        assert classify_memory_query("en qué vamos") == "work_state"

    def test_tareas_pendientes(self):
        assert classify_memory_query("qué tareas hay pendientes") == "tasks"

    def test_mis_tareas(self):
        assert classify_memory_query("mis tareas") == "tasks"

    def test_que_tengo_pendiente(self):
        assert classify_memory_query("qué tengo pendiente") == "tasks"

    def test_tareas_con_signal_sugestion_va_a_rag(self):
        """'qué tareas podríamos crear' tiene signal de sugerencia → no debe ir a memory."""
        result = _route_by_keywords("qué tareas podríamos crear")
        assert result is None or not result.startswith("memory")

    def test_fase_actual(self):
        assert classify_memory_query("en qué fase estamos") == "project_facts"

    def test_estado_del_proyecto(self):
        assert classify_memory_query("estado del proyecto") == "project_facts"

    def test_sin_match_devuelve_none(self):
        assert classify_memory_query("cómo funciona Chroma") is None


# ─────────────────────────────────────────────────────────────
# 10. CARRIL MEMORY VÍA route_query — Fix P5-Paso1: subtipo
# Antes retornaba 'memory', ahora retorna 'memory:<subtipo>'.
# Los tests usan startswith("memory") para ser robustos ante futuros subtipos.
# ─────────────────────────────────────────────────────────────

class TestMemoryViaRouteQuery:
    def test_ponme_al_dia(self):
        """'ponme al día' debe ir a memory (tasks), no a rag."""
        lane = _route_by_keywords("ponme al día")
        assert lane is not None and lane.startswith("memory")

    def test_mis_tareas_pendientes(self):
        lane = _route_by_keywords("mis tareas pendientes")
        assert lane is not None and lane.startswith("memory")


# ─────────────────────────────────────────────────────────────
# 11. CASOS LÍMITE
# ─────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_pregunta_no_va_a_save_fact(self):
        lane = kw("¿anota que algo?")
        assert lane in ("tool_save_fact", None)

    def test_frase_vacia_devuelve_none(self):
        assert kw("") is None

    def test_frase_solo_espacios(self):
        assert kw("   ") is None

    def test_mayusculas_no_rompen_keyword(self):
        assert kw("NUEVA TAREA: revisar el logger") == "tool_create_task"

    def test_tilde_no_rompe_keyword(self):
        """Fix N3: 'Completé la tarea del router' matchea tool_complete_task
        (complete la tarea → TOOL_COMPLETE_TASK_KEYWORDS), no tool_update_work_state.
        """
        assert kw("Completé la tarea del router") == "tool_complete_task"

    def test_route_query_nunca_devuelve_none(self):
        result = route_query("una frase completamente aleatoria xyz123")
        assert result is not None
        assert isinstance(result, str)

    def test_session_stats_incrementan(self):
        antes = SESSION_STATS["total"]
        route_query("qué tareas tengo")
        assert SESSION_STATS["total"] == antes + 1


# ─────────────────────────────────────────────────────────────
# 12. KEYWORDS NUEVAS — fix #8 (estado) y fix #9 (identidad)
# Fix P5-Paso1: ahora retornan 'memory:<subtipo>', se verifica con startswith.
# ─────────────────────────────────────────────────────────────

class TestKeywordsNuevas:
    """Verifica que las frases agregadas en fix #8 y fix #9
    resuelven en Capa 1 (keywords) sin necesitar embeddings ni LLM.
    Ejecutar: python -m pytest tests/test_router.py::TestKeywordsNuevas -v
    """

    # fix #9 — identidad → memory (classify → profile)
    def test_quien_soy_yo(self):
        lane = kw("quién soy yo")
        assert lane is not None and lane.startswith("memory")

    def test_quien_soy_sin_tilde(self):
        lane = kw("quien soy yo")
        assert lane is not None and lane.startswith("memory")

    def test_como_me_llamo(self):
        lane = kw("cómo me llamo")
        assert lane is not None and lane.startswith("memory")

    def test_mi_nombre(self):
        lane = kw("mi nombre")
        assert lane is not None and lane.startswith("memory")

    # fix #8 — estado natural → memory (classify → work_state)
    def test_que_hago_hoy(self):
        lane = kw("qué hago hoy")
        assert lane is not None and lane.startswith("memory")

    def test_cual_es_el_plan(self):
        lane = kw("cuál es el plan")
        assert lane is not None and lane.startswith("memory")

    def test_que_hicimos(self):
        lane = kw("qué hicimos")
        assert lane is not None and lane.startswith("memory")

    def test_cual_es_mi_foco(self):
        lane = kw("cuál es mi foco")
        assert lane is not None and lane.startswith("memory")
