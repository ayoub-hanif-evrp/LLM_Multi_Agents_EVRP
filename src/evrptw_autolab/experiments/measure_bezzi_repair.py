"""Measure Bezzi C101-5 and 10-N10 after the reserved final charge repair."""
from __future__ import annotations

import json
from pathlib import Path

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.bezzi import load_bezzi

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results" / "v2" / "diagnostics" / "bezzi_repair" / "summary.json"


def main() -> None:
    jobs = [
        ("Dataset_A/Instances/C101-5.xml", "C101-5", 7),
        ("Dataset_B/Instances/10-N10.xml", "10-N10", 7),
        ("Dataset_B/Instances/10-N10.xml", "10-N10", 11),
        ("Dataset_B/Instances/10-N10.xml", "10-N10", 22),
    ]
    rows = []
    for rel, name, seed in jobs:
        spec = load_bezzi(ROOT / "dataset" / "Bezzi & Ceselli EVRP-MRT" / rel)
        solution = solve_classical(spec, seed=seed, time_limit_s=12.0, alns_iterations=60)
        report = evaluate(spec, solution)
        fault = "" if report.first_fault is None else report.first_fault.family
        rows.append(
            {
                "instance_id": name,
                "seed": seed,
                "feasible": bool(report.feasible),
                "objective_key": [float(v) for v in report.objective_key],
                "vehicles": report.vehicles,
                "first_fault": fault,
                "completed_within_budget": solution.metadata.get("completed_within_budget"),
                "runtime_s": solution.metadata.get("runtime_s"),
            }
        )
        print(name, seed, rows[-1], flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"rows": rows}, indent=2) + "\n", encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
