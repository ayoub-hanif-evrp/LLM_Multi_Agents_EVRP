"""Before/after table for partial charging, route merge, and adaptive destroy.

Seed 7 on the five-family gate accepted every ablation because each one improved
Montoya and tied the other families. Seeds 11 and 22 then rejected turning merge
off and freezing destroy weights: both were worse than the classical baseline.
Turning partial-charge rewrites off during search improved Montoya at seeds 7, 11,
and 22. That is the retained change. A final guarded polish still runs, and a
full recharge on the seed-7 routes was longer than the partial targets
(33.318 versus 32.115). The summary file is the seed-7 table. Confirmation is
``montoya_confirmation.json``. Solver defaults are not switched by this script.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.experiments.bundle_selection import RULE, conservative_decision
from evrptw_autolab.experiments.family_gate import GATE_SEED, gate_panel
from evrptw_autolab.experiments.policy_sensitivity import paired_feasible_outcome

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "results" / "v2" / "diagnostics" / "backbone_ablation"

VARIANTS: dict[str, dict[str, bool]] = {
    "baseline": {},
    "no_partial_charges": {"optimize_partial_charges": False},
    "no_route_merge": {"merge_routes": False},
    "uniform_destroy": {"adaptive_destroy": False},
}


def _solve(item: Any, seed: int, flags: dict[str, bool]) -> dict[str, Any]:
    spec = item.loader(item.path)
    solution = solve_classical(
        spec,
        seed=seed,
        time_limit_s=item.time_limit_s,
        alns_iterations=item.alns_iterations,
        optimize_partial_charges=flags.get("optimize_partial_charges", True),
        merge_routes=flags.get("merge_routes", True),
        adaptive_destroy=flags.get("adaptive_destroy", True),
    )
    report = evaluate(spec, solution)
    return {
        "family": item.family,
        "instance_id": item.instance_id,
        "seed": int(seed),
        "feasible": bool(report.feasible),
        "objective_key": [float(v) for v in report.objective_key],
        "objective": report.objective,
        "vehicles": int(report.vehicles),
        "distance": float(report.total_distance),
        "duration": float(report.total_duration),
        "first_fault_family": None if report.first_fault is None else report.first_fault.family,
        "completed_within_budget": solution.metadata.get("completed_within_budget"),
    }


def run_ablation(root: Path | None = None, *, seed: int = GATE_SEED) -> dict[str, Any]:
    panel = gate_panel(root)
    measured: dict[str, list[dict[str, Any]]] = {}
    for name, flags in VARIANTS.items():
        measured[name] = [_solve(item, seed, flags) for item in panel]
    baseline = measured["baseline"]
    decisions: dict[str, Any] = {}
    for name, rows in measured.items():
        if name == "baseline":
            continue
        pairs = []
        for base, cand in zip(baseline, rows, strict=True):
            outcome = paired_feasible_outcome(
                bool(base["feasible"]),
                tuple(float(v) for v in base["objective_key"]),
                bool(cand["feasible"]),
                tuple(float(v) for v in cand["objective_key"]),
            )
            pairs.append(
                {
                    "family": base["family"],
                    "instance_id": base["instance_id"],
                    "seed": seed,
                    "baseline_feasible": bool(base["feasible"]),
                    "candidate_feasible": bool(cand["feasible"]),
                    "baseline_key": base["objective_key"],
                    "candidate_key": cand["objective_key"],
                    "paired_outcome": outcome,
                }
            )
        decisions[name] = {**conservative_decision(pairs), "pairs": pairs}
    accepted = [name for name, decision in decisions.items() if decision["accepted"]]
    return {
        "rule": RULE,
        "seed": seed,
        "note": (
            "One instance per family. Montoya tc0c10s3cf1 is not included because it "
            "duplicates tc0c10s2cf1. Solver defaults stay at baseline unless a variant "
            "is accepted here and then confirmed on an independent seed."
        ),
        "variants": measured,
        "decisions": decisions,
        "accepted_variants": accepted,
        "adopted_variant": "baseline",
    }


def write_ablation(root: Path | None = None, *, seed: int = GATE_SEED) -> Path:
    payload = run_ablation(root, seed=seed)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "summary.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
