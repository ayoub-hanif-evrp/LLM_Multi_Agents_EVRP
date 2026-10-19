"""Re-evaluate the seed-7 selected bundles on seeds 11 and 22.

This does not change the selection rule. The classical side is the already
measured development panel.
"""
from __future__ import annotations

import json
from pathlib import Path

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.components.expressions import wrap_expression
from evrptw_autolab.components.interfaces import DEFAULT_SOURCES
from evrptw_autolab.components.loader import load_bundle
from evrptw_autolab.experiments.family_gate import gate_panel
from evrptw_autolab.experiments.policy_sensitivity import paired_feasible_outcome

ROOT = Path(__file__).resolve().parents[3]
PILOT = ROOT / "results" / "v2" / "campaigns" / "matched_qwen_20261018T205937Z" / "matched_pilot.json"
PANEL = ROOT / "results" / "v2" / "diagnostics" / "family_development_gate" / "expanded_panel.json"
OUT = ROOT / "results" / "v2" / "campaigns" / "matched_qwen_20261018T205937Z" / "confirmation_seeds.json"


def main() -> None:
    src = json.loads(PILOT.read_text(encoding="utf-8"))
    base_rows = json.loads(PANEL.read_text(encoding="utf-8"))["independent_rows"]
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
    panel = gate_panel()
    out_rows = []
    for seed in (11, 22):
        for candidate_id, (sources, schema) in bundles.items():
            bundle, errors = load_bundle(
                sources, {key: "confirmation" for key in sources}, feature_schema=schema
            )
            for item in panel:
                spec = item.loader(item.path)
                solution = solve_classical(
                    spec,
                    seed=seed,
                    time_limit_s=item.time_limit_s,
                    alns_iterations=item.alns_iterations,
                    policy=bundle,
                )
                report = evaluate(spec, solution)
                frozen = next(
                    row
                    for row in base_rows
                    if row["instance_id"] == item.instance_id and int(row["seed"]) == seed
                )
                outcome = paired_feasible_outcome(
                    bool(frozen["feasible"]),
                    tuple(float(value) for value in frozen["objective_key"]),
                    bool(report.feasible),
                    tuple(float(value) for value in report.objective_key),
                )
                out_rows.append(
                    {
                        "candidate_id": candidate_id,
                        "family": item.family,
                        "instance_id": item.instance_id,
                        "seed": seed,
                        "feasible": bool(report.feasible),
                        "objective_key": [float(value) for value in report.objective_key],
                        "vehicles": report.vehicles,
                        "baseline_feasible": frozen["feasible"],
                        "baseline_key": frozen["objective_key"],
                        "paired_outcome": outcome,
                        "completed_within_budget": solution.metadata.get("completed_within_budget"),
                        "load_errors": errors,
                    }
                )
                print(
                    candidate_id,
                    item.instance_id,
                    seed,
                    outcome,
                    out_rows[-1]["objective_key"],
                    "budget",
                    out_rows[-1]["completed_within_budget"],
                    flush=True,
                )
    OUT.write_text(
        json.dumps(
            {
                "seeds": [11, 22],
                "rows": out_rows,
                "note": (
                    "Compared with the frozen classical panel at commit 27278a1. "
                    "The selection rule was not changed after seeing these seeds."
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("wrote", OUT)


if __name__ == "__main__":
    main()
