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

def test_consultas_juicio_van_a_work_state():
    for frase in ["qué me recomiendas atacar primero",
                  "¿qué me sugieres hacer hoy?"]:
        info = debug_route_layers(frase)
        assert info == {"layer": "kw", "lane": "memory:work_state"}, frase

def test_variantes_juicio_tareas_van_a_work_state():
    from app.router import debug_route_layers
    for frase in ["por cual tarea me recomiendas empezar",
                  "con cual tarea me conviene partir"]:
        info = debug_route_layers(frase)
        assert info == {"layer": "kw", "lane": "memory:work_state"}, frase