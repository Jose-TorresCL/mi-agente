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