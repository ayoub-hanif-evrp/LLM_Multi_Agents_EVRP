"""Conservative bundle construction and a random-expression control.

A component is added to the default bundle only when every development pair
stays feasible and none gets a worse feasible objective, with a strict gain
on at least one pair. Winning a single deployment seed is not enough.

Approach B, a learned selector over pre-solution instance features, is not
run. These two Montoya files do not give an independent feature signal.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.components.expressions import wrap_expression
from evrptw_autolab.components.interfaces import DEFAULT_SOURCES, ComponentKind
from evrptw_autolab.components.loader import load_bundle
from evrptw_autolab.experiments.montoya_attribution import (
    DEPLOYMENT_SEEDS,
    DEVELOPMENT_INSTANCES,
    ROOT,
    _sha256_file,
    _sha256_text,
    factorial_variants,
    load_recorded_single_agent_sources,
)
from evrptw_autolab.experiments.policy_sensitivity import KINDS, paired_feasible_outcome
from evrptw_autolab.problem.datasets.montoya import load_montoya

REPLICATION = ROOT / "results" / "v2" / "diagnostics" / "montoya_policy_attribution" / "removal_replication.json"
RANDOM_DISCOVERY_SEED = 0
N_RANDOM_REMOVAL = 4
RULE = (
    "Accept a component only if it preserves feasibility on every development "
    "pair, is not strictly worse on any pair, and is strictly better on at least one. "
    "Ties do not count as improvements. Infeasible objectives are never improvements."
)


def random_removal_expression(rng: random.Random) -> str:
    """Draw one removal expression from the bounded arithmetic grammar."""
    names = ["due_time", "route_distance_share", "rng_value"]
    coeffs = ("0.01", "0.1", "1.0", "5.0", "10.0")
    left, right = rng.sample(names, 2)
    coeff = rng.choice(coeffs)
    other = rng.choice(coeffs)
    kind = rng.randrange(4)
    if kind == 0:
        return f"{left} + {coeff} * {right}"
    if kind == 1:
        return f"max(0.0, {left} - {coeff} * {right})"
    if kind == 2:
        return f"{coeff} * {left} + {other} * {right} + 0.01 * rng_value"
    return f"{left} - {coeff} * {right} + {other} * rng_value"


def conservative_decision(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the no-regression rule. The pairs must already be development pairs."""
    if not pairs:
        return {"accepted": False, "reason": "no_development_pairs", "wins": 0, "losses": 0, "ties": 0}
    feasibility_regression = any(item["baseline_feasible"] and not item["candidate_feasible"] for item in pairs)
    wins = sum(1 for item in pairs if item["paired_outcome"] == "candidate")
    losses = sum(1 for item in pairs if item["paired_outcome"] == "baseline")
    ties = sum(1 for item in pairs if item["paired_outcome"] == "tie")
    infeasible = sum(1 for item in pairs if item["paired_outcome"] == "tie_infeasible")
    if feasibility_regression:
        reason = "feasibility_regression"
        accepted = False
    elif losses:
        reason = "objective_regression"
        accepted = False
    elif wins < 1:
        reason = "no_strict_improvement"
        accepted = False
    else:
        reason = "accepted_no_regression"
        accepted = True
    return {
        "accepted": accepted,
        "reason": reason,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "tie_infeasible": infeasible,
        "n_pairs": len(pairs),
    }


def _pair_from_rows(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    base_key = tuple(float(v) for v in baseline["objective_key"])
    cand_key = tuple(float(v) for v in candidate["objective_key"])
    return {
        "instance_id": baseline["instance_id"],
        "seed": int(baseline["seed"]),
        "baseline_feasible": bool(baseline["feasible"]),
        "candidate_feasible": bool(candidate["feasible"]),
        "baseline_duration": baseline["duration"],
        "candidate_duration": candidate["duration"],
        "baseline_vehicles": baseline["vehicles"],
        "candidate_vehicles": candidate["vehicles"],
        "paired_outcome": paired_feasible_outcome(
            bool(baseline["feasible"]), base_key, bool(candidate["feasible"]), cand_key
        ),
        "candidate_fault": candidate.get("first_fault", ""),
        "completed_within_budget": candidate.get("completed_within_budget"),
    }


def _solve_row(
    spec,
    sources: dict[ComponentKind, str],
    *,
    instance_id: str,
    seed: int,
    time_limit_s: float,
    alns_iterations: int,
) -> dict[str, Any]:
    bundle, errors = load_bundle({kind: sources[kind] for kind in KINDS})
    solution = solve_classical(
        spec,
        seed=seed,
        time_limit_s=time_limit_s,
        alns_iterations=alns_iterations,
        policy=bundle,
        hard_timeout=True,
    )
    report = evaluate(spec, solution)
    return {
        "instance_id": instance_id,
        "seed": seed,
        "load_errors": errors,
        "feasible": bool(report.feasible),
        "objective_key": [float(v) for v in report.objective_key],
        "vehicles": report.vehicles,
        "duration": report.total_duration,
        "first_fault": (
            f"{report.first_fault.family}: {report.first_fault.detail}" if report.first_fault else ""
        ),
        "routes": [[stop.node_id for stop in route] for route in solution.routes],
        "scorer_calls": dict(solution.metadata.get("scorer_calls") or {}),
        "completed_within_budget": solution.metadata.get("completed_within_budget"),
    }


def _defaults_from_replication(path: Path = REPLICATION) -> dict[tuple[str, int], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    found: dict[tuple[str, int], dict[str, Any]] = {}
    for row in payload["rows"]:
        if row.get("variant") != "default":
            continue
        found[(str(row["instance_id"]), int(row["seed"]))] = row
    return found


def _recorded_removal_pairs(path: Path = REPLICATION) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    grouped: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
    for row in payload["rows"]:
        grouped.setdefault((str(row["instance_id"]), int(row["seed"])), {})[str(row["variant"])] = row
    pairs: list[dict[str, Any]] = []
    for key in sorted(grouped):
        group = grouped[key]
        pairs.append(_pair_from_rows(group["default"], group["removal_only"]))
    return pairs


def _panel_pairs(
    sources: dict[ComponentKind, str],
    defaults: dict[tuple[str, int], dict[str, Any]],
    *,
    instances: tuple[str, ...],
    seeds: tuple[int, ...],
    time_limit_s: float,
    alns_iterations: int,
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for instance_id in instances:
        path = ROOT / "dataset" / "montoya-et-al-2017" / f"{instance_id}.xml"
        spec = load_montoya(path)
        for seed in seeds:
            candidate = _solve_row(
                spec,
                sources,
                instance_id=instance_id,
                seed=seed,
                time_limit_s=time_limit_s,
                alns_iterations=alns_iterations,
            )
            pairs.append(_pair_from_rows(defaults[(instance_id, seed)], candidate))
    return pairs


def run_bundle_selection(
    *,
    n_random: int = N_RANDOM_REMOVAL,
    discovery_seed: int = RANDOM_DISCOVERY_SEED,
    time_limit_s: float = 10.0,
    alns_iterations: int = 60,
) -> dict[str, Any]:
    """Judge recorded components and random removal expressions with one rule."""
    loaded = load_recorded_single_agent_sources()
    variants = factorial_variants(loaded["sources"])
    defaults = _defaults_from_replication()
    recorded: dict[str, Any] = {}
    solves = 0
    for name in ("insertion_only", "station_only"):
        pairs = _panel_pairs(
            variants[name],
            defaults,
            instances=DEVELOPMENT_INSTANCES,
            seeds=DEPLOYMENT_SEEDS,
            time_limit_s=time_limit_s,
            alns_iterations=alns_iterations,
        )
        solves += len(pairs)
        recorded[name] = {"decision": conservative_decision(pairs), "pairs": pairs}
    removal_pairs = _recorded_removal_pairs()
    recorded["removal_only"] = {
        "decision": conservative_decision(removal_pairs),
        "pairs": removal_pairs,
        "baseline": "reused_removal_replication",
    }
    rng = random.Random(discovery_seed)
    random_trials: list[dict[str, Any]] = []
    for index in range(n_random):
        expression = random_removal_expression(rng)
        source = wrap_expression("removal_priority", expression)
        sources = dict(DEFAULT_SOURCES)
        sources["removal_priority"] = source
        pairs = _panel_pairs(
            sources,
            defaults,
            instances=DEVELOPMENT_INSTANCES,
            seeds=DEPLOYMENT_SEEDS,
            time_limit_s=time_limit_s,
            alns_iterations=alns_iterations,
        )
        solves += len(pairs)
        random_trials.append(
            {
                "index": index,
                "expression": expression,
                "sha256": _sha256_text(source),
                "decision": conservative_decision(pairs),
                "pairs": pairs,
            }
        )
    accepted = [name for name, item in recorded.items() if item["decision"]["accepted"]]
    accepted_random = [item["index"] for item in random_trials if item["decision"]["accepted"]]
    return {
        "rule": RULE,
        "approach": "A_conservative_add_one",
        "approach_b_learned_portfolio": "not_adopted",
        "approach_b_reason": (
            "The two development files produce the same objective at every deployment "
            "seed, so there is no pre-solution instance feature that separates them. "
            "A selector keyed on the deployment seed would use the solver seed rather "
            "than the instance. The measured removal policy also loses on two of the "
            "three seeds, so a more complex portfolio is not justified."
        ),
        "selected_components": accepted,
        "selected_bundle": "default" if not accepted else "default_plus_" + "_".join(accepted),
        "deployment_solves_per_instance": 1,
        "recorded_component_decisions": recorded,
        "random_control": {
            "discovery_seed": discovery_seed,
            "n_expressions": n_random,
            "accepted_indices": accepted_random,
            "trials": random_trials,
        },
        "solver": {
            "time_limit_s": time_limit_s,
            "alns_iterations": alns_iterations,
            "deployment_seeds": list(DEPLOYMENT_SEEDS),
            "instances": list(DEVELOPMENT_INSTANCES),
            "new_solver_evaluations": solves,
            "reused_default_and_removal_evaluations": len(removal_pairs) * 2,
        },
        "instance_sha256": {
            instance_id: _sha256_file(ROOT / "dataset" / "montoya-et-al-2017" / f"{instance_id}.xml")
            for instance_id in DEVELOPMENT_INSTANCES
        },
    }


def write_bundle_selection(out_dir: Path | None = None) -> Path:
    out = out_dir or (ROOT / "results" / "v2" / "diagnostics" / "montoya_policy_attribution")
    out.mkdir(parents=True, exist_ok=True)
    payload = run_bundle_selection()
    path = out / "bundle_selection.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    summary = {
        "selected_bundle": payload["selected_bundle"],
        "selected_components": payload["selected_components"],
        "approach_b_learned_portfolio": payload["approach_b_learned_portfolio"],
        "recorded": {name: item["decision"] for name, item in payload["recorded_component_decisions"].items()},
        "random_accepted_indices": payload["random_control"]["accepted_indices"],
        "random_decisions": [
            {"index": item["index"], "expression": item["expression"], "decision": item["decision"]}
            for item in payload["random_control"]["trials"]
        ],
        "new_solver_evaluations": payload["solver"]["new_solver_evaluations"],
        "deployment_solves_per_instance": payload["deployment_solves_per_instance"],
    }
    (out / "bundle_selection_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return out
