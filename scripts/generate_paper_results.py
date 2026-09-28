"""Build the paper tables from this repository's experiment JSON only."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "results" / "paper"


def _rows(folder: str) -> list[dict]:
    directory = PAPER / folder
    if not directory.exists():
        return []
    rows = []
    for path in sorted(directory.glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        row["_file"] = path.name
        rows.append(row)
    return rows


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _rate(rows: list[dict], key: str) -> str:
    if not rows:
        return "0/0"
    return f"{sum(1 for row in rows if row.get(key))}/{len(rows)}"


def _md_table(headers: list[str], body: list[list[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def main() -> None:
    synthesis = [row for row in _rows("synthesis") if row.get("experiment") == "five_agent_synthesis"]
    single = [row for row in _rows("single_agent") if row.get("experiment") == "single_agent_synthesis"]
    evolution = [row for row in _rows("evolution") if row.get("experiment") == "solver_evolution"]
    fields = [
        "experiment",
        "model",
        "profile",
        "seed",
        "executable",
        "routing",
        "charging",
        "multi_customer",
        "schneider_c5",
        "fully_feasible",
        "feasible",
        "c5_total",
        "vehicles",
        "distance",
        "llm_calls",
        "tokens",
        "prompt_tokens",
        "completion_tokens",
        "solver_hash",
        "wall_s",
        "failure_reason",
        "published_solver",
        "improved",
    ]
    tables = PAPER / "tables"
    _write_csv(tables / "five_agent_runs.csv", synthesis, fields)
    _write_csv(tables / "single_agent_runs.csv", single, fields)
    _write_csv(tables / "evolution_runs.csv", evolution, fields)

    by_model: dict[str, list[dict]] = {}
    for row in synthesis:
        by_model.setdefault(str(row.get("model")), []).append(row)
    comparison = []
    for model, rows in by_model.items():
        comparison.append(
            [
                model,
                len(rows),
                _rate(rows, "executable"),
                _rate(rows, "routing"),
                _rate(rows, "charging"),
                _rate(rows, "multi_customer"),
                _rate(rows, "schneider_c5"),
                _rate(rows, "fully_feasible"),
                sum(int(row.get("llm_calls") or 0) for row in rows),
                sum(int(row.get("tokens") or 0) for row in rows),
            ]
        )
    qwen7 = [row for row in synthesis if "7b" in str(row.get("model")) and "qwen" in str(row.get("model"))]
    qwen14 = [row for row in synthesis if "14b" in str(row.get("model"))]
    single7 = single
    failures = Counter(
        (row.get("failure_reason") or "ok").split(":")[0][:80]
        for row in synthesis + single + evolution
        if row.get("failure_reason")
    )
    evolved = [row for row in evolution if row.get("improved") and row.get("fully_feasible")]
    best = None
    pool = [row for row in synthesis + single + evolution if row.get("fully_feasible") and row.get("vehicles") is not None]
    if pool:
        best = sorted(pool, key=lambda row: (int(row["vehicles"]), float(row["distance"] or 1e18)))[0]

    parts = [
        "# Paper results",
        "",
        "These tables contain only the runs produced by `scripts/run_five_agent.py`, `scripts/run_single_agent.py`, and `scripts/run_evolution.py` in this repository. Historical development runs are not included.",
        "",
        "## 1. Five-agent synthesis by model",
        "",
        _md_table(
            ["Model", "Seeds", "Executable", "Routing", "Charging", "Multi-customer", "Schneider C5 panel", "All C5", "LLM calls", "Tokens"],
            comparison or [["—", 0, "0/0", "0/0", "0/0", "0/0", "0/0", "0/0", 0, 0]],
        ),
        "",
        "## 2. Five-agent Qwen 7B vs single-agent Qwen 7B",
        "",
        _md_table(
            ["System", "Seeds", "Executable", "Routing", "Charging", "Multi-customer", "Schneider C5 panel", "All C5"],
            [
                ["five-agent Qwen 7B", len(qwen7), _rate(qwen7, "executable"), _rate(qwen7, "routing"), _rate(qwen7, "charging"), _rate(qwen7, "multi_customer"), _rate(qwen7, "schneider_c5"), _rate(qwen7, "fully_feasible")],
                ["single-agent Qwen 7B", len(single7), _rate(single7, "executable"), _rate(single7, "routing"), _rate(single7, "charging"), _rate(single7, "multi_customer"), _rate(single7, "schneider_c5"), _rate(single7, "fully_feasible")],
            ],
        ),
        "",
        "## 3. Qwen 7B vs Qwen 14B (five-agent)",
        "",
        _md_table(
            ["Model", "Seeds", "Schneider C5 panel", "All C5", "LLM calls", "Tokens"],
            [
                ["Qwen 7B", len(qwen7), _rate(qwen7, "schneider_c5"), _rate(qwen7, "fully_feasible"), sum(int(r.get("llm_calls") or 0) for r in qwen7), sum(int(r.get("tokens") or 0) for r in qwen7)],
                ["Qwen 14B", len(qwen14), _rate(qwen14, "schneider_c5"), _rate(qwen14, "fully_feasible"), sum(int(r.get("llm_calls") or 0) for r in qwen14), sum(int(r.get("tokens") or 0) for r in qwen14)],
            ],
        ),
        "",
        "## 4. Solver evolution",
        "",
        _md_table(
            ["Seed", "Improved", "All C5", "Vehicles", "Distance", "Calls", "Hash", "Runtime s"],
            [
                [
                    row.get("seed"),
                    row.get("improved"),
                    f"{row.get('feasible')}/{row.get('c5_total')}",
                    row.get("vehicles"),
                    row.get("distance"),
                    row.get("llm_calls"),
                    row.get("solver_hash"),
                    row.get("wall_s"),
                ]
                for row in evolution
            ]
            or [["—", "—", "—", "—", "—", "—", "—", "—"]],
        ),
        "",
        f"Valid improvements kept: {len(evolved)}.",
        "",
        "## 5. Failure categories",
        "",
        _md_table(
            ["Failure", "Count"],
            [[name, count] for name, count in failures.most_common()] or [["none", 0]],
        ),
        "",
        "## Best valid generated solver",
        "",
    ]
    if best is None:
        parts.append("No run produced a solver that is fully feasible on every discovery C5 instance.")
    else:
        parts.append(
            f"- Experiment: `{best.get('experiment')}`\n"
            f"- Model: `{best.get('model')}` seed `{best.get('seed')}`\n"
            f"- Vehicles: `{best.get('vehicles')}` distance `{best.get('distance')}`\n"
            f"- Hash: `{best.get('solver_hash')}`\n"
            f"- File: `{best.get('published_solver')}`"
        )
    parts.append("")
    text = "\n".join(parts)
    (PAPER / "README.md").write_text(text, encoding="utf-8")
    print(f"wrote {PAPER / 'README.md'}")


if __name__ == "__main__":
    main()
