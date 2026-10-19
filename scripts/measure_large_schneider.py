"""Full classical solve of Schneider discovery c101_21 after route-local construction."""
from __future__ import annotations

import json
import time
from pathlib import Path

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v2" / "diagnostics" / "large_development" / "c101_21_route_local.json"


def main() -> None:
    spec = load_schneider_v2(ROOT / "dataset" / "schneider" / "raw_instances" / "c101_21.txt")
    started = time.monotonic()
    solution = solve_classical(spec, seed=7, time_limit_s=20.0, alns_iterations=40)
    report = evaluate(spec, solution)
    fault = None if report.first_fault is None else report.first_fault.family
    payload = {
        "instance_id": "c101_21",
        "seed": 7,
        "time_limit_s": 20.0,
        "alns_iterations": 40,
        "construction": solution.metadata.get("construction"),
        "feasible": report.feasible,
        "objective_key": list(report.objective_key) if report.feasible else None,
        "vehicles": report.vehicles if report.feasible else None,
        "distance": report.total_distance if report.feasible else None,
        "fault_family": fault,
        "completed_within_budget": solution.metadata.get("completed_within_budget"),
        "runtime_s": round(time.monotonic() - started, 3),
        "time_to_first_feasible_s": solution.metadata.get("time_to_first_feasible_s"),
        "return_status": solution.metadata.get("return_status"),
        "note": "Development Schneider c101_21 only. Not an RC2 held-out instance. Classical solver.",
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(payload, flush=True)


if __name__ == "__main__":
    main()
