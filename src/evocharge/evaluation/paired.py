"""Paired deterministic evaluation of generated candidates (Milestone 8)."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from evocharge.candidates.integration import anchored_instance_paths
from evocharge.data.schneider_parser import parse_schneider_file
from evocharge.evaluation.adapter import (
    build_plan_in_sandbox,
    load_candidate_source,
    make_generated_destroy,
    make_noop_destroy,
)
from evocharge.evaluation.analogues import analogue_for_category
from evocharge.evaluation.behavioral import apply_and_measure, is_behaviorally_inert
from evocharge.evaluation.classify import classify_candidate
from evocharge.operators.api import OperatorContext
from evocharge.operators.generated_api import ReadOnlySearchState
from evocharge.operators.handcrafted.destroy import DESTROY_OPERATORS
from evocharge.operators.handcrafted.repair import REPAIR_OPERATORS
from evocharge.solver.alns import ALNSConfig, load_alns_config, run_alns
from evocharge.solver.charging_repair import ChargingRepairCache
from evocharge.solver.construction import construct_initial_solution
from evocharge.verification.sandbox import validate_plan


def load_m8_config(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return dict(raw)


def _anchored_paths(project_root: Path) -> list[Path]:
    return anchored_instance_paths(project_root)


def _category_from_hypothesis(candidate_dir: Path) -> str:
    hyp = candidate_dir / "hypothesis.json"
    if hyp.is_file():
        data = json.loads(hyp.read_text(encoding="utf-8"))
        return str(data.get("category") or "destroy")
    return "destroy"


def probe_behavioral(
    *,
    project_root: Path,
    candidate_id: str,
    seeds: list[int],
) -> dict[str, Any]:
    cdir = project_root / "artifacts" / "candidates" / candidate_id
    source = load_candidate_source(cdir)
    effects: list[dict[str, Any]] = []
    for inst_path in _anchored_paths(project_root):
        inst = parse_schneider_file(inst_path)
        constructed = construct_initial_solution(inst)
        if constructed.solution is None:
            continue
        ctx = OperatorContext(instance=inst, cache=ChargingRepairCache())
        for seed in seeds:
            plan = build_plan_in_sandbox(source, seed=seed)
            if plan is None:
                effects.append(
                    {
                        "instance": inst_path.name,
                        "seed": seed,
                        "error": "plan_build_failed",
                    }
                )
                continue
            state = ReadOnlySearchState(
                solution=constructed.solution, instance=inst
            )
            pv = validate_plan(plan, state=state, max_removals=20)
            if not pv.accepted:
                effects.append(
                    {
                        "instance": inst_path.name,
                        "seed": seed,
                        "plan": plan.model_dump(),
                        "rejected": True,
                        "errors": pv.errors,
                    }
                )
                continue
            _after, effect = apply_and_measure(
                instance=inst,
                solution=constructed.solution,
                plan=plan,
                context=ctx,
            )
            effects.append(
                {
                    "instance": inst_path.name,
                    "seed": seed,
                    "plan": plan.model_dump(),
                    "effect": effect.model_dump(),
                    "inert": is_behaviorally_inert(effect),
                }
            )
    return {"candidate_id": candidate_id, "behavioral_probes": effects}


def _short_method_tag(method: str) -> str:
    if method == "baseline":
        return "base"
    if method == "noop_control":
        return "noop"
    if method.startswith("analogue_"):
        return "ana_" + method.split("_", 1)[1][:24]
    if method.startswith("candidate_"):
        return "cand"
    return method[:32]


def _run_method(
    *,
    project_root: Path,
    instance_path: Path,
    method: str,
    seed: int,
    alns_cfg: ALNSConfig,
    experiment_dir: Path,
    candidate_source: str | None = None,
    destroy_only: str | None = None,
) -> dict[str, Any]:
    inst = parse_schneider_file(instance_path)
    constructed = construct_initial_solution(inst)
    if constructed.solution is None:
        return {"ok": False, "error": "construction_failed"}

    destroy_ops = dict(DESTROY_OPERATORS)
    repair_ops = dict(REPAIR_OPERATORS)
    if method.startswith("candidate_") and candidate_source is not None:
        destroy_ops["generated_candidate"] = make_generated_destroy(
            candidate_source, use_sandbox=False
        )
    elif method == "noop_control":
        destroy_ops["noop_control"] = make_noop_destroy()
    elif method.startswith("analogue_"):
        # Force only the analogue destroy name if present
        if destroy_only and destroy_only in destroy_ops:
            destroy_ops = {destroy_only: destroy_ops[destroy_only]}

    cfg = ALNSConfig(**{**alns_cfg.__dict__, "seed": seed})
    # Keep Windows paths under MAX_PATH (OneDrive + long candidate ids).
    stem = instance_path.stem
    short_inst = stem.replace("solomon_dataset_", "sd").replace("_wide_", "w")[:40]
    run_id = f"{_short_method_tag(method)}_s{seed}_{short_inst}"
    run_dir = experiment_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    result = run_alns(
        inst,
        config=cfg,
        run_dir=run_dir,
        run_id=run_id,
        initial=constructed.solution,
        instance_path=str(instance_path),
        destroy_operators=destroy_ops,
        repair_operators=repair_ops,
    )
    return {
        "ok": True,
        "method": method,
        "seed": seed,
        "instance": instance_path.name,
        "feasible": result.feasible,
        "objective": result.objective.model_dump(),
        "vehicles": result.objective.vehicles_used,
        "total_distance": result.objective.total_distance,
        "time_to_best": result.time_to_best,
        "elapsed_seconds": result.elapsed_seconds,
        "iterations": result.iterations,
        "cache_hits": result.cache_hits,
        "cache_misses": result.cache_misses,
        "wall_seconds": time.perf_counter() - t0,
        "run_id": run_id,
    }


def evaluate_candidate(
    *,
    project_root: Path,
    candidate_id: str,
    config_path: Path,
    experiment_id: str | None = None,
) -> dict[str, Any]:
    cfg = load_m8_config(config_path)
    eval_cfg = dict(cfg.get("evaluation") or {})
    n_seeds = int(eval_cfg.get("paired_seeds", 5))
    base_seed = int(eval_cfg.get("base_seed", 2027))
    seeds = [base_seed + i for i in range(n_seeds)]
    alns_raw = dict(cfg.get("alns") or {})
    alns_cfg = load_alns_config({"alns": alns_raw})

    eid = experiment_id or f"m8_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}_{candidate_id}"
    exp_dir = project_root / "artifacts" / "evaluations" / eid
    exp_dir.mkdir(parents=True, exist_ok=True)

    cdir = project_root / "artifacts" / "candidates" / candidate_id
    source = load_candidate_source(cdir)
    category = _category_from_hypothesis(cdir)
    analogue = analogue_for_category(category)

    behavioral = probe_behavioral(
        project_root=project_root, candidate_id=candidate_id, seeds=seeds[:3]
    )

    methods = [
        "baseline",
        f"candidate_{candidate_id}",
        "noop_control",
        f"analogue_{analogue['handcrafted_destroy']}",
    ]
    paired_rows: list[dict[str, Any]] = []
    for inst_path in _anchored_paths(project_root):
        for seed in seeds:
            for method in methods:
                row = _run_method(
                    project_root=project_root,
                    instance_path=inst_path,
                    method=method,
                    seed=seed,
                    alns_cfg=alns_cfg,
                    experiment_dir=exp_dir,
                    candidate_source=source
                    if method.startswith("candidate_")
                    else None,
                    destroy_only=analogue["handcrafted_destroy"]
                    if method.startswith("analogue_")
                    else None,
                )
                paired_rows.append(row)

    # Paired deltas: candidate - baseline on total_distance for matching seed/instance
    deltas: list[float] = []
    by_key: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
    for row in paired_rows:
        if not row.get("ok"):
            continue
        key = (str(row["instance"]), int(row["seed"]))
        by_key.setdefault(key, {})[str(row["method"])] = row
    cand_method = f"candidate_{candidate_id}"
    for _key, methods_map in by_key.items():
        base = methods_map.get("baseline")
        cand = methods_map.get(cand_method)
        if base and cand:
            deltas.append(
                float(cand["total_distance"]) - float(base["total_distance"])
            )

    # Analogue similarity: correlation of distance deltas vs analogue method
    analogue_deltas: list[float] = []
    for _key, methods_map in by_key.items():
        base = methods_map.get("baseline")
        ana = methods_map.get(f"analogue_{analogue['handcrafted_destroy']}")
        if base and ana:
            analogue_deltas.append(
                float(ana["total_distance"]) - float(base["total_distance"])
            )
    similarity = None
    if deltas and analogue_deltas and len(deltas) == len(analogue_deltas):
        # simple agreement rate on sign of delta
        agree = sum(
            1
            for a, b in zip(deltas, analogue_deltas, strict=True)
            if (a < 0 and b < 0) or (a > 0 and b > 0) or (abs(a) < 1e-9 and abs(b) < 1e-9)
        )
        similarity = agree / len(deltas)

    from evocharge.evaluation.behavioral import BehavioralEffect

    effects_models: list[BehavioralEffect] = []
    for p in behavioral["behavioral_probes"]:
        if "effect" in p:
            effects_models.append(BehavioralEffect.model_validate(p["effect"]))

    feasible_runs = [r for r in paired_rows if r.get("ok") and r.get("method") == cand_method]
    feas_rate = (
        sum(1 for r in feasible_runs if r.get("feasible")) / len(feasible_runs)
        if feasible_runs
        else None
    )
    classification = classify_candidate(
        candidate_id=candidate_id,
        behavioral_effects=effects_models,
        paired_delta_primary=deltas,
        analogue_similarity=similarity,
        feasible_run_rate=feas_rate,
        min_effects=3,
    )

    from evocharge.evaluation.analysis import answer_candidate_questions
    from evocharge.evaluation.classify import CLASS_DEFINITIONS

    candidate_questions = answer_candidate_questions(
        candidate_id=candidate_id,
        category=category,
        behavioral=behavioral,
        classification=classification.model_dump(),
        paired_deltas=deltas,
        analogue_similarity=similarity,
    )

    summary = {
        "experiment_id": eid,
        "candidate_id": candidate_id,
        "category": category,
        "analogue": analogue,
        "set_label": "anchored_cus100_regression",
        "not_benchmark_claim": True,
        "seeds": seeds,
        "behavioral": behavioral,
        "paired_rows": paired_rows,
        "paired_distance_deltas_vs_baseline": deltas,
        "analogue_similarity_sign_agreement": similarity,
        "classification": classification.model_dump(),
        "candidate_questions": candidate_questions,
        "class_definitions": dict(CLASS_DEFINITIONS),
        "optimization_claim": False,
        "auto_promoted": False,
        "created_at": datetime.now(UTC).isoformat(),
    }
    (exp_dir / "evaluation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (exp_dir / "classification.json").write_text(
        json.dumps(classification.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def compare_candidates(
    *,
    project_root: Path,
    candidate_ids: list[str],
    config_path: Path,
    experiment_id: str | None = None,
) -> dict[str, Any]:
    eid = experiment_id or f"m8_compare_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    results = []
    for i, cid in enumerate(candidate_ids):
        # Short per-candidate dirs to avoid Windows MAX_PATH under OneDrive.
        tag = f"c{i}"
        if "destroy" in cid:
            tag = "h2"
        elif "charging" in cid:
            tag = "h3"
        elif "composite" in cid:
            tag = "h1"
        elif "noop" in cid:
            tag = "noop"
        results.append(
            evaluate_candidate(
                project_root=project_root,
                candidate_id=cid,
                config_path=config_path,
                experiment_id=f"{eid}_{tag}",
            )
        )
    out = {
        "experiment_id": eid,
        "candidates": results,
        "created_at": datetime.now(UTC).isoformat(),
    }
    dest = project_root / "artifacts" / "evaluations" / eid
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "compare_summary.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return out
