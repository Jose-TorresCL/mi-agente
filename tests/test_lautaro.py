"""
test_lautaro.py
================
Suite de verificación funcional de Lautaro.
Cubre: router, herramientas, caché semántica, fidelidad RAG e indexación Chroma.

Nota: test_memoria_corta eliminado — _format_chat_history fue refactorizado
fuera de la API pública de chat_core en la reorganización intelligence.py.
La memoria corta ahora se gestiona internamente en process_turn.

Uso:
    python tests/test_lautaro.py

Requisitos previos:
    - Ollama corriendo: ollama serve
    - Modelos disponibles: llama3.2:latest y nomic-embed-text
    - storage/chroma con al menos un documento indexado
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── Colores consola ────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

passed   = []
failed   = []
warnings = []


def ok(name, detail=""):
    passed.append(name)
    print(f"  {GREEN}✅ PASS{RESET}  {name}" + (f"  →  {detail}" if detail else ""))


def fail(name, detail=""):
    failed.append(name)
    print(f"  {RED}❌ FAIL{RESET}  {name}" + (f"  →  {detail}" if detail else ""))


def warn(name, detail=""):
    warnings.append(name)
    print(f"  {YELLOW}⚠️  WARN{RESET}  {name}" + (f"  →  {detail}" if detail else ""))


def seccion(titulo):
    print(f"\n{BOLD}{CYAN}{'─'*60}{RESET}")
    print(f"{BOLD}{CYAN}  {titulo}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*60}{RESET}")


# ═══════════════════════════════════════════════════════════════════════════
# 1. ROUTER
# ═══════════════════════════════════════════════════════════════════════════
def test_router():
    seccion("1. Router — clasificación de intenciones")

    from app.router import route_query

    casos = [
        ("hasta luego",                              "exit",              "Salida: 'hasta luego'"),
        ("chao",                                     "exit",              "Salida: 'chao'"),
        ("guarda como hecho que el modelo es llama3.2", "tool_save_fact", "Guardar hecho"),
        ("crea una tarea: revisar fidelity_check",   "tool_create_task",  "Crear tarea"),
        ("marca T-001 como completada",              "tool_complete_task", "Completar tarea"),
        ("lista los archivos del proyecto",          "tool_list_files",   "Listar archivos"),
        ("¿cómo me llamo?",                          "memory",            "Query de memoria"),
        ("¿cuál es mi nombre?",                      "memory",            "Query de memoria 2"),
        ("¿qué es LangChain?",                       "rag",               "Query RAG"),
        ("explícame el paper de Google",             "rag",               "Query documental"),
    ]

    for entrada, esperada, descripcion in casos:
        ruta = route_query(entrada)
        if ruta == esperada:
            ok(f"1 — {descripcion}", f"'{entrada}' → {ruta}")
        else:
            fail(f"1 — {descripcion}", f"esperaba '{esperada}', obtuvo '{ruta}'")


# ═══════════════════════════════════════════════════════════════════════════
# 2. HERRAMIENTAS
# ═══════════════════════════════════════════════════════════════════════════
def test_tools():
    seccion("2. Herramientas básicas")

    from app.tools import tool_save_fact, tool_create_task, list_project_files

    # 2a: guardar hecho
    try:
        r = tool_save_fact("test de verificación automática")
        if "guard" in r.lower() or "hecho" in r.lower():
            ok("2a — tool_save_fact guarda y confirma", r[:60])
        else:
            warn("2a — tool_save_fact respondió, revisar mensaje", r[:60])
    except Exception as e:
        fail("2a — tool_save_fact excepción", str(e))

    # 2b: crear tarea
    try:
        r = tool_create_task(title="Tarea de prueba automática", priority="low")
        if "tarea" in r.lower() or "creada" in r.lower() or "T-" in r:
            ok("2b — tool_create_task crea la tarea", r[:60])
        else:
            warn("2b — tool_create_task respondió, revisar mensaje", r[:60])
    except Exception as e:
        fail("2b — tool_create_task excepción", str(e))

    # 2c: listar archivos
    try:
        archivos = list_project_files()
        if isinstance(archivos, list):
            ok(f"2c — list_project_files retorna lista ({len(archivos)} archivos)")
        else:
            fail("2c — list_project_files no retornó lista", type(archivos).__name__)
    except Exception as e:
        fail("2c — list_project_files excepción", str(e))


# ═══════════════════════════════════════════════════════════════════════════
# 3. CACHÉ SEMÁNTICA
# ═══════════════════════════════════════════════════════════════════════════
def test_cache_semantico():
    seccion("3. Caché semántica (umbral 0.88)")

    from app.semantic_cache import cache_lookup, cache_save, cache_invalidate, cache_stats

    pregunta_original = "¿cuál es el objetivo principal de Lautaro?"
    pregunta_similar  = "¿cuál es el objetivo de Lautaro?"
    pregunta_distinta = "¿qué es un transformer en deep learning?"

    try:
        cache_invalidate(pregunta_original)
    except Exception:
        pass

    # 3a: sin caché → None
    if cache_lookup(pregunta_original) is None:
        ok("3a — Pregunta nueva no tiene caché (correcto)")
    else:
        warn("3a — Ya tenía caché previo (puede ser de sesión anterior)")

    # 3b: guardar y recuperar
    cache_save(pregunta_original, "Lautaro es un asistente local de proyecto.")
    r = cache_lookup(pregunta_original)
    if r is not None:
        ok("3b — cache_save + cache_lookup exacto funciona", r[:50])
    else:
        fail("3b — cache_save guardó pero cache_lookup no recuperó")

    # 3c: similar debe recuperar
    r_sim = cache_lookup(pregunta_similar)
    if r_sim is not None:
        ok("3c — Pregunta similar recupera del caché (umbral ok)", r_sim[:50])
    else:
        warn("3c — Pregunta similar NO recuperó del caché (revisar umbral)")

    # 3d: distinta NO debe recuperar
    r_dis = cache_lookup(pregunta_distinta)
    if r_dis is None:
        ok("3d — Pregunta distinta no hace match en caché (correcto)")
    else:
        warn("3d — Pregunta distinta hizo match (revisar umbral)", r_dis[:50])

    # 3e: stats
    try:
        stats = cache_stats()
        if isinstance(stats, dict):
            ok("3e — cache_stats retorna dict válido", str(stats))
        else:
            warn("3e — cache_stats retornó tipo inesperado", type(stats).__name__)
    except Exception as e:
        fail("3e — cache_stats excepción", str(e))


# ═══════════════════════════════════════════════════════════════════════════
# 4. FIDELIDAD
# ═══════════════════════════════════════════════════════════════════════════
def test_fidelidad():
    seccion("4. Verificación de fidelidad (fidelity_check)")

    from app.fidelity_check import verify_fidelity, NO_EVIDENCE_MSG
    from langchain_core.documents import Document

    docs = [
        Document(page_content="Lautaro usa LangChain y Chroma para RAG local.", metadata={}),
        Document(page_content="El modelo base es llama3.2 corriendo en Ollama.", metadata={}),
    ]

    # 4a: respuesta fiel → True
    if verify_fidelity("Lautaro usa LangChain y Chroma para RAG.", docs) is True:
        ok("4a — Respuesta fiel pasa verificación")
    else:
        fail("4a — Respuesta fiel fue rechazada (falso negativo)")

    # 4b: respuesta inventada → False
    if verify_fidelity("Lautaro usa GPT-4 y Pinecone para embeddings.", docs) is False:
        ok("4b — Respuesta inventada es correctamente rechazada")
    else:
        warn("4b — Respuesta inventada no fue rechazada (revisar umbral)")

    # 4c: sin documentos → False
    if verify_fidelity("cualquier respuesta", []) is False:
        ok("4c — Sin docs, fidelidad rechaza correctamente")
    else:
        warn("4c — Sin docs, fidelidad pasó (revisar lógica)")

    # 4d: NO_EVIDENCE_MSG definido
    if NO_EVIDENCE_MSG and len(NO_EVIDENCE_MSG) > 5:
        ok("4d — NO_EVIDENCE_MSG está definido", NO_EVIDENCE_MSG[:60])
    else:
        fail("4d — NO_EVIDENCE_MSG no está definido o vacío")


# ═══════════════════════════════════════════════════════════════════════════
# 5. CHROMA
# ═══════════════════════════════════════════════════════════════════════════
def test_chroma():
    seccion("5. Indexación Chroma (RAG)")

    storage_path = ROOT / "storage" / "chroma"

    if not storage_path.exists():
        fail("5a — storage/chroma no existe", "Ejecuta: python indexacion.py")
        return

    ok("5a — Directorio storage/chroma existe")

    archivos = list(storage_path.iterdir())
    if not archivos:
        fail("5b — Directorio chroma está vacío")
        return
    ok(f"5b — Chroma tiene {len(archivos)} archivos/carpetas")

    try:
        from app.chat_core import load_vector_store
        vectordb = load_vector_store()
        ok("5c — Conexión con Chroma exitosa (Ollama activo)")

        retriever = vectordb.as_retriever(search_kwargs={"k": 2})
        docs = retriever.invoke("¿qué es Lautaro?")
        if docs:
            ok(f"5d — Búsqueda retornó {len(docs)} documento(s)", docs[0].page_content[:60])
        else:
            warn("5d — Búsqueda retornó 0 docs (¿hay docs indexados?)")

    except Exception as e:
        msg = str(e).lower()
        if "connection" in msg or "refused" in msg:
            warn("5c — Ollama no está corriendo", "Inicia con: ollama serve")
        else:
            fail("5c — Error al conectar con Chroma", str(e)[:100])


# ═══════════════════════════════════════════════════════════════════════════
# REPORTE FINAL
# ═══════════════════════════════════════════════════════════════════════════
def reporte_final():
    total = len(passed) + len(failed)
    print(f"\n{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}  REPORTE FINAL — Lautaro{RESET}")
    print(f"{BOLD}{'═'*60}{RESET}")
    print(f"  {GREEN}✅ Pasaron:{RESET}  {len(passed)}/{total}")
    print(f"  {RED}❌ Fallaron:{RESET} {len(failed)}/{total}")
    if warnings:
        print(f"  {YELLOW}⚠️  Avisos:{RESET}  {len(warnings)}")
    print()

    if failed:
        print(f"{RED}{BOLD}  Tests fallidos:{RESET}")
        for f in failed:
            print(f"  {RED}  • {f}{RESET}")
        print()

    if warnings:
        print(f"{YELLOW}{BOLD}  Avisos (no bloquean, pero revisar):{RESET}")
        for w in warnings:
            print(f"  {YELLOW}  • {w}{RESET}")
        print()

    if not failed:
        print(f"{GREEN}{BOLD}  Lautaro está funcionando correctamente. ✨{RESET}\n")
    else:
        print(f"{RED}{BOLD}  Hay {len(failed)} test(s) que necesitan atención.{RESET}\n")

    return len(failed) == 0


# ═══════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print(f"\n{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}  Suite de tests — Lautaro{RESET}")
    print(f"{BOLD}{'═'*60}{RESET}")

    test_router()
    test_tools()
    test_cache_semantico()
    test_fidelidad()
    test_chroma()

    ok_final = reporte_final()
    sys.exit(0 if ok_final else 1)
