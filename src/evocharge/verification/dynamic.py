"""Dynamic verification levels for generated operators."""

from __future__ import annotations

import math
import time
from typing import Any, Literal

from evocharge.operators.api import OperatorContext
from evocharge.operators.generated_api import EntityCandidate, OperatorPlan, ReadOnlySearchState
from evocharge.operators.primitives import apply_operator_plan
from evocharge.solver.charging_repair import ChargingRepairCache
from evocharge.solver.construction import construct_initial_solution
from evocharge.solver.feasibility import evaluate_feasibility
from evocharge.verification.sandbox import DynamicVerificationReport, run_in_sandbox, validate_plan
from evocharge.verification.synth import make_tiny_instance


def _ctx(instance: Any) -> OperatorContext:
    return OperatorContext(instance=instance, cache=ChargingRepairCache())


def run_dynamic_verification(
    source: str,
    *,
    operator_type: Literal["scoring", "plan_builder"],
    timeout_seconds: float = 2.0,
) -> DynamicVerificationReport:
    t0 = time.perf_counter()
    errors: list[str] = []
    warnings: list[str] = []
    levels: dict[str, bool] = {}

    # Level 1 — API fixtures
    try:
        empty = run_in_sandbox(
            source,
            operator_type=operator_type,
            candidates=[],
            seed=1,
            timeout_seconds=timeout_seconds,
        )
        one = run_in_sandbox(
            source,
            operator_type=operator_type,
            candidates=[
                {
                    "entity_type": "customer",
                    "entity_id": "C0",
                    "route_index": 0,
                    "metadata": {},
                }
            ],
            seed=1,
            timeout_seconds=timeout_seconds,
        )
        levels["level1_api"] = bool(empty.get("ok")) and bool(one.get("ok"))
        if not levels["level1_api"]:
            errors.append(f"level1:{empty.get('error') or one.get('error')}")
    except Exception as exc:  # noqa: BLE001
        levels["level1_api"] = False
        errors.append(f"level1_exception:{exc}")

    # Level 2 — properties
    try:
        cand = [{"entity_type": "customer", "entity_id": "C0", "metadata": {}}]
        a = run_in_sandbox(
            source,
            operator_type=operator_type,
            candidates=cand,
            seed=42,
            timeout_seconds=timeout_seconds,
        )
        b = run_in_sandbox(
            source,
            operator_type=operator_type,
            candidates=cand,
            seed=42,
            timeout_seconds=timeout_seconds,
        )
        if operator_type == "scoring":
            det = a.get("ok") and b.get("ok") and a.get("scores") == b.get("scores")
        else:
            det = a.get("ok") and b.get("ok") and a.get("plan") == b.get("plan")
        finite = True
        if operator_type == "scoring" and a.get("scores") is not None:
            for s in a["scores"]:
                if not isinstance(s, (int, float)) or not math.isfinite(float(s)):
                    finite = False
        levels["level2_properties"] = bool(det and finite)
        if not levels["level2_properties"]:
            errors.append("level2_nondeterministic_or_nonfinite")
    except Exception as exc:  # noqa: BLE001
        levels["level2_properties"] = False
        errors.append(f"level2_exception:{exc}")

    # Level 3 — synthetic EVRPTW
    try:
        inst = make_tiny_instance()
        ctx = _ctx(inst)
        cres = construct_initial_solution(inst)
        if cres.solution is None:
            levels["level3_synthetic"] = False
            errors.append("level3_construction_failed")
        else:
            state = ReadOnlySearchState(solution=cres.solution, instance=inst)
            if operator_type == "plan_builder":
                sand = run_in_sandbox(
                    source,
                    operator_type=operator_type,
                    seed=7,
                    timeout_seconds=timeout_seconds,
                )
                if not sand.get("ok"):
                    levels["level3_synthetic"] = False
                    errors.append(f"level3_sandbox:{sand.get('error')}")
                else:
                    plan = OperatorPlan.model_validate(sand["plan"])
                    pv = validate_plan(plan, state=state, max_removals=5)
                    if not pv.accepted:
                        levels["level3_synthetic"] = False
                        errors.extend(pv.errors)
                    else:
                        after = apply_operator_plan(state, ctx, plan)
                        report = evaluate_feasibility(inst, after)
                        levels["level3_synthetic"] = True
                        if not report.feasible:
                            warnings.append("level3_infeasible_after_plan")
            else:
                cands = [
                    EntityCandidate(entity_type="customer", entity_id=cid).model_dump()
                    for cid in inst.customer_ids
                ]
                sand = run_in_sandbox(
                    source,
                    operator_type="scoring",
                    candidates=cands,
                    seed=7,
                    timeout_seconds=timeout_seconds,
                )
                ok = bool(sand.get("ok")) and len(sand.get("scores") or []) == len(cands)
                levels["level3_synthetic"] = ok
                if not ok:
                    errors.append("level3_score_length")
    except Exception as exc:  # noqa: BLE001
        levels["level3_synthetic"] = False
        errors.append(f"level3_exception:{exc}")

    levels["level4_anchored"] = False
    warnings.append("level4_requires_integration_command")

    accepted = (
        bool(levels.get("level1_api"))
        and bool(levels.get("level2_properties"))
        and bool(levels.get("level3_synthetic"))
    )
    return DynamicVerificationReport(
        accepted=accepted,
        level_results=levels,
        errors=errors,
        warnings=warnings,
        runtime_seconds=time.perf_counter() - t0,
    )
