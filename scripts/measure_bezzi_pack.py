"""Paired development check after the Bezzi fleet packer. Does not overwrite old runs."""
from __future__ import annotations

import json
import time
from pathlib import Path

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.bezzi import load_bezzi

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "dataset" / "Bezzi & Ceselli EVRP-MRT"
CASES = [
    ("C101-5", BASE / "Dataset_A" / "Instances" / "C101-5.xml", [7]),
    ("R105-5", BASE / "Dataset_A" / "Instances" / "R105-5.xml", [7]),
    ("10-N10", BASE / "Dataset_B" / "Instances" / "10-N10.xml", [7, 11, 22]),
]
OUT = ROOT / "results" / "v2" / "diagnostics" / "bezzi_pack" / "summary.json"


def main() -> None:
    rows = []
    started = time.monotonic()
    for instance_id, path, seeds in CASES:
        spec = load_bezzi(path)
        for seed in seeds:
            t0 = time.monotonic()
            solution = solve_classical(spec, seed=seed, time_limit_s=12.0, alns_iterations=60)
            report = evaluate(spec, solution)
            row = {
                "instance_id": instance_id,
                "seed": seed,
                "feasible": report.feasible,
                "objective_key": list(report.objective_key),
                "vehicles": report.vehicles,
                "fault": None if report.first_fault is None else report.first_fault.detail,
                "completed_within_budget": bool(solution.metadata.get("completed_within_budget")),
                "runtime_s": round(time.monotonic() - t0, 3),
                "bezzi_pack": bool(solution.metadata.get("bezzi_pack")),
            }
            print(row, flush=True)
            rows.append(row)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"rows": rows, "wall_s": round(time.monotonic() - started, 3)}, indent=2),
        encoding="utf-8",
    )
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
