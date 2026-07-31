"""Smoke checks for verified candidates on Schneider instances."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from evocharge.data.schneider_parser import parse_schneider_file
from evocharge.operators.api import OperatorContext
from evocharge.operators.generated_api import OperatorPlan, ReadOnlySearchState
from evocharge.operators.primitives import apply_operator_plan
from evocharge.solver.charging_repair import ChargingRepairCache
from evocharge.solver.construction import construct_initial_solution
from evocharge.solver.feasibility import evaluate_feasibility
from evocharge.verification.sandbox import run_in_sandbox, validate_plan

# Small Schneider Solomon instances used for Level-4 smoke
ANCHORED_RELATIVE = (
    "c101C5.txt",
    "r104C5.txt",
    "rc105C5.txt",
)


def _anchored_paths(project_root: Path) -> list[Path]:
    root = project_root / "dataset" / "schneider" / "raw_instances"
    return [root / name for name in ANCHORED_RELATIVE if (root / name).is_file()]


def run_integration_test(
    *,
    project_root: Path,
    source: str,
    operator_type: Literal["scoring", "plan_builder"],
    max_instances: int = 3,
    seed: int = 7,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Level-4 Schneider smoke: feasibility must hold after applying a plan."""
    paths = _anchored_paths(project_root)[:max_instances]
    if not paths:
        return {
            "accepted": False,
            "errors": ["no_schneider_fixtures"],
            "instances": [],
        }

    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in paths:
        try:
            inst = parse_schneider_file(path)
            cres = construct_initial_solution(inst)
            if cres.solution is None:
                results.append(
                    {
                        "instance": path.name,
                        "ok": False,
                        "error": "construction_failed",
                    }
                )
                errors.append(f"{path.name}:construction_failed")
                continue
            before = evaluate_feasibility(inst, cres.solution)
            sand = run_in_sandbox(
                source,
                operator_type=operator_type,
                seed=seed,
                timeout_seconds=timeout_seconds,
            )
            if not sand.get("ok"):
                results.append(
                    {
                        "instance": path.name,
                        "ok": False,
                        "error": sand.get("error"),
                    }
                )
                errors.append(f"{path.name}:sandbox:{sand.get('error')}")
                continue
            if operator_type == "scoring":
                results.append(
                    {
                        "instance": path.name,
                        "ok": True,
                        "before_feasible": before.feasible,
                        "note": "scoring_only_no_mutation",
                    }
                )
                continue
            plan = OperatorPlan.model_validate(sand["plan"])
            state = ReadOnlySearchState(solution=cres.solution, instance=inst)
            pv = validate_plan(plan, state=state, max_removals=20)
            if not pv.accepted:
                results.append(
                    {
                        "instance": path.name,
                        "ok": False,
                        "errors": pv.errors,
                    }
                )
                errors.extend(f"{path.name}:{e}" for e in pv.errors)
                continue
            ctx = OperatorContext(instance=inst, cache=ChargingRepairCache())
            before_nodes = [list(r.node_ids) for r in cres.solution.routes]
            after_sol = apply_operator_plan(state, ctx, plan)
            after_nodes = [list(r.node_ids) for r in after_sol.routes]
            after = evaluate_feasibility(inst, after_sol)
            ok = after.feasible
            from evocharge.candidates.pipeline import assess_plan_nontriviality

            nt = assess_plan_nontriviality(plan)
            solution_changed = before_nodes != after_nodes
            results.append(
                {
                    "instance": path.name,
                    "ok": ok,
                    "before_feasible": before.feasible,
                    "after_feasible": after.feasible,
                    "after_violations": after.violation_count,
                    "n_actions": len(plan.actions),
                    "nontrivial": nt.get("nontrivial"),
                    "plan_primitives": nt.get("plan_primitives"),
                    "solution_changed": solution_changed,
                    "meaningful_neighborhood_change": bool(
                        solution_changed or nt.get("nontrivial")
                    ),
                }
            )
            if not ok:
                errors.append(f"{path.name}:infeasible_after_plan")
        except Exception as exc:  # noqa: BLE001
            results.append({"instance": str(path), "ok": False, "error": str(exc)})
            errors.append(f"{path.name}:{exc}")

    accepted = bool(results) and all(r.get("ok") for r in results)
    nontrivial_any = any(r.get("nontrivial") for r in results)
    changed_any = any(r.get("solution_changed") for r in results)
    return {
        "accepted": accepted,
        "errors": errors,
        "instances": results,
        "level": 4,
        "nontrivial_any": nontrivial_any,
        "solution_changed_any": changed_any,
        "note": "Verified candidate means validator-certified on tested cases only.",
    }


def anchored_instance_paths(project_root: Path) -> list[Path]:
    return _anchored_paths(project_root)


def write_integration_results(candidate_dir: Path, payload: dict[str, Any]) -> None:
    (candidate_dir / "integration_results.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
