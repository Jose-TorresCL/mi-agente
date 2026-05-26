#!/usr/bin/env python3
"""Audit script mejorado — verifica consistencia entre código y docs.

Arreglos vs versión anterior:
- ✅ Encoding UTF-8 explícito en todos los Path.read_text()
- ✅ Regex robusto para VALID_LANES
- ✅ Detección inteligente de documentación incompleta
- ✅ Reporte visual en lugar de solo pasar/fallar
"""

import re
from pathlib import Path
from collections import defaultdict

# Usar encoding UTF-8 explícitamente para Windows
ENCODING = "utf-8"


def read_file_safe(path: str) -> str:
    """Lee archivo con encoding UTF-8 seguro."""
    try:
        return Path(path).read_text(encoding=ENCODING)
    except UnicodeDecodeError:
        print(f"⚠️  Error de encoding en {path}, intentando con latin-1...")
        return Path(path).read_text(encoding="latin-1")
    except FileNotFoundError:
        print(f"❌ Archivo no encontrado: {path}")
        return ""


def extract_valid_lanes() -> set[str]:
    """Extrae VALID_LANES de router.py."""
    router_code = read_file_safe("app/router.py")
    
    # Buscar el set VALID_LANES
    match = re.search(r'VALID_LANES\s*=\s*\{([^}]+)\}', router_code, re.DOTALL)
    if not match:
        print("❌ No se encontró VALID_LANES en router.py")
        return set()
    
    lanes_text = match.group(1)
    # Extraer todos los strings entre comillas
    lanes = set(re.findall(r'"([^"]+)"', lanes_text))
    return lanes


def extract_tools() -> set[str]:
    """Extrae todas las funciones tool_* de tools.py."""
    tools_code = read_file_safe("app/tools.py")
    
    # Buscar definiciones def tool_*
    tool_defs = set(re.findall(r'def\s+(tool_\w+)', tools_code))
    return tool_defs


def extract_modules() -> set[str]:
    """Extrae todos los módulos .py de app/."""
    app_dir = Path("app")
    if not app_dir.exists():
        print(f"❌ Directorio {app_dir} no encontrado")
        return set()
    
    modules = set(f.stem for f in app_dir.glob("*.py") if f.name != "__pycache__")
    return modules


def check_documentation_in_readme(items: set[str], item_type: str) -> dict:
    """Verifica qué items están mencionados en README."""
    readme = read_file_safe("README.md")
    
    documented = {}
    for item in sorted(items):
        # Buscar el item en README (entre backticks para código)
        if f"`{item}`" in readme:
            documented[item] = "✅ Documentado"
        elif item in readme:
            documented[item] = "⚠️  Mencionado pero sin backticks"
        else:
            documented[item] = "❌ NO DOCUMENTADO"
    
    return documented


def audit_routers():
    """Auditoría de carriles del router."""
    print("\n" + "="*60)
    print("🛣️  AUDITORÍA: CARRILES DEL ROUTER (16 esperados)")
    print("="*60)
    
    lanes = extract_valid_lanes()
    if not lanes:
        return False
    
    print(f"\n✅ Encontrados {len(lanes)} carriles en router.py:\n")
    
    # Agrupar por tipo
    tool_lanes = sorted([l for l in lanes if l.startswith("tool_")])
    memory_lanes = sorted([l for l in lanes if l.startswith("memory")])
    special_lanes = sorted([l for l in lanes if l not in tool_lanes and l not in memory_lanes])
    
    if tool_lanes:
        print("  🔧 Herramientas:")
        for lane in tool_lanes:
            print(f"     - {lane}")
    
    if memory_lanes:
        print("\n  💾 Memoria:")
        for lane in memory_lanes:
            print(f"     - {lane}")
    
    if special_lanes:
        print("\n  ⚡ Especiales:")
        for lane in special_lanes:
            print(f"     - {lane}")
    
    # Verificar documentación en README
    print("\n📄 Verificando documentación en README.md:\n")
    documented = check_documentation_in_readme(lanes, "carriles")
    
    status_count = defaultdict(int)
    for lane, status in documented.items():
        status_count[status] += 1
        if "NO" in status:
            print(f"  {status}  {lane}")
    
    print("\n📊 Resumen:")
    for status, count in sorted(status_count.items()):
        print(f"  {status}: {count}")
    
    missing_count = status_count["❌ NO DOCUMENTADO"]
    return missing_count == 0


def audit_tools():
    """Auditoría de herramientas."""
    print("\n" + "="*60)
    print("🔧 AUDITORÍA: HERRAMIENTAS DISPONIBLES")
    print("="*60)
    
    tools = extract_tools()
    if not tools:
        print("❌ No se encontraron herramientas en tools.py")
        return False
    
    print(f"\n✅ Encontradas {len(tools)} herramientas en tools.py:\n")
    
    for tool in sorted(tools):
        print(f"  • {tool}")
    
    # Verificar documentación en README
    print("\n📄 Verificando documentación en README.md:\n")
    documented = check_documentation_in_readme(tools, "herramientas")
    
    status_count = defaultdict(int)
    for tool, status in documented.items():
        status_count[status] += 1
        if "NO" in status:
            print(f"  {status}  {tool}")
    
    print("\n📊 Resumen:")
    for status, count in sorted(status_count.items()):
        print(f"  {status}: {count}")
    
    missing_count = status_count["❌ NO DOCUMENTADO"]
    return missing_count == 0


def audit_modules():
    """Auditoría de módulos."""
    print("\n" + "="*60)
    print("📦 AUDITORÍA: MÓDULOS DE app/")
    print("="*60)
    
    modules = extract_modules()
    if not modules:
        return False
    
    print(f"\n✅ Encontrados {len(modules)} módulos en app/:\n")
    
    for mod in sorted(modules):
        print(f"  • {mod}.py")
    
    # Verificar documentación en README
    print("\n📄 Verificando documentación en README.md:\n")
    documented = check_documentation_in_readme(modules, "módulos")
    
    status_count = defaultdict(int)
    for mod, status in documented.items():
        status_count[status] += 1
        if "NO" in status:
            print(f"  {status}  {mod}.py")
    
    print("\n📊 Resumen:")
    for status, count in sorted(status_count.items()):
        print(f"  {status}: {count}")
    
    missing_count = status_count["❌ NO DOCUMENTADO"]
    return missing_count == 0


def main():
    """Ejecuta todas las auditorías."""
    print("\n🔍 AUDITORÍA COMPLETA DE DOCUMENTACIÓN")
    print("=" * 60)
    print(f"Encoding: {ENCODING}")
    print(f"Directorio: {Path.cwd()}")
    
    results = {
        "Carriles del router": audit_routers(),
        "Herramientas": audit_tools(),
        "Módulos": audit_modules(),
    }
    
    # Resumen final
    print("\n" + "="*60)
    print("📋 RESUMEN FINAL")
    print("="*60)
    
    passed = sum(results.values())
    total = len(results)
    pct = (passed / total) * 100
    
    for section, result in results.items():
        status = "✅ PASS" if result else "⚠️  FALTA"
        print(f"  {status}  {section}")
    
    print(f"\n{passed}/{total} auditorías sin gaps ({pct:.0f}%)")
    
    if passed < total:
        print("\n⚠️  RECOMENDACIÓN: Actualizar README.md con elementos faltantes")
        print("   Ver arriba qué está marcado como 'NO DOCUMENTADO'")
    else:
        print("\n✅ ¡Excelente! Documentación coherente con código")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)