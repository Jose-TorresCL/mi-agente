"""
run_eval.py — Evaluación formal del sistema (R3-D)

Lee los resultados de test_routing_matrix.py y test_bateria_20.py
y genera el reporte:

  Routing matrix : 27/27 correctos
  Batería 20     : 20/20 routing | 8/8 memoria
  TOTAL          : 47/47 — sistema habilitado para R7

No requiere Ollama activo — evaluación determinista, sin LLM.

Uso:
    python run_eval.py
    python run_eval.py --json        # salida JSON para CI
    python run_eval.py --fail-fast   # detiene al primer fallo
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from app.router import route_query, classify_memory_query
from tests.test_routing_matrix import ROUTING_MATRIX
from tests.test_bateria_20 import BATERIA_20


# Normaliza un carril potencialmente compuesto como "memory:profile"
def normalize_lane(raw_lane: Optional[str]) -> tuple[str, Optional[str]]:
    """Return (base_lane, subtype) where subtype may be None."""
    if not raw_lane:
        return "", None

    if ":" in raw_lane:
        base, subtype = raw_lane.split(":", 1)
        return base.strip(), subtype.strip()

    return raw_lane.strip(), None

# ─────────────────────────────────────────────────────────────
# Tipos de resultado
# ─────────────────────────────────────────────────────────────

@dataclass
class CaseResult:
    id: str
    pregunta: str
    ok: bool
    carril_esperado: str
    carril_obtenido: str
    memoria_esperada: Optional[str] = None
    memoria_obtenida: Optional[str] = None
    detalle: str = ""


@dataclass
class SuiteResult:
    nombre: str
    casos: list[CaseResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.casos)

    @property
    def pasados(self) -> int:
        return sum(1 for c in self.casos if c.ok)

    @property
    def fallidos(self) -> int:
        return self.total - self.pasados

    @property
    def porcentaje(self) -> float:
        return (self.pasados / self.total * 100) if self.total else 0.0


# ─────────────────────────────────────────────────────────────
# Evaluadores
# ─────────────────────────────────────────────────────────────

def evaluar_routing_matrix(fail_fast: bool = False) -> SuiteResult:
    """Evalúa los 27 casos de test_routing_matrix.py."""
    suite = SuiteResult(nombre="Routing Matrix (27 casos)")

    for pregunta, carril_esperado, descripcion in ROUTING_MATRIX:
        carril_real = route_query(pregunta)
        carril_base, carril_subtipo = normalize_lane(carril_real)
        ok = carril_base == carril_esperado
        resultado = CaseResult(
            id=descripcion.split(":")[0].strip(),
            pregunta=pregunta,
            ok=ok,
            carril_esperado=carril_esperado,
            carril_obtenido=carril_real,
            detalle=descripcion,
        )
        suite.casos.append(resultado)
        if fail_fast and not ok:
            break

    return suite


def evaluar_bateria_20(fail_fast: bool = False) -> SuiteResult:
    """Evalúa los 20 casos de test_bateria_20.py (carril + sub-tipo memoria)."""
    suite = SuiteResult(nombre="Batería 20 preguntas (carril + memoria)")

    for caso in BATERIA_20:
        carril_real = route_query(caso["pregunta"])
        carril_base, carril_subtipo = normalize_lane(carril_real)
        carril_ok = carril_base == caso["carril"]

        mem_esperada = caso.get("memoria")
        mem_real = None
        mem_ok = True
        if mem_esperada is not None and carril_base == "memory":
            # Preferir el subtipo ya emitido por el router (e.g. "memory:profile").
            if carril_subtipo is not None:
                mem_real = carril_subtipo
            else:
                mem_real = classify_memory_query(caso["pregunta"])
            mem_ok = mem_real == mem_esperada

        ok = carril_ok and mem_ok
        resultado = CaseResult(
            id=caso["id"],
            pregunta=caso["pregunta"],
            ok=ok,
            carril_esperado=caso["carril"],
            carril_obtenido=carril_real,
            memoria_esperada=mem_esperada,
            memoria_obtenida=mem_real,
        )
        suite.casos.append(resultado)
        if fail_fast and not ok:
            break

    return suite


# ─────────────────────────────────────────────────────────────
# Reporte en terminal
# ─────────────────────────────────────────────────────────────

VERDE  = "\033[92m"
ROJO   = "\033[91m"
AMAR   = "\033[93m"
NEGRI  = "\033[1m"
RESET  = "\033[0m"


def _color(ok: bool) -> str:
    return f"{VERDE}✅ PASS{RESET}" if ok else f"{ROJO}❌ FAIL{RESET}"


def imprimir_suite(suite: SuiteResult, verbose: bool = False) -> None:
    print(f"\n{NEGRI}{'─' * 60}{RESET}")
    print(f"{NEGRI}  {suite.nombre}{RESET}")
    print(f"{'─' * 60}")

    fallidos = [c for c in suite.casos if not c.ok]

    if verbose:
        for c in suite.casos:
            print(f"  [{c.id}] {_color(c.ok)}  {c.pregunta[:55]}")
            if not c.ok:
                print(f"         carril  esperado={c.carril_esperado!r}  "
                      f"obtenido={c.carril_obtenido!r}")
                if c.memoria_esperada:
                    print(f"         memoria esperada={c.memoria_esperada!r}  "
                          f"obtenida={c.memoria_obtenida!r}")
    else:
        if fallidos:
            print(f"  {AMAR}Fallos detectados:{RESET}")
            for c in fallidos:
                print(f"  [{c.id}] ❌  {c.pregunta[:55]}")
                print(f"         carril esperado={c.carril_esperado!r}  "
                      f"obtenido={c.carril_obtenido!r}")
                if c.memoria_esperada and c.memoria_obtenida != c.memoria_esperada:
                    print(f"         memoria esperada={c.memoria_esperada!r}  "
                          f"obtenida={c.memoria_obtenida!r}")
        else:
            print(f"  {VERDE}Todos los casos pasaron.{RESET}")

    color_total = VERDE if suite.fallidos == 0 else ROJO
    print(f"\n  Resultado: {color_total}{NEGRI}{suite.pasados}/{suite.total}{RESET}  "
          f"({suite.porcentaje:.0f}%)")


def imprimir_resumen(suites: list[SuiteResult]) -> int:
    """Imprime el resumen global. Retorna exit code (0=ok, 1=fallos)."""
    total_casos   = sum(s.total    for s in suites)
    total_pasados = sum(s.pasados  for s in suites)
    total_fallos  = sum(s.fallidos for s in suites)

    print(f"\n{'═' * 60}")
    print(f"{NEGRI}  EVALUACIÓN R3 — RESUMEN GLOBAL{RESET}")
    print(f"{'═' * 60}")

    for s in suites:
        icono = f"{VERDE}✅{RESET}" if s.fallidos == 0 else f"{ROJO}❌{RESET}"
        print(f"  {icono}  {s.nombre:<42} {s.pasados}/{s.total}")

    print(f"{'─' * 60}")

    if total_fallos == 0:
        estado = f"{VERDE}{NEGRI}SISTEMA HABILITADO PARA R7{RESET}"
        exitcode = 0
    else:
        estado = f"{ROJO}{NEGRI}{total_fallos} FALLO(S) — revisar router.py{RESET}"
        exitcode = 1

    print(f"  TOTAL : {NEGRI}{total_pasados}/{total_casos}{RESET}  —  {estado}")
    print(f"{'═' * 60}\n")
    return exitcode


# ─────────────────────────────────────────────────────────────
# Salida JSON (para CI / métricas)
# ─────────────────────────────────────────────────────────────

def salida_json(suites: list[SuiteResult]) -> None:
    data = {
        "r3_eval": [
            {
                "suite": s.nombre,
                "total": s.total,
                "pasados": s.pasados,
                "fallidos": s.fallidos,
                "porcentaje": round(s.porcentaje, 1),
                "fallos": [
                    {
                        "id": c.id,
                        "pregunta": c.pregunta,
                        "carril_esperado": c.carril_esperado,
                        "carril_obtenido": c.carril_obtenido,
                        "memoria_esperada": c.memoria_esperada,
                        "memoria_obtenida": c.memoria_obtenida,
                    }
                    for c in s.casos if not c.ok
                ],
            }
            for s in suites
        ],
        "total_casos": sum(s.total for s in suites),
        "total_pasados": sum(s.pasados for s in suites),
        "habilitado_r7": all(s.fallidos == 0 for s in suites),
    }
    print(json.dumps(data, ensure_ascii=False, indent=2))


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluación formal R3 — routing determinista sin LLM"
    )
    parser.add_argument("--json",      action="store_true", help="Salida en formato JSON")
    parser.add_argument("--verbose",   action="store_true", help="Mostrar cada caso")
    parser.add_argument("--fail-fast", action="store_true", help="Detener al primer fallo")
    args = parser.parse_args()

    fail_fast = args.fail_fast

    suites = [
        evaluar_routing_matrix(fail_fast=fail_fast),
        evaluar_bateria_20(fail_fast=fail_fast),
    ]

    if args.json:
        salida_json(suites)
        return 0 if all(s.fallidos == 0 for s in suites) else 1

    for suite in suites:
        imprimir_suite(suite, verbose=args.verbose)

    return imprimir_resumen(suites)


if __name__ == "__main__":
    sys.exit(main())
