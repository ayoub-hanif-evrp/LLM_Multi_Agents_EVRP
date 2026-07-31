"""Minimal full-stack solve wiring: register a verified candidate into ALNS and compare."""

from __future__ import annotations

import hashlib
import json
import random
import time
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from evocharge.data.schneider_parser import parse_schneider_file
from evocharge.domain.solution import Solution
from evocharge.evaluation.adapter import (
    compile_plan_builder,
    load_candidate_source,
)
from evocharge.evaluation.analogues import analogue_for_category
from evocharge.operators.api import DestroyResult, OperatorContext
from evocharge.operators.generated_api import OperatorPlan, RandomSource, ReadOnlySearchState
from evocharge.operators.handcrafted.destroy import DESTROY_OPERATORS
from evocharge.operators.handcrafted.repair import REPAIR_OPERATORS
from evocharge.operators.primitives import apply_operator_plan
from evocharge.solver.alns import ALNSConfig, load_alns_config, run_alns
from evocharge.solver.construction import construct_initial_solution
from evocharge.verification.sandbox import validate_plan


def _route_fp(sol: Solution) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(r.node_ids) for r in sol.routes)


def _copy_solution(sol: Solution) -> Solution:
    return deepcopy(sol)


def instrumented_generated_destroy(
    source: str,
    *,
    operator_name: str = "generated_candidate",
    stats: dict[str, Any],
) -> Callable[..., DestroyResult]:
    """Destroy wrapper that records invocation / change stats (API 1.1.0 plan builder)."""
    builder = compile_plan_builder(source)

    def _destroy(solution: Solution, context: OperatorContext, rng: random.Random) -> DestroyResult:
        stats["invocations"] = int(stats.get("invocations") or 0) + 1
        seed = int(rng.random() * 1_000_000)
        before = _route_fp(solution)
        try:
            state = ReadOnlySearchState(solution=solution, instance=context.instance)
            plan = builder(state, context, RandomSource(seed))
            if not isinstance(plan, OperatorPlan):
                plan = OperatorPlan.model_validate(plan)
        except Exception as exc:  # noqa: BLE001
            stats["errors"] = int(stats.get("errors") or 0) + 1
            return DestroyResult(
                solution=solution,
                removed_customers=(),
                operator=operator_name,
                metadata={"error": "plan_build_exception", "detail": str(exc)},
            )
        if plan.applicable:
            stats["applicable"] = int(stats.get("applicable") or 0) + 1
        else:
            stats["not_applicable"] = int(stats.get("not_applicable") or 0) + 1
            return DestroyResult(
                solution=solution,
                removed_customers=(),
                operator=operator_name,
                metadata={"plan": plan.model_dump(), "plan_applied": False},
            )
        pv = validate_plan(plan, state=state, max_removals=20)
        if not pv.accepted:
            stats["plan_rejected"] = int(stats.get("plan_rejected") or 0) + 1
            return DestroyResult(
                solution=solution,
                removed_customers=(),
                operator=operator_name,
                metadata={"error": "plan_invalid", "errors": pv.errors},
            )
        after_sol = apply_operator_plan(state, context, plan)
        stats["plan_applied"] = int(stats.get("plan_applied") or 0) + 1
        after = _route_fp(after_sol)
        if after != before:
            stats["solution_changed"] = int(stats.get("solution_changed") or 0) + 1
        else:
            stats["solution_unchanged"] = int(stats.get("solution_unchanged") or 0) + 1
        return DestroyResult(
            solution=after_sol,
            removed_customers=(),
            operator=operator_name,
            metadata={
                "plan": plan.model_dump(),
                "n_actions": len(plan.actions),
                "plan_applied": True,
                "solution_changed": after != before,
            },
        )

    _destroy.__name__ = operator_name
    return _destroy


def _parse_trace_operator_stats(run_dir: Path, operator_name: str) -> dict[str, Any]:
    from evocharge.solver.trace import read_trace_events

    trace = run_dir / "events.jsonl.gz"
    if not trace.is_file():
        plain = run_dir / "trace.jsonl"
        if plain.is_file():
            trace = plain
        else:
            return {"selected_in_alns": 0, "accepted_when_selected": 0}
    selected = 0
    accepted_when_selected = 0
    for row in read_trace_events(trace):
        if row.get("event") != "iteration":
            continue
        if row.get("destroy") == operator_name:
            selected += 1
            if row.get("accepted"):
                accepted_when_selected += 1
    return {
        "selected_in_alns": selected,
        "accepted_when_selected": accepted_when_selected,
    }


def _label_delta(base_dist: float, other_dist: float, base_veh: int, other_veh: int) -> str:
    if other_veh < base_veh or (
        other_veh == base_veh and other_dist < base_dist - 1e-9
    ):
        return "improved"
    if other_veh > base_veh or (
        other_veh == base_veh and other_dist > base_dist + 1e-9
    ):
        return "harmed"
    return "no_change"


def _solution_hash(sol: Solution) -> str:
    blob = json.dumps(_route_fp(sol), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _run_arm(
    *,
    instance: Any,
    instance_path: Path,
    initial: Solution,
    alns_cfg: ALNSConfig,
    seed: int,
    run_dir: Path,
    run_id: str,
    destroy_ops: dict[str, Any],
    repair_ops: dict[str, Any],
) -> dict[str, Any]:
    cfg = ALNSConfig(**{**alns_cfg.__dict__, "seed": seed})
    run_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    result = run_alns(
        instance,
        config=cfg,
        run_dir=run_dir,
        run_id=run_id,
        initial=_copy_solution(initial),
        instance_path=str(instance_path),
        destroy_operators=destroy_ops,
        repair_operators=repair_ops,
    )
    return {
        "ok": True,
        "feasible": result.feasible,
        "vehicles": result.objective.vehicles_used,
        "total_distance": result.objective.total_distance,
        "objective": result.objective.model_dump(),
        "elapsed_seconds": result.elapsed_seconds,
        "wall_seconds": time.perf_counter() - t0,
        "iterations": result.iterations,
        "time_to_best": result.time_to_best,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "solution_hash": _solution_hash(result.solution),
    }


def run_full_stack(
    *,
    project_root: Path,
    instance_path: Path,
    candidate_id: str,
    seed: int = 2027,
    config_path: Path | None = None,
    experiment_id: str | None = None,
    analogue_category: str = "composite",
    replace_slot: str = "random_removal",
) -> dict[str, Any]:
    """Baseline vs slot-replaced generated / analogue / noop under identical control."""
    cfg_path = config_path or (project_root / "configs" / "schneider_main.yaml")
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    alns_cfg = load_alns_config(raw)
    alns_cfg.iteration_budget_only = True
    alns_cfg.repair_timeout_seconds = max(float(alns_cfg.repair_timeout_seconds), 60.0)
    alns_cfg.local_search_every = 0

    if replace_slot not in DESTROY_OPERATORS:
        replace_slot = sorted(DESTROY_OPERATORS.keys())[0]

    cdir = project_root / "artifacts" / "candidates" / candidate_id
    source = load_candidate_source(cdir)

    inst = parse_schneider_file(instance_path)
    constructed = construct_initial_solution(inst)
    if constructed.solution is None:
        raise RuntimeError("construction_failed")
    initial = constructed.solution

    eid = experiment_id or f"fullstack_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    exp_dir = project_root / "artifacts" / "fullstack" / eid
    exp_dir.mkdir(parents=True, exist_ok=True)

    gen_stats: dict[str, Any] = {
        "invocations": 0,
        "applicable": 0,
        "not_applicable": 0,
        "plan_applied": 0,
        "plan_rejected": 0,
        "solution_changed": 0,
        "solution_unchanged": 0,
        "errors": 0,
    }
    noop_stats: dict[str, Any] = {"invocations": 0}

    baseline_destroy = dict(DESTROY_OPERATORS)
    baseline_repair = dict(REPAIR_OPERATORS)

    def _slot_replace(callable_op: Any) -> dict[str, Any]:
        ops = dict(DESTROY_OPERATORS)
        ops[replace_slot] = callable_op
        return ops

    generated_destroy = _slot_replace(
        instrumented_generated_destroy(
            source, operator_name=replace_slot, stats=gen_stats
        )
    )

    ana = analogue_for_category(analogue_category)
    ana_name = ana["handcrafted_destroy"]
    if ana_name not in DESTROY_OPERATORS:
        ana_name = sorted(DESTROY_OPERATORS.keys())[0]
    analogue_destroy = _slot_replace(DESTROY_OPERATORS[ana_name])

    def _count_noop(
        solution: Solution, context: OperatorContext, rng: random.Random
    ) -> DestroyResult:
        # Experimental-control "noop": re-register the original slot operator through
        # the same replace path. Isolates runner/RNG invariance (baseline ≡ this arm).
        # A true identity destroy would diverge whenever the slot is selected.
        noop_stats["invocations"] = int(noop_stats.get("invocations") or 0) + 1
        return DESTROY_OPERATORS[replace_slot](solution, context, rng)

    noop_destroy = _slot_replace(_count_noop)

    arms: dict[str, dict[str, Any]] = {}
    arms["baseline"] = _run_arm(
        instance=inst,
        instance_path=instance_path,
        initial=initial,
        alns_cfg=alns_cfg,
        seed=seed,
        run_dir=exp_dir / "baseline",
        run_id=f"{eid}_base",
        destroy_ops=baseline_destroy,
        repair_ops=baseline_repair,
    )
    arms["baseline_plus_generated"] = _run_arm(
        instance=inst,
        instance_path=instance_path,
        initial=initial,
        alns_cfg=alns_cfg,
        seed=seed,
        run_dir=exp_dir / "generated",
        run_id=f"{eid}_gen",
        destroy_ops=generated_destroy,
        repair_ops=baseline_repair,
    )
    arms["baseline_plus_analogue"] = _run_arm(
        instance=inst,
        instance_path=instance_path,
        initial=initial,
        alns_cfg=alns_cfg,
        seed=seed,
        run_dir=exp_dir / "analogue",
        run_id=f"{eid}_ana",
        destroy_ops=analogue_destroy,
        repair_ops=baseline_repair,
    )
    arms["baseline_plus_analogue"]["analogue_destroy_name"] = ana_name
    arms["baseline_plus_analogue"]["analogue_note"] = ana.get("note")
    arms["noop_control"] = _run_arm(
        instance=inst,
        instance_path=instance_path,
        initial=initial,
        alns_cfg=alns_cfg,
        seed=seed,
        run_dir=exp_dir / "noop",
        run_id=f"{eid}_noop",
        destroy_ops=noop_destroy,
        repair_ops=baseline_repair,
    )

    gen_trace = _parse_trace_operator_stats(exp_dir / "generated", replace_slot)
    noop_trace = _parse_trace_operator_stats(exp_dir / "noop", replace_slot)
    ana_trace = _parse_trace_operator_stats(exp_dir / "analogue", replace_slot)

    base = arms["baseline"]
    gen = arms["baseline_plus_generated"]
    noop = arms["noop_control"]
    verdict = _label_delta(
        float(base["total_distance"]),
        float(gen["total_distance"]),
        int(base["vehicles"]),
        int(gen["vehicles"]),
    )
    baseline_noop_identical = (
        base["solution_hash"] == noop["solution_hash"]
        and abs(float(base["total_distance"]) - float(noop["total_distance"])) < 1e-9
        and int(base["vehicles"]) == int(noop["vehicles"])
        and bool(base["feasible"]) == bool(noop["feasible"])
        and int(base["iterations"]) == int(noop["iterations"])
    )

    changed = int(gen_stats.get("solution_changed") or 0)
    applied = int(gen_stats.get("plan_applied") or 0)
    invocations = int(gen_stats.get("invocations") or 0)
    selected = int(gen_trace.get("selected_in_alns") or 0) or invocations
    if selected == 0 and invocations == 0:
        op_behavior = "never_called"
    elif changed == 0 and applied == 0:
        op_behavior = "called_but_inert_or_rejected"
    elif changed == 0:
        op_behavior = "applied_but_no_route_change"
    else:
        op_behavior = "changed_solution_when_called"

    if not baseline_noop_identical:
        recommendation = "fix_experimental_control_before_model_changes"
    elif verdict == "improved":
        recommendation = "proceed_stronger_model_or_heldout"
    elif selected > 0:
        recommendation = "wiring_works_but_no_optimization_gain"
    else:
        recommendation = "do_not_expand_until_end_to_end_value_shown"

    report = {
        "experiment_id": eid,
        "candidate_id": candidate_id,
        "instance": instance_path.name,
        "instance_path": str(instance_path),
        "seed": seed,
        "alns_budget": {
            "max_iterations": alns_cfg.max_iterations,
            "iteration_budget_only": True,
            "time_limit_seconds": alns_cfg.time_limit_seconds,
        },
        "identical_initial_solution": True,
        "api_version": "1.1.0",
        "experimental_control": {
            "replace_slot": replace_slot,
            "separate_rng_streams": True,
            "noop_kind": "sham_original_through_replace_path",
            "baseline_noop_identical": baseline_noop_identical,
            "baseline_solution_hash": base["solution_hash"],
            "noop_solution_hash": noop["solution_hash"],
        },
        "selection_note": (
            f"All arms share identical destroy/repair name sets; the '{replace_slot}' "
            "slot callable is replaced (generated / analogue / noop) without adding options."
        ),
        "arms": {
            "baseline": {
                "vehicles": base["vehicles"],
                "total_distance": base["total_distance"],
                "feasible": base["feasible"],
                "runtime_seconds": base["elapsed_seconds"],
                "iterations": base["iterations"],
                "solution_hash": base["solution_hash"],
            },
            "baseline_plus_generated": {
                "vehicles": gen["vehicles"],
                "total_distance": gen["total_distance"],
                "feasible": gen["feasible"],
                "runtime_seconds": gen["elapsed_seconds"],
                "iterations": gen["iterations"],
                "solution_hash": gen["solution_hash"],
                "vs_baseline": verdict,
            },
            "baseline_plus_analogue": {
                "vehicles": arms["baseline_plus_analogue"]["vehicles"],
                "total_distance": arms["baseline_plus_analogue"]["total_distance"],
                "feasible": arms["baseline_plus_analogue"]["feasible"],
                "runtime_seconds": arms["baseline_plus_analogue"]["elapsed_seconds"],
                "iterations": arms["baseline_plus_analogue"]["iterations"],
                "solution_hash": arms["baseline_plus_analogue"]["solution_hash"],
                "analogue_source_operator": ana_name,
                "replaced_slot": replace_slot,
                "vs_baseline": _label_delta(
                    float(base["total_distance"]),
                    float(arms["baseline_plus_analogue"]["total_distance"]),
                    int(base["vehicles"]),
                    int(arms["baseline_plus_analogue"]["vehicles"]),
                ),
            },
            "noop_control": {
                "vehicles": noop["vehicles"],
                "total_distance": noop["total_distance"],
                "feasible": noop["feasible"],
                "runtime_seconds": noop["elapsed_seconds"],
                "iterations": noop["iterations"],
                "solution_hash": noop["solution_hash"],
                "vs_baseline": _label_delta(
                    float(base["total_distance"]),
                    float(noop["total_distance"]),
                    int(base["vehicles"]),
                    int(noop["vehicles"]),
                ),
            },
        },
        "generated_operator": {
            "replaced_slot": replace_slot,
            "invocations": gen_stats.get("invocations"),
            "applicable": gen_stats.get("applicable"),
            "plan_applied": gen_stats.get("plan_applied"),
            "solution_changed": gen_stats.get("solution_changed"),
            "alns_selected": selected,
            "alns_accepted_when_selected": gen_trace["accepted_when_selected"],
            "behavior": op_behavior,
            "raw_stats": gen_stats,
            "trace_stats": gen_trace,
        },
        "analogue_operator": {
            "source_operator": ana_name,
            "replaced_slot": replace_slot,
            "alns_selected": ana_trace["selected_in_alns"],
            "note": ana.get("note"),
        },
        "noop_operator": {
            "invocations": noop_stats.get("invocations"),
            "alns_selected": noop_trace["selected_in_alns"],
            "replaced_slot": replace_slot,
        },
        "decision_gate": {
            "baseline_noop_identical": baseline_noop_identical,
            "generated_vs_baseline": verdict,
            "operator_produced_measurable_change": changed > 0,
            "operator_was_called": selected > 0,
            "recommendation": recommendation,
        },
        "created_at": datetime.now(UTC).isoformat(),
        "hidden_test_evaluation": False,
        "schneider_transfer": False,
        "optimization_claim": verdict == "improved" and baseline_noop_identical,
    }

    (exp_dir / "fullstack_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    md = _markdown_report(report)
    (exp_dir / "fullstack_report.md").write_text(md, encoding="utf-8")
    docs = project_root / "docs" / "reports" / "fullstack_integration_report.md"
    docs.parent.mkdir(parents=True, exist_ok=True)
    docs.write_text(md, encoding="utf-8")
    return report


def _markdown_report(report: dict[str, Any]) -> str:
    arms = report["arms"]
    g = report["generated_operator"]
    ctrl = report.get("experimental_control") or {}
    lines = [
        "# Full-stack integration report",
        "",
        f"- Experiment: `{report['experiment_id']}`",
        f"- Candidate: `{report['candidate_id']}`",
        f"- Instance: `{report['instance']}`",
        f"- Seed: `{report['seed']}`",
        f"- API: `{report['api_version']}`",
        f"- Replace slot: `{ctrl.get('replace_slot')}`",
        f"- Baseline≡noop: `{ctrl.get('baseline_noop_identical')}`",
        "",
        "## Results",
        "",
        "| Arm | Vehicles | Distance | Feasible | Runtime (s) | vs baseline |",
        "|---|---:|---:|:---:|---:|---|",
    ]
    for key, label in [
        ("baseline", "baseline ALNS"),
        ("baseline_plus_generated", "slot←generated"),
        ("baseline_plus_analogue", "slot←analogue"),
        ("noop_control", "slot←noop"),
    ]:
        a = arms[key]
        vs = a.get("vs_baseline", "—")
        lines.append(
            f"| {label} | {a['vehicles']} | {a['total_distance']:.4f} | "
            f"{a['feasible']} | {a['runtime_seconds']:.2f} | {vs} |"
        )
    lines.extend(
        [
            "",
            "## Generated operator usage",
            "",
            f"- Called in ALNS: **{g['alns_selected']}** times "
            f"(accepted {g['alns_accepted_when_selected']})",
            f"- Plan applied: **{g['plan_applied']}**",
            f"- Solution changed: **{g['solution_changed']}**",
            f"- Behavior: **{g['behavior']}**",
            "",
            "## Decision gate",
            "",
            f"- Baseline≡noop: **{report['decision_gate'].get('baseline_noop_identical')}**",
            f"- Generated vs baseline: **{report['decision_gate']['generated_vs_baseline']}**",
            f"- Recommendation: `{report['decision_gate']['recommendation']}`",
            "",
            "No hidden-test or Schneider evaluation.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"
