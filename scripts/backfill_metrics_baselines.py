from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

METRICS_FILE = Path("storage") / "logs" / "metrics.jsonl"
BASELINE_ID = "septiembre-1"
START_TS = "2026-09-01T00:00:00"


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def main() -> None:
    if not METRICS_FILE.exists():
        print(f"No existe {METRICS_FILE}")
        return

    start_dt = parse_ts(START_TS)
    if start_dt is None:
        print("Fecha de inicio inválida")
        return

    updated = 0
    total = 0
    lines: list[str] = []

    for line in METRICS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue

        total += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            lines.append(line)
            continue

        ts = parse_ts(row.get("timestamp") or row.get("finished_at") or row.get("end_time"))
        if ts and ts >= start_dt:
            row["baseline_id"] = BASELINE_ID
            row["metric_schema_version"] = row.get("metric_schema_version", 2)
            updated += 1

        lines.append(json.dumps(row, ensure_ascii=False))

    METRICS_FILE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"Backfill completado: {updated} filas actualizadas de {total} analizadas.")


if __name__ == "__main__":
    main()
