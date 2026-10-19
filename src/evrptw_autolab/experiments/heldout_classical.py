"""Classical solver on the predefined Schneider held-out split.

Budgets are fixed by instance size before any result is read. The split is
the existing RC2 held-out list. No learned policy is evaluated here.
"""
from __future__ import annotations

import json
from pathlib import Path

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2

ROOT = Path(__file__).resolve().parents[3]
SPLIT = ROOT / "results" / "manifests" / "split.json"
OUT = ROOT / "results" / "v2" / "paper" / "heldout_classical.json"


def _budget(instance_id: str) -> tuple[float, int]:
    if instance_id.endswith("C5"):
        return 8.0, 80
    if instance_id.endswith("C10"):
        return 12.0, 60
    if instance_id.endswith("C15"):
        return 15.0, 60
    return 20.0, 40


def main() -> None:
    held = json.loads(SPLIT.read_text(encoding="utf-8"))["heldout_ids"]
    rows = []
    for instance_id in held:
        path = ROOT / "dataset" / "schneider" / "raw_instances" / f"{instance_id}.txt"
        limit, iterations = _budget(instance_id)
        spec = load_schneider_v2(path)
        for seed in (7, 11, 22):
            solution = solve_classical(
                spec, seed=seed, time_limit_s=limit, alns_iterations=iterations
            )
            report = evaluate(spec, solution)
            fault = "" if report.first_fault is None else report.first_fault.family
            rows.append(
                {
                    "family": "schneider",
                    "instance_id": instance_id,
                    "seed": seed,
                    "time_limit_s": limit,
                    "alns_iterations": iterations,
                    "feasible": bool(report.feasible),
                    "objective_key": [float(v) for v in report.objective_key],
                    "vehicles": report.vehicles,
                    "distance": report.total_distance,
                    "first_fault": fault,
                    "completed_within_budget": solution.metadata.get("completed_within_budget"),
                    "runtime_s": solution.metadata.get("runtime_s"),
                }
            )
            print(instance_id, seed, rows[-1]["feasible"], rows[-1]["objective_key"], flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    feasible = sum(1 for row in rows if row["feasible"])
    OUT.write_text(
        json.dumps(
            {
                "protocol": "predeclared_schneider_rc2_heldout",
                "policy": "classical_default",
                "seeds": [7, 11, 22],
                "n": len(rows),
                "feasible": feasible,
                "rows": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("wrote", OUT, feasible, "/", len(rows))


if __name__ == "__main__":
    main()
