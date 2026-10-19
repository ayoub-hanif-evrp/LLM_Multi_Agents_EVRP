"""Profile Schneider discovery instances that are not the RC2 holdout."""
from __future__ import annotations

import json
import time
from pathlib import Path

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "dataset" / "schneider" / "raw_instances"
# Predeclared from the filename before looking at objectives. Not RC2.
CASES = [
    ("c103C15", 15.0, 60),
    ("r102C10", 12.0, 60),
    ("c101_21", 20.0, 40),
]
OUT = ROOT / "results" / "v2" / "diagnostics" / "large_development" / "profile.json"


def main() -> None:
    rows = []
    for instance_id, limit, iterations in CASES:
        path = RAW / f"{instance_id}.txt"
        spec = load_schneider_v2(path)
        started = time.monotonic()
        solution = solve_classical(
            spec, seed=7, time_limit_s=limit, alns_iterations=iterations
        )
        report = evaluate(spec, solution)
        fault = None if report.first_fault is None else report.first_fault.detail
        family = None if report.first_fault is None else report.first_fault.family
        row = {
            "instance_id": instance_id,
            "seed": 7,
            "time_limit_s": limit,
            "alns_iterations": iterations,
            "customers": sum(1 for node in spec.nodes if node.kind == "customer"),
            "feasible": report.feasible,
            "objective_key": list(report.objective_key) if report.feasible else None,
            "vehicles": report.vehicles if report.feasible else None,
            "fault_family": family,
            "fault_detail": fault,
            "completed_within_budget": bool(solution.metadata.get("completed_within_budget")),
            "runtime_s": round(time.monotonic() - started, 3),
            "stage_construction_s": solution.metadata.get("stage_construction_s"),
            "time_to_first_feasible_s": solution.metadata.get("time_to_first_feasible_s"),
            "return_status": solution.metadata.get("return_status"),
        }
        print(row, flush=True)
        rows.append(row)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "protocol": "development_large_profile",
                "note": "Schneider discovery ids only. RC2 held-out ids are not loaded.",
                "rows": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
