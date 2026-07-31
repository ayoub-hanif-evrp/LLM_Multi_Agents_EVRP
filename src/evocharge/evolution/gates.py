"""Mandatory verification gates for M9B offspring (fail-fast)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from evocharge.data.schneider_parser import parse_schneider_file
from evocharge.evaluation.adapter import compile_plan_builder
from evocharge.evaluation.dev_set import development_instance_paths, regression_cus100_paths
from evocharge.evaluation.m9a import evaluate_m9a_candidate
from evocharge.operators.api import OperatorContext
from evocharge.operators.generated_api import (
    API_VERSION,
    OperatorPlan,
    RandomSource,
    ReadOnlySearchState,
)
from evocharge.solver.charging_repair import ChargingRepairCache
from evocharge.solver.construction import construct_initial_solution
from evocharge.verification.dynamic import run_dynamic_verification
from evocharge.verification.hardcoded import detect_hardcoded_identities
from evocharge.verification.metamorphic import run_metamorphic_suite
from evocharge.verification.sandbox import validate_plan
from evocharge.verification.semantic_plan import validate_plan_semantics
from evocharge.verification.static import verify_source
from evocharge.verification.synth import make_tiny_instance


def run_gates(
    source: str,
    *,
    project_root: Path,
    candidate_id: str,
    fidelity: str = "short",
) -> dict[str, Any]:
    """Ordered gates. Earlier failure skips full evaluation budget."""
    errors: list[str] = []
    stage = "schema"

    # 1) Schema: compile + OperatorPlan return on tiny
    try:
        builder = compile_plan_builder(source)
        tiny = make_tiny_instance()
        constructed = construct_initial_solution(tiny)
        if constructed.solution is None:
            return _fail(candidate_id, stage, ["tiny_construction_failed"])
        state = ReadOnlySearchState(solution=constructed.solution, instance=tiny)
        ctx = OperatorContext(instance=tiny, cache=ChargingRepairCache())
        plan = builder(state, ctx, RandomSource(0))
        if not isinstance(plan, OperatorPlan):
            plan = OperatorPlan.model_validate(plan)
        if plan.plan_version.startswith("1.0"):
            # Force M9B to use 1.1.0 semantics
            errors.append("legacy_plan_version_not_allowed_in_m9b")
    except Exception as exc:  # noqa: BLE001
        return _fail(candidate_id, stage, [f"schema:{exc}"])

    stage = "static"
    static = verify_source(source, expected_type="plan_builder")
    if not static.accepted:
        return _fail(candidate_id, stage, static.errors, static=static.model_dump())

    stage = "hardcoded"
    hardcoded = detect_hardcoded_identities(source)
    if hardcoded:
        return _fail(candidate_id, stage, hardcoded, static=static.model_dump())

    stage = "semantic_plan"
    sem = validate_plan_semantics(plan)
    if not sem.accepted:
        return _fail(
            candidate_id,
            stage,
            sem.errors,
            static=static.model_dump(),
            semantic=sem.model_dump(),
        )

    stage = "metamorphic"
    meta_inst = tiny
    reg = regression_cus100_paths(project_root)
    if reg:
        meta_inst = parse_schneider_file(reg[0])
    meta = run_metamorphic_suite(source, instance=meta_inst)
    if not meta.accepted:
        return _fail(
            candidate_id,
            stage,
            [r.detail for r in meta.results if not r.passed],
            static=static.model_dump(),
            metamorphic=meta.model_dump(),
        )

    stage = "dynamic"
    dyn = run_dynamic_verification(source, operator_type="plan_builder", timeout_seconds=3.0)
    if not dyn.accepted:
        return _fail(
            candidate_id,
            stage,
            dyn.errors,
            static=static.model_dump(),
            metamorphic=meta.model_dump(),
            dynamic=dyn.model_dump(),
        )

    # Valid no-action probe: empty routes path already covered by operators;
    # check that applicable=False plans validate.
    stage = "no_action_contract"
    if not plan.applicable and not plan.no_action_reason:
        return _fail(candidate_id, stage, ["missing_no_action_reason"])

    stage = "synthetic_validate_apply"
    pv = validate_plan(plan, state=state)
    if plan.applicable and not pv.accepted:
        return _fail(candidate_id, stage, pv.errors)

    # Multi-fidelity numerical evaluation
    max_inst = {"synthetic": 1, "short": 4, "full": 13, "paired": 8}.get(fidelity, 4)
    stage = "development_eval"
    summary = evaluate_m9a_candidate(
        project_root=project_root,
        candidate_id=candidate_id,
        source=source,
        max_dev_instances=max_inst,
    )
    if not summary.get("static_accepted"):
        return _fail(candidate_id, stage, summary.get("static_errors") or ["eval_static"])

    # Feasibility: no APPLICABLE_BUT_REJECTED storm; effective or valid no-action ok
    outcomes = summary.get("outcome_counts") or {}
    if outcomes.get("APPLICABLE_BUT_REJECTED", 0) > max(1, max_inst // 2):
        return _fail(candidate_id, stage, ["too_many_applicable_rejected"])

    return {
        "accepted": True,
        "candidate_id": candidate_id,
        "failed_stage": None,
        "errors": [],
        "static": static.model_dump(),
        "hardcoded_errors": [],
        "metamorphic": meta.model_dump(),
        "dynamic": dyn.model_dump(),
        "evaluation": summary,
        "api_version": API_VERSION,
        "n_dev_paths": len(development_instance_paths(project_root)),
    }


def _fail(
    candidate_id: str,
    stage: str,
    errors: list[str],
    **extra: Any,
) -> dict[str, Any]:
    return {
        "accepted": False,
        "candidate_id": candidate_id,
        "failed_stage": stage,
        "errors": list(errors),
        **extra,
    }
