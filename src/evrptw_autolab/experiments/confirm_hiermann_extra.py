"""Paired check of the seed-7 bundles on the other measured Hiermann instances."""
from __future__ import annotations

import json
from pathlib import Path

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.components.expressions import wrap_expression
from evrptw_autolab.components.interfaces import DEFAULT_SOURCES
from evrptw_autolab.components.loader import load_bundle
from evrptw_autolab.experiments.policy_sensitivity import paired_feasible_outcome
from evrptw_autolab.problem.datasets.hiermann import load_hiermann

ROOT = Path(__file__).resolve().parents[3]
PILOT = ROOT / "results" / "v2" / "campaigns" / "matched_qwen_20261018T205937Z" / "matched_pilot.json"
BASE = ROOT / "results" / "v2" / "diagnostics" / "hiermann_init" / "summary.json"
OUT = ROOT / "results" / "v2" / "campaigns" / "matched_qwen_20261018T205937Z" / "hiermann_extra.json"
INSTANCES = ("r101_21", "c201_21")


def main() -> None:
    src = json.loads(PILOT.read_text(encoding="utf-8"))
    frozen = {
        (row["instance_id"], int(row["seed"])): row
        for row in json.loads(BASE.read_text(encoding="utf-8"))["rows"]
        if row["instance_id"] in INSTANCES
    }
    five = next(row for row in src["rows"] if row["candidate_id"] == "five_1")
    rand = next(row for row in src["rows"] if row["candidate_id"] == "random_0")
    bundles = {
        "five_1": (
            {item["component"]: item["source"] for item in five["attribution"]},
            five["feature_schema"],
        ),
        "random_0": (
            {
                **DEFAULT_SOURCES,
                "removal_priority": wrap_expression("removal_priority", rand["expression"]),
            },
            "2026-10-18.v1",
        ),
    }
    rows = []
    for name in INSTANCES:
        spec = load_hiermann(ROOT / "dataset" / "hiermann-et-al-2017-set-1" / f"{name}.txt")
        for seed in (7, 11, 22):
            base = frozen[(name, seed)]
            for candidate_id, (sources, schema) in bundles.items():
                bundle, errors = load_bundle(
                    sources, {key: "confirmation" for key in sources}, feature_schema=schema
                )
                solution = solve_classical(
                    spec, seed=seed, time_limit_s=15.0, alns_iterations=40, policy=bundle
                )
                report = evaluate(spec, solution)
                outcome = paired_feasible_outcome(
                    bool(base["feasible"]),
                    (float(base["objective"]),),
                    bool(report.feasible),
                    tuple(float(value) for value in report.objective_key),
                )
                rows.append(
                    {
                        "candidate_id": candidate_id,
                        "instance_id": name,
                        "seed": seed,
                        "feasible": bool(report.feasible),
                        "objective_key": [float(value) for value in report.objective_key],
                        "vehicles": report.vehicles,
                        "baseline_objective": base["objective"],
                        "baseline_vehicles": base["vehicles"],
                        "paired_outcome": outcome,
                        "completed_within_budget": solution.metadata.get("completed_within_budget"),
                        "load_errors": errors,
                    }
                )
                print(candidate_id, name, seed, outcome, rows[-1]["objective_key"], flush=True)
    OUT.write_text(json.dumps({"rows": rows}, indent=2) + "\n", encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
