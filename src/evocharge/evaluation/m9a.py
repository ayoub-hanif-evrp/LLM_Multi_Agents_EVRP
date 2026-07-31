"""Milestone 9A evaluation: applicability, metamorphic, comparisons."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evocharge.data.schneider_parser import parse_schneider_file
from evocharge.evaluation.adapter import compile_plan_builder, load_candidate_source
from evocharge.evaluation.behavioral import apply_and_measure, is_behaviorally_inert
from evocharge.evaluation.dev_set import (
    development_instance_paths,
    development_manifest,
    regression_cus100_paths,
)
from evocharge.operators.api import OperatorContext
from evocharge.operators.generated_api import OperatorPlan, RandomSource, ReadOnlySearchState
from evocharge.operators.m9a_reference import REFERENCE_SOURCES
from evocharge.solver.charging_repair import ChargingRepairCache
from evocharge.solver.construction import construct_initial_solution
from evocharge.verification.hardcoded import detect_hardcoded_identities
from evocharge.verification.metamorphic import run_metamorphic_suite
from evocharge.verification.sandbox import validate_plan
from evocharge.verification.semantic_plan import (
    classify_invocation_outcome,
    validate_plan_semantics,
)
from evocharge.verification.static import verify_source


def _outcome_for_plan(
    *,
    plan: OperatorPlan,
    applied: bool,
    changed: bool,
) -> str:
    sem = validate_plan_semantics(plan)
    return classify_invocation_outcome(
        semantic=sem, plan_applied=applied, behaviorally_changed=changed
    )


def evaluate_m9a_candidate(
    *,
    project_root: Path,
    candidate_id: str,
    source: str | None = None,
    max_dev_instances: int = 12,
) -> dict[str, Any]:
    if source is None:
        source = load_candidate_source(project_root / "artifacts" / "candidates" / candidate_id)

    static = verify_source(source, expected_type="plan_builder")
    hardcoded = detect_hardcoded_identities(source)

    builder = None
    compile_error = None
    try:
        builder = compile_plan_builder(source)
    except Exception as exc:  # noqa: BLE001
        compile_error = str(exc)

    outcomes: list[str] = []
    probes: list[dict[str, Any]] = []
    selection_ids: list[str] = []
    changed_instances: set[str] = set()

    paths = development_instance_paths(project_root)[:max_dev_instances]
    for path in paths:
        inst = parse_schneider_file(path)
        constructed = construct_initial_solution(inst)
        if constructed.solution is None or builder is None:
            probes.append({"instance": path.name, "error": "construction_or_compile"})
            continue
        state = ReadOnlySearchState(solution=constructed.solution, instance=inst)
        ctx = OperatorContext(instance=inst, cache=ChargingRepairCache())
        try:
            plan = builder(state, ctx, RandomSource(0))
            if not isinstance(plan, OperatorPlan):
                plan = OperatorPlan.model_validate(plan)
        except Exception as exc:  # noqa: BLE001
            probes.append({"instance": path.name, "error": f"build:{exc}"})
            continue
        sem = validate_plan_semantics(plan)
        pv = validate_plan(plan, state=state)
        if not plan.applicable:
            outcome = "NOT_APPLICABLE"
            probes.append(
                {
                    "instance": path.name,
                    "outcome": outcome,
                    "plan": plan.model_dump(),
                    "semantic": sem.model_dump(),
                }
            )
            outcomes.append(outcome)
            continue
        if not pv.accepted or not sem.accepted:
            outcome = "APPLICABLE_BUT_REJECTED"
            probes.append(
                {
                    "instance": path.name,
                    "outcome": outcome,
                    "errors": pv.errors + sem.errors,
                    "plan": plan.model_dump(),
                }
            )
            outcomes.append(outcome)
            continue
        _after, effect = apply_and_measure(
            instance=inst, solution=constructed.solution, plan=plan, context=ctx
        )
        changed = not is_behaviorally_inert(effect) and (
            effect.customer_sequence_changed
            or effect.station_sequence_changed
            or effect.charging_decision_changed
            or effect.route_assignment_changed
        )
        outcome = "APPLIED_AND_EFFECTIVE" if changed else "APPLIED_BUT_INERT"
        if changed:
            changed_instances.add(path.name)
        for e in plan.selected_entities:
            selection_ids.append(e.entity_id)
        probes.append(
            {
                "instance": path.name,
                "outcome": outcome,
                "effect": effect.model_dump(),
                "plan": plan.model_dump(),
            }
        )
        outcomes.append(outcome)

    # Metamorphic on first regression or first dev instance
    meta_paths = regression_cus100_paths(project_root) or paths
    meta = None
    if meta_paths:
        meta = run_metamorphic_suite(
            source, instance=parse_schneider_file(meta_paths[0])
        ).model_dump()

    n = len(outcomes) or 1
    summary = {
        "candidate_id": candidate_id,
        "static_accepted": static.accepted,
        "static_errors": static.errors,
        "hardcoded_errors": hardcoded,
        "compile_error": compile_error,
        "applicability_rate": sum(1 for o in outcomes if o != "NOT_APPLICABLE") / n,
        "valid_no_action_rate": sum(1 for o in outcomes if o == "NOT_APPLICABLE") / n,
        "plan_application_rate": sum(
            1 for o in outcomes if o in {"APPLIED_BUT_INERT", "APPLIED_AND_EFFECTIVE"}
        )
        / n,
        "effective_behavioral_change_rate": sum(
            1 for o in outcomes if o == "APPLIED_AND_EFFECTIVE"
        )
        / n,
        "selection_diversity": len(set(selection_ids)),
        "changed_instances": sorted(changed_instances),
        "n_changed_instances": len(changed_instances),
        "outcome_counts": {
            k: outcomes.count(k)
            for k in (
                "NOT_APPLICABLE",
                "APPLICABLE_BUT_REJECTED",
                "APPLIED_BUT_INERT",
                "APPLIED_AND_EFFECTIVE",
            )
        },
        "probes": probes,
        "metamorphic": meta,
        "dev_manifest": development_manifest(project_root),
        "optimization_claim": False,
        "auto_promoted": False,
        "created_at": datetime.now(UTC).isoformat(),
    }
    return summary


def install_reference_candidates(project_root: Path) -> list[str]:
    """Write M9A reference operator candidates under artifacts/candidates."""
    from evocharge.operators.primitives import catalogue_hash, write_catalogue_json

    ids = []
    for key, source in REFERENCE_SOURCES.items():
        cid = f"m9a_ref_{key}_precondition"
        cdir = project_root / "artifacts" / "candidates" / cid
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "source.py").write_text(source, encoding="utf-8")
        hyp = {
            "hypothesis_id": f"M9A-{key.upper()}",
            "category": {
                "h2": "destroy",
                "h3": "charging",
                "h1": "composite",
            }[key],
            "name": f"precondition_aware_{key}",
            "api_version": "1.1.0",
            "authoring": "human_reference_m9a",
        }
        (cdir / "hypothesis.json").write_text(
            json.dumps(hyp, indent=2) + "\n", encoding="utf-8"
        )
        write_catalogue_json(cdir / "primitive_catalogue.json")
        (cdir / "catalogue_hash.txt").write_text(catalogue_hash() + "\n", encoding="utf-8")
        static = verify_source(source, expected_type="plan_builder")
        (cdir / "static_report.json").write_text(
            static.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        (cdir / "status.txt").write_text(
            "VERIFIED_REFERENCE\n" if static.accepted else "STATIC_REJECTED\n",
            encoding="utf-8",
        )
        ids.append(cid)
    return ids


def compare_m9a_vs_hardcoded(
    *,
    project_root: Path,
    revised_id: str,
    hardcoded_id: str,
) -> dict[str, Any]:
    rev = evaluate_m9a_candidate(project_root=project_root, candidate_id=revised_id)
    try:
        old = evaluate_m9a_candidate(project_root=project_root, candidate_id=hardcoded_id)
    except Exception as exc:  # noqa: BLE001
        old = {"error": str(exc), "candidate_id": hardcoded_id}
    return {
        "revised": {
            "candidate_id": revised_id,
            "effective_rate": rev.get("effective_behavioral_change_rate"),
            "hardcoded_errors": rev.get("hardcoded_errors"),
            "static_accepted": rev.get("static_accepted"),
            "n_changed_instances": rev.get("n_changed_instances"),
        },
        "hardcoded_baseline": {
            "candidate_id": hardcoded_id,
            "effective_rate": old.get("effective_behavioral_change_rate"),
            "hardcoded_errors": old.get("hardcoded_errors"),
            "static_accepted": old.get("static_accepted"),
        },
        "not_benchmark_claim": True,
    }
