from __future__ import annotations

import re
from typing import TypedDict

# Palabras de salida
_EXIT_WORDS = {
    "salir", "exit", "quit", "bye",
    "sal", "salo", "sali", "salie",
    "chao", "chau",
    "adios",
    "hasta luego", "hasta pronto",
    "nos vemos",
    "me voy", "cierro",
    "by",
    "cerrar sesion", "cerrar la sesion",
    "terminar sesion", "terminar la sesion",
    "fin de sesion", "finalizar sesion",
}

# Carriles de escritura
_WRITE_LANES = {
    "tool_save_fact", "tool_create_task", "tool_complete_task",
    "tool_update_work_state", "tool_set_session_goal",
}

# Verbos lectores (Fix B3)
_READ_VERBS = {
    "leer", "lee", "abre", "abrir",
    "muestrame", "mostrar", "ver", "open",
}

# Listas de keywords (Capa 1)
TOOL_LIST_KEYWORDS = [
    "listar archivos", "lista de archivos", "que archivos",
    "archivos del proyecto", "ver archivos", "mostrar archivos",
    "muestrame los archivos",
    "que hay en el proyecto",
]

TOOL_READ_KEYWORDS = [
    "leer archivo", "muestrame el archivo",
    "abre el archivo", "ver archivo", "mostrar archivo", "lee el archivo",
    "leer docs", "leer documentacion", "leer documento", "mostrar documento",
]

MEMORY_PROFILE_KEYWORDS = [
    "mi estilo", "estilo preferido", "preferencia", "preferido",
    "como prefiero", "como trabajo",
    "perfil", "mi perfil",
    "quien soy", "quien soy yo",
    "como me llamo", "mi nombre", "cual es mi nombre",
]

MEMORY_WORK_STATE_KEYWORDS = [
    "estado actual", "foco actual", "siguiente paso",
    "en que vamos", "que sigue",
    "en que estoy", "que estoy haciendo",
    "ultimo paso", "en que quedamos",
    "que hicimos", "en que estamos", "que hago hoy",
    "cual es el plan",
    "cual es mi foco", "que estoy trabajando",
    "que estaba haciendo", "a que me dedico ahora",
    "que bloquea", "que esta bloqueando", "que esta frenando",
    "que me bloquea", "que nos bloquea", "que bloqueo hay",
    "hay algun bloqueo", "cuales son los bloqueos",
    "que impide", "que me impide", "que nos impide",
    "que obstaculiza", "hay obstaculos", "que obstaculo hay",
    "que frena", "que frena el avance", "que esta frenando el avance",
    "por que no avanzamos", "por que no avanzo",
    "que me detiene", "que nos detiene",
]

MEMORY_TASKS_KEYWORDS = [
    "que tareas hay", "mis tareas", "mis tareas pendientes",
    "lista de tareas pendientes",
    "tareas pendientes", "tareas abiertas",
    "que tengo pendiente", "que tareas tengo",
    "ponme al dia",
    "tareas", "ver tareas", "mostrar tareas",
    "tareas hechas", "tareas completadas", "tareas cerradas",
    "que tareas hice",
    "lista todas las tareas", "todas las tareas",
]
_TASK_PRIORITY_QUERY_PHRASES = [
    "cual es la de mas alta prioridad",
    "cual tiene mayor prioridad",
    "cuales son las tareas mas importantes",
    "que tarea es mas importante",
    "hay tareas de alta prioridad",
    "tengo tareas de alta prioridad",
]

_TASK_RECOMMENDATION_QUERY_PHRASES = [
    # Consultas breves que ya implican elegir una tarea.
    "por cual empiezo",
    "por cual tarea empiezo",
    "que ataco primero",
    "cual ataco primero",
    "que me recomendas atacar primero",
    "que me recomiendas atacar primero",

    # Variantes explícitas sobre una tarea.
    "por cual tarea me recomiendas empezar",
    "con cual tarea me conviene partir",
    "cual tarea me conviene partir",
    "cual tarea me conviene empezar",
    "cual tarea deberia empezar",
    "que tarea me conviene",
    "que tarea deberia empezar",
    "que tarea me conviene ahora",
    "cual tarea deberia empezar ahora",
]

_TASK_SUGGESTION_SIGNALS = [
    "podriamos", "podrias",
    "agregar", "sugerir",
    "posibles", "ideas", "proponer", "que mas",
    "implementar", "anadir",
]

MEMORY_PROJECT_FACTS_KEYWORDS = [
    "fase actual", "fase del proyecto", "estado del proyecto",
    "hechos del proyecto", "datos del proyecto",
    "en que fase", "nombre del proyecto",
    "sprint", "en que sprint",
    "que sprint", "sprint actual",
]

_RE_RECENT_EPISODE = re.compile(
    r"ultimas?\s+(\d+\s+)?(sesiones|conversaciones|veces)",
    re.IGNORECASE,
)

MEMORY_EPISODE_KEYWORDS = [
    "que aprendi", "que aprendimos",
    "sesion anterior", "ultima sesion",
    "sesiones anteriores", "la semana pasada", "ayer trabajamos",
    "que hicimos antes", "que trabajamos",
    "historial de sesiones", "episodios anteriores",
    "que avance", "que avanzamos",
    "ultima vez que","alguna vez", "hablamos de", "hablamos sobre",
    "hemos hablado", "ya habiamos",
    "briefing", "dame un briefing",
    "retomar el trabajo", "retomar trabajo", "retomar la sesion",
    "desde el ultimo episodio", "desde el ultimo episodio sugiere",
    "por donde empezar hoy", "por donde empezamos hoy",
    "resumen de la sesion anterior", "dame un resumen de la sesion",
    "que paso en la sesion anterior", "que hicimos en la sesion anterior",
    "acciones concretas que deberia hacer hoy",
    "sugerencias desde el ultimo episodio",
    "ultimas sesiones", "sesiones recientes", "sesiones pasadas",
    "ultimas conversaciones", "conversaciones recientes",
]

TRIVIAL_CONVERSATIONAL_KEYWORDS = [
    "hola",
    "holi",
    "buenas",
    "buenos dias",
    "buen día",
    "buen dia",
    "buenas tardes",
    "buenas noches",
    "gracias",
    "muchas gracias",
    "ok",
    "oki",
    "dale",
    "listo",
    "perfecto",
]

AGENT_IDENTITY_KEYWORDS = [
    "quien eres", "quien eres tu",
    "que eres", "que eres tu",
    "que puedes hacer", "que puedes",
    "que sabes hacer",
    "para que sirves",
    "cuentame de ti", "cuentame sobre ti",
    "dime quien eres",
    "como te llamas", "cual es tu nombre",
    "que modelo eres",
    "cuales son tus capacidades",
    "que herramientas tienes",
    "tus limites", "que no puedes hacer",
    "tus capacidades",
]

TOOL_SAVE_FACT_KEYWORDS = [
    "guarda como hecho", "guardar hecho", "registra que", "anota que",
    "guarda el hecho", "registra el hecho", "guarda esto como hecho",
]

TOOL_SAVE_NOTE_KEYWORDS = [
    "guarda esta nota", "guarda esta anotacion", "guarda esto",
    "anota esto", "anotá esto", "guardá esto",
    "guardá esta nota", "registrá esto", "registra esto",
    "guarda el siguiente apunte", "apunta esto", "apuntá esto",
    "nota:", "apunte:", "quiero guardar",
    "guarda que", "guardá que",
]

TOOL_CREATE_TASK_KEYWORDS = [
    "crea una tarea", "crear tarea", "agrega una tarea", "agregar tarea",
    "nueva tarea", "anade una tarea", "anota una tarea", "registra una tarea",
    "crea tarea", "crea la tarea", "crea tarea:",
    "agrega tarea", "agrega la tarea",
    "áñade una tarea", "áñade tarea",
    "nueva tarea:", "tarea nueva:",
]

TOOL_COMPLETE_TASK_KEYWORDS = [
    "marca como completada", "marca como completado",
    "marcar como completada", "marcar como completado",
    "cierra la tarea", "cerrar tarea",
    "complete la tarea",
    "tarea completada", "completar tarea",
    "como completada", "como completado",
]

# Patrón de cierre de tareas.
#
# Se evalúa en router.py antes de memoria/episodios. Acepta:
# - formas de voseo: "marcá", "cerrá", "finalizá";
# - formas neutras: "marca", "cerrar", "finalizar";
# - estados equivalentes: completada, terminada y finalizada;
# - referencias por ID, ordinal o título.
#
# La pregunta debe contener una acción de escritura; por eso no captura
# consultas como "qué tareas están terminadas".
_COMPLETE_TASK_PATTERN = re.compile(
    r"^(?:"
    r"(?:marca(?:r)?(?:\s+(?:la\s+)?tarea)?(?:\s+(?:t[- ]?\d+|.+?))?\s+como\s+(?:completad[oa]|terminad[oa]|finalizad[oa])(?:\s+.*)?)"
    r"|(?:marca(?:r)?\s+t[- ]?\d+(?:\s+.*)?)"
    r"|(?:cerrar(?:\s+la)?\s+tarea(?:\s+pendiente)?(?:\s+.*)?)"
    r"|(?:cierra(?:r)?\s+(?:la\s+)?tarea(?:\s+.*)?)"
    r"|(?:finalizar(?:\s+la)?\s+tarea(?:\s+.*)?)"
    r"|(?:finaliza(?:r)?\s+(?:la\s+)?tarea(?:\s+.*)?)"
    r"|(?:completar(?:\s+la)?\s+tarea(?:\s+.*)?)"
    r"|(?:complete(?:\s+la)?\s+tarea(?:\s+.*)?)"
    r"|(?:marcar\s+como\s+(?:completad[oa]|terminad[oa]|finalizad[oa])(?:\s+.*)?)"
    r")$",
    re.IGNORECASE,
)

TOOL_UPDATE_WORK_STATE_KEYWORDS = [
    "actualiza el foco", "cambia el foco", "enfocate en", "ahora estoy en",
    "complete", "termine", "acabe", "ya hice", "listo:",
    "el siguiente paso es", "sigue:", "proximo paso",
    "nuevo bloqueo", "actualiza bloqueante", "actualiza el estado de trabajo",
    "foco a ", "foco en ",
    "mi foco es", "mi foco sera", "mi foco ahora es",
    "cambio de foco", "cambio el foco",
    "ahora me enfoco en", "me enfoco en", "siguiente paso:", "siguiente paso es", "pon en siguiente paso",
    "proximo paso:", "próximo paso:", "actualiza el siguiente paso",
    "cambia el siguiente paso",
    "quiero enfocarme en", "voy a enfocarme en",
]

TOOL_SET_SESSION_GOAL_KEYWORDS = [
    "mi objetivo hoy es",
    "mi objetivo para hoy es",
    "objetivo de esta sesion",
    "objetivo de hoy",
    "quiero lograr hoy",
    "quiero lograr esta sesion",
    "meta de hoy es",
    "meta de esta sesion",
    "hoy quiero",
    "en esta sesion quiero",
    "define mi objetivo",
    "guarda mi objetivo",
    "mi meta hoy",
]

# Carril tool_plan_retoma (lectura de analysis/retoma_plan.json).
# Deliberadamente NO incluye "plan" ni "tareas" sueltos: esas palabras ya
# pertenecen a memory:work_state ("cual es el plan") y memory:tasks ("tareas"),
# y meterlas aquí le robaría consultas a carriles que ya funcionan.
# Regla: frases específicas > palabras genéricas.
TOOL_PLAN_RETOMA_KEYWORDS = [
    "plan de retoma",
    "plan retoma",
    "plan_retoma",
    "retoma del proyecto",
    "retomar el proyecto",
    "auditoria de documentacion",
    "auditoria de la documentacion",
    "estado de la documentacion",
    "que me falta documentar",
    "acciones del plan",
    "proximas acciones del plan",
    "recomendaciones del plan",
    "secciones faltantes",
]

# Keywords para tool_analizar_mercado — detectan intent de consulta de mercado
TOOL_ANALIZAR_MERCADO_KEYWORDS = [
    # Consultas directas de precio
    "precio del btc", "precio de btc", "precio bitcoin",
    "precio del eth", "precio de eth", "precio ethereum",
    "precio actual", "precio de la cripto", "precio del cripto",
    "cuanto vale el btc", "cuanto vale btc", "cuanto vale bitcoin",
    "cuanto vale el eth", "cuanto vale eth", "cuanto vale ethereum",
    "cuanto esta el btc", "cuanto esta bitcoin",
    "cuanto esta el eth", "cuanto esta ethereum",
    # Consultas de señal / análisis
    "senal de trading", "señal de trading",
    "senal del mercado", "señal del mercado",
    "analiza el mercado", "analizame el mercado",
    "analizar mercado", "consulta el mercado",
    "que dice el mercado", "como esta el mercado",
    "indicadores del mercado", "indicadores de btc",
    "rsi de btc", "rsi bitcoin", "rsi eth",
    "ema de btc", "atr de btc",
    # Frases cortas con crypto
    "btcusdt", "ethusdt",
    "analizar btc", "analizar eth",
    "como va el btc", "como va bitcoin",
    "como va el eth", "como va ethereum",
    "dame la senal", "dame la señal",
    "hay senal", "hay señal",
    "mercado cripto", "mercado crypto",
    "consulta mercado", "ver mercado",
]

TOOL_UNSUPPORTED_KEYWORDS = [
    "cuantas lineas",
    "lineas de codigo", "lineas tiene",
    "cuanto codigo", "cuantas lineas de codigo",
    "tamano del proyecto", "peso del proyecto",
    "cuantos archivos hay", "cuantos archivos tiene",
    "cuantas funciones hay", "cuantas funciones tiene",
    "cuantas clases hay", "cuantas clases tiene",
    "cuantas funciones", "cuantas clases",
]

MATH_KEYWORDS = [
    "dividido", "dividido entre", "dividido por",
    "multiplicado", "multiplicado por",
    "mas menos", "cuanto es", "cuanto da",
    "resultado de", "calcula", "calculame",
    "calculá", "calculame esto",
    "cuanto suma", "cuanto resta",
    "cuanto multiplica",
    "raiz de", "raiz cuadrada",
    "potencia de", "al cuadrado", "al cubo",
    "porcentaje de", "el porcentaje",
    "cuantos son",
]

_RE_MATH_EXPR = re.compile(
    r'^\s*[\d.,]+\s*[+\-*/÷x×]\s*[\d.,]+\s*$',
    re.IGNORECASE,
)

RAG_HINTS = [
    "segun los documentos", "como se usa", "diferencia de", "que es", "para que sirve", "componentes", "partes", "metodos",
    "segun la documentacion",
    "segun los archivos",
    "que dice", "que hace",
    "como funciona", "como esta",
    "arquitectura",
    "relacion entre",
    "diferencia entre",
    "que es el", "que es la", "que es un", "que es una",
    "que es",
    "para que sirve",
    "explicame", "explicame el", "explicame la",
    "para que sirve el", "para que sirve la",
]

MEMORY_REASONING_KEYWORDS = [
    # Consultas de razonamiento sobre el estado de trabajo en general.
    #
    # Las consultas que mencionan elegir, priorizar o recomendar una tarea
    # concreta se resuelven en memory:tasks, donde se usa tasks.json real.
    "que me conviene hacer",
    "que me conviene hacer ahora",
    "que me recomiendas hacer",
    "que me sugieres hacer hoy",
]

_RE_TASK_RECOMMENDATION = re.compile(
    r"(qué|cuál|por cuál).*(tarea|acción).*(empezar|hacer|conviene)",
    re.IGNORECASE,
)

VALID_LANES = {
    "tool_list_files", "tool_read_file", "tool_save_fact",
    "tool_create_task", "tool_complete_task", "tool_update_work_state",
    "tool_set_session_goal", "tool_plan_retoma", "tool_analizar_mercado",
    "memory",
    "memory:profile", "memory:work_state", "memory:tasks",
    "memory:project_facts", "memory:episode", "memory:reasoning",
    "rag", "identity",
    "unsupported",
    "math",
    "tool_save_note",
}

class RouterDebugInfo(TypedDict):
    layer: str
    lane: str | None

__all__ = [
    "_EXIT_WORDS",
    "_WRITE_LANES",
    "_READ_VERBS",
    "_RE_RECENT_EPISODE",
    "TOOL_LIST_KEYWORDS",
    "TOOL_READ_KEYWORDS",
    "MEMORY_PROFILE_KEYWORDS",
    "MEMORY_WORK_STATE_KEYWORDS",
    "MEMORY_TASKS_KEYWORDS",
    "_TASK_PRIORITY_QUERY_PHRASES",
    "_TASK_RECOMMENDATION_QUERY_PHRASES",
    "_TASK_SUGGESTION_SIGNALS",
    "MEMORY_PROJECT_FACTS_KEYWORDS",
    "MEMORY_EPISODE_KEYWORDS",
    "TRIVIAL_CONVERSATIONAL_KEYWORDS",
    "AGENT_IDENTITY_KEYWORDS",
    "TOOL_SAVE_FACT_KEYWORDS",
    "TOOL_SAVE_NOTE_KEYWORDS",
    "TOOL_CREATE_TASK_KEYWORDS",
    "TOOL_COMPLETE_TASK_KEYWORDS",
    "_COMPLETE_TASK_PATTERN",
    "TOOL_UPDATE_WORK_STATE_KEYWORDS",
    "TOOL_SET_SESSION_GOAL_KEYWORDS",
    "TOOL_PLAN_RETOMA_KEYWORDS",
    "TOOL_ANALIZAR_MERCADO_KEYWORDS",
    "TOOL_UNSUPPORTED_KEYWORDS",
    "MATH_KEYWORDS",
    "_RE_MATH_EXPR",
    "RAG_HINTS",
    "MEMORY_REASONING_KEYWORDS",
    "VALID_LANES",
    "RouterDebugInfo",
]