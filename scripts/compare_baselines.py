from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

METRICS_FILE = Path("storage") / "logs" / "metrics.jsonl"
BASELINES_FILE = Path("data") / "metrics_baselines.json"


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def load_baselines(path: Path) -> list[dict]:
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []

    return data.get("baselines", [])


def assign_baseline(row: dict, baselines: list[dict]) -> str | None:
    row_ts = parse_ts(row.get("timestamp") or row.get("finished_at") or row.get("end_time"))
    if row_ts is None:
        return None

    for baseline in baselines:
        start_ts = parse_ts(baseline.get("started_at"))
        end_ts = parse_ts(baseline.get("ended_at"))

        if start_ts is None:
            continue

        if row_ts < start_ts:
            continue

        if end_ts is not None and row_ts > end_ts:
            continue

        return baseline.get("id")

    return None


def main() -> None:
    metrics_rows = load_jsonl(METRICS_FILE)
    baselines = load_baselines(BASELINES_FILE)

    if not metrics_rows:
        print("No se encontraron métricas en storage/logs/metrics.jsonl")
        return

    if not baselines:
        print("No se encontraron baselines en data/metrics_baselines.json")
        return

    df = pd.DataFrame(metrics_rows)

    # Normalizar columnas clave
    for col in ["llm_ms", "retrieval_ms", "fidelity_ms", "total_ms", "tokens_est"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["timestamp"] = pd.to_datetime(df.get("timestamp", pd.Series([None] * len(df))), errors="coerce")
    df["assigned_baseline"] = df.apply(lambda row: assign_baseline(row, baselines), axis=1)

    # Construir resumen por baseline
    summary_rows = []
    baseline_names = [baseline.get("id") for baseline in baselines if baseline.get("id")]

    for baseline_id in baseline_names:
        rows = df[df["assigned_baseline"] == baseline_id]

        if rows.empty:
            summary_rows.append(
                {
                    "baseline_id": baseline_id,
                    "turnos": 0,
                    "avg_total_s": 0,
                    "avg_llm_s": 0,
                    "avg_retrieval_s": 0,
                    "avg_fidelity_s": 0,
                    "tokens_est": 0,
                }
            )
            continue

        summary_rows.append(
            {
                "baseline_id": baseline_id,
                "turnos": len(rows),
                "avg_total_s": rows["total_ms"].mean() / 1000,
                "avg_llm_s": rows["llm_ms"].mean() / 1000,
                "avg_retrieval_s": rows["retrieval_ms"].mean() / 1000,
                "avg_fidelity_s": rows["fidelity_ms"].mean() / 1000,
                "tokens_est": int(rows["tokens_est"].sum()),
            }
        )

    summary = pd.DataFrame(summary_rows)

    print("📊 Tabla resumen de métricas por baseline:")
    print(summary.to_string(index=False))

    # Gráfico 1: tiempos promedio
    melt = summary.melt(
        id_vars="baseline_id",
        value_vars=["avg_total_s", "avg_llm_s", "avg_retrieval_s", "avg_fidelity_s"],
        var_name="metric",
        value_name="seconds",
    )

    plt.figure(figsize=(11, 6))
    sns.barplot(data=melt, x="baseline_id", y="seconds", hue="metric")
    plt.title("Comparación de tiempos promedio por baseline")
    plt.ylabel("Segundos")
    plt.xticks(rotation=15)
    plt.tight_layout()
    plt.show()

    # Gráfico 2: tokens consumidos
    plt.figure(figsize=(8, 5))
    sns.barplot(data=summary, x="baseline_id", y="tokens_est")
    plt.title("Tokens consumidos por baseline")
    plt.ylabel("Tokens totales")
    plt.xticks(rotation=15)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
