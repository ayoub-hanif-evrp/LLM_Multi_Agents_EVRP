"""Longer-budget development gate. One distinct instance per family.

The CI smoke test in ``tests/test_family_regression.py`` only requires a
feasible incumbent on a Schneider micro-instance. This gate uses the
development-panel budgets and fails when a frozen feasible row becomes
infeasible or its lexicographic objective gets worse.

``tc0c10s3cf1`` is omitted. It duplicates ``tc0c10s2cf1`` and is not a
second independent test.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.baselines.classical_pilot import PilotInstance, development_panel

ROOT = Path(__file__).resolve().parents[3]
BASELINE_PATH = ROOT / "results" / "v2" / "diagnostics" / "family_development_gate" / "baseline.json"
OBJECTIVE_TOLERANCE = 1e-6
GATE_SEED = 7


def gate_panel(root: Path | None = None) -> list[PilotInstance]:
    """First development instance of each family, in panel order."""
    chosen: list[PilotInstance] = []
    seen: set[str] = set()
    for item in development_panel(root):
        if item.family in seen:
            continue
        seen.add(item.family)
        chosen.append(item)
    return chosen


def measure_gate(root: Path | None = None, *, seed: int = GATE_SEED) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in gate_panel(root):
        spec = item.loader(item.path)
        solution = solve_classical(
            spec,
            seed=seed,
            time_limit_s=item.time_limit_s,
            alns_iterations=item.alns_iterations,
        )
        report = evaluate(spec, solution)
        fault = None if report.first_fault is None else report.first_fault.family
        rows.append(
            {
                "family": item.family,
                "instance_id": item.instance_id,
                "seed": int(seed),
                "time_limit_s": float(item.time_limit_s),
                "alns_iterations": int(item.alns_iterations),
                "feasible": bool(report.feasible),
                "objective": report.objective,
                "objective_key": [float(v) for v in report.objective_key],
                "vehicles": int(report.vehicles),
                "distance": float(report.total_distance),
                "duration": float(report.total_duration),
                "first_fault_family": fault,
                "solution_feasible": solution.metadata.get("solution_feasible"),
                "completed_within_budget": solution.metadata.get("completed_within_budget"),
            }
        )
    return rows


def objective_regressed(frozen_key: list[float], measured_key: list[float]) -> bool:
    """True when the measured lexicographic key is strictly worse."""
    if len(frozen_key) != len(measured_key):
        return True
    for measured, frozen in zip(measured_key, frozen_key, strict=True):
        if measured > frozen + OBJECTIVE_TOLERANCE:
            return True
        if frozen > measured + OBJECTIVE_TOLERANCE:
            return False
    return False


def judge_gate(measured: list[dict[str, Any]], frozen_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Feasibility loss and a worse feasible objective are regressions.

    An infeasible nominal objective is not a win and is not an objective
    regression. Becoming feasible is allowed.
    """
    frozen_by_id = {str(row["instance_id"]): row for row in frozen_rows}
    failures: list[dict[str, Any]] = []
    for row in measured:
        base = frozen_by_id.get(str(row["instance_id"]))
        if base is None:
            failures.append({"instance_id": row["instance_id"], "reason": "missing_frozen_row"})
            continue
        if bool(base["feasible"]) and not bool(row["feasible"]):
            failures.append(
                {
                    "instance_id": row["instance_id"],
                    "reason": "feasibility_regression",
                    "frozen_key": base.get("objective_key"),
                    "measured_key": row.get("objective_key"),
                    "first_fault_family": row.get("first_fault_family"),
                }
            )
            continue
        if bool(base["feasible"]) and bool(row["feasible"]):
            frozen_key = [float(v) for v in base["objective_key"]]
            measured_key = [float(v) for v in row["objective_key"]]
            if objective_regressed(frozen_key, measured_key):
                failures.append(
                    {
                        "instance_id": row["instance_id"],
                        "reason": "objective_regression",
                        "frozen_key": frozen_key,
                        "measured_key": measured_key,
                    }
                )
        if row.get("solution_feasible") != row["feasible"]:
            failures.append(
                {
                    "instance_id": row["instance_id"],
                    "reason": "feasibility_flag_mismatch",
                }
            )
    return {"ok": not failures, "failures": failures, "n_rows": len(measured)}


def load_baseline(path: Path | None = None) -> dict[str, Any]:
    target = path or BASELINE_PATH
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("development gate baseline must be a JSON object")
    return cast(dict[str, Any], payload)


def write_baseline(rows: list[dict[str, Any]], path: Path | None = None) -> Path:
    target = path or BASELINE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "description": (
            "Seed 7 development gate under the wall-clock solver. One instance per family. "
            "Montoya tc0c10s3cf1 is excluded because it duplicates tc0c10s2cf1. "
            "Partial charge targets are a final guarded polish; they are not applied inside ALNS. "
            "Hiermann c101_21 did not return a feasible incumbent inside its 15 second budget. "
            "A later run regresses when a feasible row becomes infeasible or its "
            "lexicographic objective gets worse. A better feasible objective is allowed."
        ),
        "seed": GATE_SEED,
        "rows": rows,
    }
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target
