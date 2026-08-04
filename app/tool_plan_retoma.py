"""Tool de lectura del plan de retoma — `analysis/retoma_plan.json`.

Responsabilidad
---------------
Exponer, como tool de solo lectura, el plan de retoma del proyecto:
la auditoría de documentación que dice qué falta, qué recomendar y
qué hacer a continuación.

Fuente de datos
---------------
`analysis/retoma_plan.json` (versionado en el repo, editable a mano).
Estructura esperada — un diccionario con estas claves de primer nivel:

    validation        dict[str, str]   estado por documento (ok | pendiente)
    missing_sections  list[str]        secciones faltantes detectadas
    recommendations   list[str]        mejoras propuestas
    next_actions      list[str]        acciones concretas siguientes

Uso
---
    from app.tool_plan_retoma import tool_plan_retoma

    tool_plan_retoma()                    # resumen de todas las secciones
    tool_plan_retoma("next_actions")      # solo esa sección
    tool_plan_retoma("acciones")          # alias en español

Clasificación
-------------
risk = RiskLevel.READ — no escribe nada, no toca red, no ejecuta procesos.

Never raises: cualquier fallo (archivo ausente, JSON inválido, clave
desconocida) se devuelve como ToolResult(ok=False, error_code=...).
"""
from __future__ import annotations

import json
from pathlib import Path

from app.logger import get_logger
from app.schemas import ToolResult

log = get_logger(__name__)

# ──────────────────────────────────────────────
PLAN_FILE = Path("analysis") / "retoma_plan.json"
TOOL_NAME = "tool_plan_retoma"

# Claves canónicas del JSON, en orden de lectura natural.
SECCIONES: tuple[str, ...] = (
    "validation",
    "missing_sections",
    "recommendations",
    "next_actions",
)

# Alias en español / lenguaje natural → clave canónica.
_ALIAS: dict[str, str] = {
    "validacion": "validation",
    "validación": "validation",
    "estado": "validation",
    "faltantes": "missing_sections",
    "faltante": "missing_sections",
    "secciones_faltantes": "missing_sections",
    "missing": "missing_sections",
    "recomendaciones": "recommendations",
    "mejoras": "recommendations",
    "acciones": "next_actions",
    "proximos_pasos": "next_actions",
    "próximos_pasos": "next_actions",
    "siguientes": "next_actions",
    "next": "next_actions",
}

_TITULOS: dict[str, str] = {
    "validation": "📋 Estado de validación",
    "missing_sections": "🕳️ Secciones faltantes",
    "recommendations": "💡 Recomendaciones",
    "next_actions": "▶️ Próximas acciones",
}
# ──────────────────────────────────────────────


def _normalizar_clave(texto: str) -> str | None:
    """Traduce texto libre a una clave canónica del plan.

    Devuelve None si no hay coincidencia. No adivina: preferimos
    responder 'no reconocí la sección' antes que devolver la sección
    equivocada (evita ambigüedad de router).
    """
    clave = texto.strip().lower().replace(" ", "_").replace("-", "_")
    if clave in SECCIONES:
        return clave
    if clave in _ALIAS:
        return _ALIAS[clave]
    # Coincidencia parcial: 'next_actions?' , 'las recomendaciones'
    for candidato in SECCIONES:
        if candidato in clave:
            return candidato
    for alias, canonica in _ALIAS.items():
        if alias in clave:
            return canonica
    return None


def _cargar_plan(ruta: Path = PLAN_FILE) -> dict:
    """Lee y parsea el JSON del plan. Lanza excepciones: uso interno."""
    with open(ruta, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("el plan debe ser un objeto JSON en la raíz")
    return data


def _formatear_seccion(clave: str, valor) -> str:
    """Convierte una sección del plan a texto legible."""
    titulo = _TITULOS.get(clave, clave)
    if isinstance(valor, dict):
        cuerpo = "\n".join(f"  - {k}: {v}" for k, v in valor.items())
    elif isinstance(valor, list):
        cuerpo = "\n".join(f"  {i}. {item}" for i, item in enumerate(valor, 1))
    else:
        cuerpo = f"  {valor}"
    return f"{titulo}\n{cuerpo}" if cuerpo else f"{titulo}\n  (vacío)"


def tool_plan_retoma(seccion: str | None = None, ruta: Path = PLAN_FILE) -> ToolResult:
    """Devuelve el plan de retoma completo o una sección concreta.

    Args:
        seccion: clave o alias ('next_actions', 'acciones', 'recomendaciones'…).
                 Si es None o vacío, devuelve un resumen de todas las secciones.
        ruta:    ruta del JSON. Parametrizable para tests.

    Returns:
        ToolResult con:
          message: texto listo para mostrar.
          data:    {"seccion": <clave|"all">, "contenido": <valor>, "claves": [...]}

    Códigos de error:
        PLAN_NOT_FOUND   el archivo no existe.
        INVALID_JSON     el archivo existe pero no es JSON válido.
        UNKNOWN_SECTION  la sección pedida no está en el plan.
        READ_ERROR       cualquier otro fallo de lectura.
    """
    if not ruta.exists():
        log.warning("[%s] plan no encontrado: %s", TOOL_NAME, ruta)
        return ToolResult(
            ok=False,
            message=f"⚠️ No encontré el plan de retoma en '{ruta}'.",
            error_code="PLAN_NOT_FOUND",
            tool_name=TOOL_NAME,
        )

    try:
        plan = _cargar_plan(ruta)
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("[%s] JSON inválido: %s", TOOL_NAME, exc)
        return ToolResult(
            ok=False,
            message=f"⚠️ El plan de retoma existe pero no es JSON válido ({exc}).",
            error_code="INVALID_JSON",
            tool_name=TOOL_NAME,
        )
    except Exception as exc:  # pragma: no cover — defensa, never raises
        log.warning("[%s] error leyendo el plan: %s", TOOL_NAME, exc)
        return ToolResult(
            ok=False,
            message=f"⚠️ No pude leer el plan de retoma: {exc}",
            error_code="READ_ERROR",
            tool_name=TOOL_NAME,
        )

    claves = list(plan.keys())

    # ── Caso 1: sección concreta ──────────────────────────
    if seccion and seccion.strip():
        clave = _normalizar_clave(seccion)
        if clave is None or clave not in plan:
            return ToolResult(
                ok=False,
                message=(
                    f"⚠️ No reconocí la sección '{seccion}'. "
                    f"Secciones disponibles: {', '.join(claves)}."
                ),
                error_code="UNKNOWN_SECTION",
                data={"claves": claves},
                tool_name=TOOL_NAME,
            )
        contenido = plan[clave]
        log.info("[%s] sección '%s' entregada", TOOL_NAME, clave)
        return ToolResult(
            ok=True,
            message=_formatear_seccion(clave, contenido),
            data={"seccion": clave, "contenido": contenido, "claves": claves},
            tool_name=TOOL_NAME,
        )

    # ── Caso 2: resumen completo ──────────────────────────
    orden = [k for k in SECCIONES if k in plan] + [k for k in claves if k not in SECCIONES]
    bloques = [_formatear_seccion(k, plan[k]) for k in orden]
    resumen = "🧭 Plan de retoma (analysis/retoma_plan.json)\n\n" + "\n\n".join(bloques)
    log.info("[%s] plan completo entregado (%d secciones)", TOOL_NAME, len(orden))
    return ToolResult(
        ok=True,
        message=resumen,
        data={"seccion": "all", "contenido": plan, "claves": claves},
        tool_name=TOOL_NAME,
    )


def build_episode_plan_retoma(
    date: str,
    time: str = "00:00",
    ruta: Path = PLAN_FILE,
) -> dict | None:
    """Construye un episodio 'plan_retoma' a partir del plan actual.

    Pensado para poblar `storage/episodic_memory.json` sin escribir a mano.
    Devuelve None si el plan no se puede leer (never raises).

    Uso:
        from app.tool_plan_retoma import build_episode_plan_retoma
        ep = build_episode_plan_retoma("2026-08-03", "20:58")
    """
    try:
        plan = _cargar_plan(ruta)
    except Exception as exc:
        log.warning("[%s] build_episode: no pude leer el plan: %s", TOOL_NAME, exc)
        return None

    pendientes = [k for k, v in (plan.get("validation") or {}).items() if v != "ok"]
    return {
        "date": date,
        "time": time,
        "type": "plan_retoma",
        "turns": 1,
        "summary": (
            "Auditoría de documentación al retomar el proyecto: "
            f"{len(pendientes)} documento(s) pendiente(s) ({', '.join(pendientes) or 'ninguno'}), "
            f"{len(plan.get('missing_sections', []))} secciones faltantes y "
            f"{len(plan.get('next_actions', []))} acciones siguientes. "
            "Decisión: documentar la integración con bot_trading (ADR-010) antes de expandir."
        ),
        "details": plan,
        "carril_dominante": "tool_plan_retoma",
        "tareas_completadas": 0,
        "exitoso": None,
        "source": "analysis/retoma_plan.json",
    }


if __name__ == "__main__":  # pragma: no cover — smoke test manual
    import sys

    arg = sys.argv[1] if len(sys.argv) > 1 else None
    resultado = tool_plan_retoma(arg)
    print(f"ok={resultado['ok']} error_code={resultado.get('error_code')}")
    print(resultado["message"])
