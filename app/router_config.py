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
    # Fix exit-cerrar-sesion: variantes de cierre con frase compuesta
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
    "que hago hoy", "cual es el plan",
    "que hicimos", "en que estamos",
    "cual es mi foco", "que estoy trabajando",
    "que estaba haciendo", "a que me dedico ahora",
    # Fix 2: preguntas de bloqueo/impedimento → work_state.current_blockers
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

MEMORY_EPISODE_KEYWORDS = [
    "que aprendi", "que aprendimos",
    "sesion anterior", "ultima sesion",
    "sesiones anteriores", "la semana pasada", "ayer trabajamos",
    "que hicimos antes", "que trabajamos",
    "historial de sesiones", "episodios anteriores",
    "que avance", "que avanzamos",
    "ultima vez que",
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

# Fix: keywords para guardar notas libres → tool_save_fact
# Antes estas frases caían a RAG porque no había keywords de nota.
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
]

TOOL_COMPLETE_TASK_KEYWORDS = [
    "marca como completada", "marca como completado",
    "marcar como completada", "marcar como completado",
    "cierra la tarea", "cerrar tarea",
    "complete la tarea",
    "tarea completada", "completar tarea",
    "como completada", "como completado",
]

_COMPLETE_TASK_PATTERN = re.compile(
    r"(marca|marcar|cierra|cerrar|completar|complete)\s+(t-\d+|la tarea|el issue|el paso)",
    re.IGNORECASE,
)

TOOL_UPDATE_WORK_STATE_KEYWORDS = [
    "actualiza el foco", "cambia el foco", "enfocate en", "ahora estoy en",
    "complete", "termine", "acabe", "ya hice", "listo:",
    "el siguiente paso es", "sigue:", "proximo paso",
    "nuevo bloqueo", "actualiza bloqueante", "actualiza el estado de trabajo",
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

# Fix: carril math para preguntas aritméticas y matemáticas puras
# Antes estas preguntas caían a RAG donde el fidelity las bloqueaba
# porque los números del enunciado no aparecen en ningún chunk.
MATH_KEYWORDS = [
    # Operaciones explícitas
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
    # Patrones numéricos directos (ej. "847 / 13", "20 * 5")
    # Se evalúan con regex en router.py, no como keyword exacta
]

# Patrón regex para expresiones matemáticas directas: "847 / 13", "20 * 5", "3 + 4"
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

# [A] Fix A: keywords de razonamiento personal → memory:work_state
MEMORY_REASONING_KEYWORDS = [
    "que me conviene hacer",
    "que me conviene atacar",
    "que me conviene primero",
    "que deberia hacer primero",
    "que deberia atacar primero",
    "que deberia hacer hoy",
    "que deberiamos hacer primero",
    "que deberiamos atacar",
    "por donde empiezo",
    "por donde empezamos",
    "por donde arranco",
    "por donde arrancamos",
    "que me recomendas hacer",
    "que me recomendas atacar",
    "que me recomendarías",
    "que es lo mas importante para mi",
    "cual es lo mas importante para mi",
    "que es lo primero que debo hacer",
    "como priorizo mis tareas",
    "como priorizamos",
    "como ordeno mis tareas",
    "que hago primero",
    "que hacemos primero",
    "cual es mi prioridad ahora",
    "cuales son mis prioridades",
]

VALID_LANES = {
    "tool_list_files", "tool_read_file", "tool_save_fact",
    "tool_create_task", "tool_complete_task", "tool_update_work_state",
    "tool_set_session_goal",
    "memory",
    "memory:profile", "memory:work_state", "memory:tasks",
    "memory:project_facts", "memory:episode",
    "rag", "identity",
    "unsupported",
    "math",           # Fix: carril para preguntas matemáticas puras
    "tool_save_note", # Fix: carril para guardar notas libres
}

class RouterDebugInfo(TypedDict):
    layer: str
    lane: str | None

__all__ = [
    "_EXIT_WORDS",
    "_WRITE_LANES",
    "_READ_VERBS",
    "TOOL_LIST_KEYWORDS",
    "TOOL_READ_KEYWORDS",
    "MEMORY_PROFILE_KEYWORDS",
    "MEMORY_WORK_STATE_KEYWORDS",
    "MEMORY_TASKS_KEYWORDS",
    "_TASK_SUGGESTION_SIGNALS",
    "MEMORY_PROJECT_FACTS_KEYWORDS",
    "MEMORY_EPISODE_KEYWORDS",
    "AGENT_IDENTITY_KEYWORDS",
    "TOOL_SAVE_FACT_KEYWORDS",
    "TOOL_SAVE_NOTE_KEYWORDS",
    "TOOL_CREATE_TASK_KEYWORDS",
    "TOOL_COMPLETE_TASK_KEYWORDS",
    "_COMPLETE_TASK_PATTERN",
    "TOOL_UPDATE_WORK_STATE_KEYWORDS",
    "TOOL_SET_SESSION_GOAL_KEYWORDS",
    "TOOL_UNSUPPORTED_KEYWORDS",
    "MATH_KEYWORDS",
    "_RE_MATH_EXPR",
    "RAG_HINTS",
    "MEMORY_REASONING_KEYWORDS",
    "VALID_LANES",
    "RouterDebugInfo",
]
