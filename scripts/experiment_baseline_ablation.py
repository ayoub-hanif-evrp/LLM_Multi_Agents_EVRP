"""B0–B4 baseline ablation: total-route vs marginal vs fleet-aware vs handcrafted vs LLM control.

Paired against B0 (legacy classical total-route repair). Trusted native evaluator only.
Screened local feasibility with battery debt is NOT treated as final feasibility.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate, is_better
from evrptw_autolab.discovery.controller import operator_fingerprint
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "cipher" / "research" / "baseline_ablation_b0b4.json"
RAW = ROOT / "dataset" / "schneider" / "raw_instances"

SEEDS = (7, 11, 22)
# Expanded Schneider panel: prior sprint instances + one extra C/R/RC each.
CASES = (
    ("c101C5", RAW / "c101C5.txt", 5.0, 20),
    ("c101_21", RAW / "c101_21.txt", 10.0, 24),
    ("c103C5", RAW / "c103C5.txt", 5.0, 20),
    ("r104C5", RAW / "r104C5.txt", 5.0, 20),
    ("rc105C5", RAW / "rc105C5.txt", 5.0, 20),
)


def _op(scoring: str, *, operator_id: str, source: str) -> OperatorSpec:
    operator = OperatorSpec(
        operator_id=operator_id,
        version="1",
        source_agent=source,
        description=scoring,
        operator_family="repair",
        implementation_reference="repair_greedy",
        required_capabilities=["time_windows"],
        candidate_scoring_policy=scoring,
        applicability_rule="1",
        mine_counterexamples=False,
        fallback_operator="classical_default",
    )
    return operator.model_copy(update={"source_hash": operator_fingerprint(operator)})


def _outcome(baseline, candidate) -> str:
    if baseline.feasible and not candidate.feasible:
        return "feasibility_regression"
    if is_better(candidate, baseline):
        return "improved"
    if is_better(baseline, candidate):
        return "objective_regression"
    return "tie"


def _gate(outcomes: list[str]) -> str:
    wins = outcomes.count("improved")
    losses = outcomes.count("objective_regression") + outcomes.count("feasibility_regression")
    if wins > 0 and losses == 0:
        return "beneficial"
    if wins > 0 and losses > 0:
        return "mixed"
    if losses > 0 and wins == 0:
        if "feasibility_regression" in outcomes:
            return "feasibility_regression"
        return "objective_regression"
    return "tie"


def main() -> None:
    arms: dict[str, dict] = {
        "B0": {
            "repair_scoring_mode": "total_route_distance",
            "policy": None,
            "note": "Legacy classical: minimize post-insertion total route distance",
        },
        "B1": {
            "repair_scoring_mode": "marginal_delta_distance",
            "policy": None,
            "note": "Corrected classical: minimize marginal delta_distance",
        },
        "B2": {
            "repair_scoring_mode": "marginal_fleet_aware",
            "policy": None,
            "note": "B1 + light consolidation bias (prefer busier routes)",
        },
        "B3": {
            "repair_scoring_mode": "total_route_distance",
            "policy": _op("delta_distance", operator_id="handcrafted_delta", source="handcrafted"),
            "note": "Handcrafted delta_distance OperatorSpec on B0 backbone",
        },
        "B4": {
            "repair_scoring_mode": "total_route_distance",
            "policy": _op("battery_margin", operator_id="llm_battery_margin", source="llm_negative_control"),
            "note": "LLM battery_margin negative control on B0 backbone",
        },
    }

    # Run B0 first so every other arm can pair against the same baseline solutions.
    baseline_cache: dict[tuple[str, int], object] = {}
    rows: list[dict] = []

    for arm_name, cfg in arms.items():
        for instance_id, path, limit, iters in CASES:
            if not path.exists():
                print("skip missing", instance_id, flush=True)
                continue
            spec = load_schneider_v2(path)
            for seed in SEEDS:
                sol = solve_classical(
                    spec,
                    seed=seed,
                    time_limit_s=limit,
                    alns_iterations=iters,
                    hard_timeout=False,
                    experiment_partition="development",
                    policy=cfg["policy"],
                    repair_scoring_mode=cfg["repair_scoring_mode"],
                )
                report = evaluate(spec, sol)
                if arm_name == "B0":
                    baseline_cache[(instance_id, seed)] = (sol, report)
                b0_sol, b0_report = baseline_cache[(instance_id, seed)]
                outcome = "tie" if arm_name == "B0" else _outcome(b0_report, report)
                row = {
                    "arm": arm_name,
                    "family": "schneider",
                    "instance_id": instance_id,
                    "seed": seed,
                    "repair_scoring_mode": cfg["repair_scoring_mode"],
                    "policy": None
                    if cfg["policy"] is None
                    else {
                        "operator_id": cfg["policy"].operator_id,
                        "candidate_scoring_policy": cfg["policy"].candidate_scoring_policy,
                    },
                    "outcome_vs_b0": outcome,
                    "feasible": bool(report.feasible),
                    "objective_key": [float(v) for v in report.objective_key],
                    "vehicles": int(report.vehicles),
                    "total_distance": float(report.total_distance),
                    "b0_objective_key": [float(v) for v in b0_report.objective_key],
                    "b0_vehicles": int(b0_report.vehicles),
                    "changed_decisions": int(sol.metadata.get("changed_decisions") or 0),
                    "note": "screened allow_battery_debt is local only; outcomes use trusted evaluate()",
                }
                rows.append(row)
                print(
                    arm_name,
                    instance_id,
                    seed,
                    outcome,
                    f"veh={report.vehicles}",
                    f"dist={report.total_distance:.1f}",
                    flush=True,
                )

    by_arm: dict[str, dict] = {}
    by_instance: dict[str, dict] = {}
    for row in rows:
        arm = row["arm"]
        by_arm.setdefault(
            arm, {"improved": 0, "tie": 0, "objective_regression": 0, "feasibility_regression": 0}
        )
        by_arm[arm][row["outcome_vs_b0"]] = by_arm[arm].get(row["outcome_vs_b0"], 0) + 1
        ikey = f"{arm}/{row['instance_id']}"
        by_instance.setdefault(
            ikey, {"improved": 0, "tie": 0, "objective_regression": 0, "feasibility_regression": 0}
        )
        by_instance[ikey][row["outcome_vs_b0"]] = by_instance[ikey].get(row["outcome_vs_b0"], 0) + 1

    arm_gates = {
        arm: _gate([r["outcome_vs_b0"] for r in rows if r["arm"] == arm and arm != "B0"])
        if arm != "B0"
        else "baseline"
        for arm in arms
    }

    # Decision rules from the research redesign plan.
    b1_c101 = by_instance.get("B1/c101_21", {})
    b3_c101 = by_instance.get("B3/c101_21", {})
    b1_matches_b3 = (
        b1_c101.get("improved", 0) == b3_c101.get("improved", 0)
        and b1_c101.get("tie", 0) == b3_c101.get("tie", 0)
        and b1_c101.get("objective_regression", 0) == b3_c101.get("objective_regression", 0)
    )
    b2_beats_b1 = by_arm.get("B2", {}).get("improved", 0) > by_arm.get("B1", {}).get("improved", 0)

    if b1_matches_b3 and b3_c101.get("improved", 0) > 0:
        next_step = (
            "Adopt B1 as classical baseline: handcrafted B3 gain on c101_21 is largely "
            "explained by correcting total-route vs marginal scoring."
        )
    elif b2_beats_b1:
        next_step = (
            "Keep B2 as stronger baseline before LLM work; objective-aware consolidation helped."
        )
    elif by_arm.get("B1", {}).get("improved", 0) > 0 or by_arm.get("B2", {}).get("improved", 0) > 0:
        next_step = (
            "Marginal scoring helps some instances; next: residual headroom audit on B1/B2, "
            "then rollout dataset only if headroom remains."
        )
    else:
        next_step = (
            "Little gain from scoring fix alone on this panel; retarget discovery toward "
            "route elimination / destroy selection / charging rather than insertion prompts."
        )

    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": "cipher_baseline_ablation_b0b4_v1",
        "seeds": list(SEEDS),
        "arms": {k: {"repair_scoring_mode": v["repair_scoring_mode"], "note": v["note"]} for k, v in arms.items()},
        "rows": rows,
        "summary_by_arm": by_arm,
        "summary_by_instance": by_instance,
        "arm_gates_vs_b0": arm_gates,
        "decision": {
            "b1_matches_b3_on_c101_21": b1_matches_b3,
            "b2_beats_b1_on_wins": b2_beats_b1,
            "next_step": next_step,
        },
        "reinterpretation_note": (
            "Prior E1 headroom and E3 handcrafted wins used B0 total-route classical ranking. "
            "If B1≈B3, those gains partly measure baseline criterion mismatch, not discovery skill."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", OUT, flush=True)
    print("decision:", next_step, flush=True)


if __name__ == "__main__":
    main()
