from app.router import debug_route_layers

def test_episodios_recientes_resuelven_por_keywords():
    frases = [
        "dame un resumen ultimas sesiones",
        "¿qué hicimos en las últimas 3 sesiones?",
        "muéstrame las sesiones recientes",
        "resumen de las sesiones pasadas",
        "¿de qué hablamos las últimas veces?",
    ]
    for frase in frases:
        info = debug_route_layers(frase)
        assert info == {"layer": "kw", "lane": "memory:episode"}, frase
        
def test_historial_por_contenido_va_a_episode():
    for frase in ["¿alguna vez hablamos de bot_trading?",
                  "¿hemos hablado de la arquitectura?"]:
        info = debug_route_layers(frase)
        assert info == {"layer": "kw", "lane": "memory:episode"}, frase

def test_recomendacion_para_atacar_tarea_va_a_memory_tasks():
    info = debug_route_layers("qué me recomiendas atacar primero")

    assert info == {"layer": "kw", "lane": "memory:tasks"}

def test_sugerencia_general_para_hoy_va_a_memory_reasoning():
    info = debug_route_layers("¿qué me sugieres hacer hoy?")

    assert info == {"layer": "kw", "lane": "memory:reasoning"}

def test_variantes_de_recomendacion_de_tareas_van_a_memory_tasks():
    for frase in [
        "por cual tarea me recomiendas empezar",
        "con cual tarea me conviene partir",
        "cuál tarea me conviene partir",
    ]:
        info = debug_route_layers(frase)

        assert info == {"layer": "kw", "lane": "memory:tasks"}, frase