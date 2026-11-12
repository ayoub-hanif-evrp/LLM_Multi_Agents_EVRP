"""Freeze a small Schneider + Hiermann classical baseline. Zero LLM calls."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.hiermann import load_hiermann
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2

ROOT = Path(__file__).resolve().parents[3]

PANEL = (
    ("schneider", "c101C5", ROOT / "dataset" / "schneider" / "raw_instances" / "c101C5.txt", 5.0, 20, load_schneider_v2),
    ("schneider", "r105C5", ROOT / "dataset" / "schneider" / "raw_instances" / "r105C5.txt", 5.0, 20, load_schneider_v2),
    ("hiermann", "c101_21", ROOT / "dataset" / "hiermann-et-al-2017-set-1" / "c101_21.txt", 8.0, 10, load_hiermann),
)
SEEDS = (7, 11)


def freeze_panel(*, destination: Path | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for family, instance_id, path, time_limit, iterations, loader in PANEL:
        if not path.exists():
            raise FileNotFoundError(path)
        spec = loader(path)
        for seed in SEEDS:
            solution = solve_classical(
                spec,
                seed=seed,
                time_limit_s=time_limit,
                alns_iterations=iterations,
                hard_timeout=True,
                experiment_partition="development",
                policy=None,
            )
            report = evaluate(spec, solution)
            rows.append(
                {
                    "family": family,
                    "instance_id": instance_id,
                    "seed": seed,
                    "time_limit_s": time_limit,
                    "alns_iterations": iterations,
                    "feasible": bool(report.feasible),
                    "objective_key": [float(value) for value in report.objective_key],
                    "vehicles": report.vehicles,
                    "runtime_s": float(solution.metadata.get("runtime_s") or 0.0),
                    "policy_executed": bool(solution.metadata.get("policy_executed")),
                    "method_attribution": solution.metadata.get("method_attribution"),
                    "changed_decisions": int(solution.metadata.get("changed_decisions") or 0),
                    "llm_calls": 0,
                }
            )
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "partition": "development",
        "llm_calls": 0,
        "rows": rows,
    }
    out = destination or (ROOT / "results" / "cipher" / "classical" / "development_panel.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
