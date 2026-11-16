"""EXPERIMENT 1 — measured improvement headroom on real development instances.

Samples classical destroy/repair checkpoints with multiple feasible insertions.
Compares classical immediate-cost choice against diverse alternatives using equal
continuation budgets. Records whether better downstream native objectives exist.
"""

from __future__ import annotations

import json
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evrptw_autolab.backbone.alns import alns_improve, destroy_random, repair_greedy
from evrptw_autolab.backbone.construct import construct_greedy
from evrptw_autolab.backbone.decision_features import insertion_features_v4
from evrptw_autolab.backbone.route_screen import replace_route, screen_repair_route
from evrptw_autolab.backbone.util import (
    clone_solution,
    default_vehicle_id,
    empty_route,
    evaluate,
    is_better,
    make_customer_stop,
    vehicle_for_route,
)
from evrptw_autolab.problem.datasets.hiermann import load_hiermann
from evrptw_autolab.problem.datasets.montoya import load_montoya
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "cipher" / "research" / "headroom_audit.json"

# Predeclared development panel. Seeds fixed before looking at outcomes.
CASES = (
    ("schneider", "c101C5", ROOT / "dataset/schneider/raw_instances/c101C5.txt", load_schneider_v2, 4.0, 12),
    ("schneider", "c101_21", ROOT / "dataset/schneider/raw_instances/c101_21.txt", load_schneider_v2, 8.0, 16),
    ("hiermann", "c101_21", ROOT / "dataset/hiermann-et-al-2017-set-1/c101_21.txt", load_hiermann, 6.0, 8),
    ("montoya", "tc0c10s2cf1", ROOT / "dataset/montoya-et-al-2017/tc0c10s2cf1.xml", load_montoya, 6.0, 12),
)
SEEDS = (7, 11, 22)
CHECKPOINTS_PER_RUN = 4
CONTINUATION_ITERS = 8
CONTINUATION_LIMIT_S = 2.0
MAX_ALTERNATIVES = 4  # plus classical


def _enumerate_insertions(
    spec: ProblemSpecV2,
    current: SolutionV2,
    node_id: str,
) -> list[dict[str, Any]]:
    vehicle_id = default_vehicle_id(spec)
    rows: list[dict[str, Any]] = []
    for r_idx, route in enumerate(current.routes):
        try:
            vehicle = vehicle_for_route(spec, current, r_idx)
        except ValueError:
            continue
        for pos in range(1, len(route)):
            trial_route = list(route)
            trial_route.insert(pos, make_customer_stop(node_id, spec))
            ok, distance = screen_repair_route(spec, trial_route, vehicle, allow_battery_debt=True)
            if not ok:
                continue
            features = insertion_features_v4(spec, route, pos, node_id, vehicle)
            rows.append(
                {
                    "label": f"{r_idx}:{pos}",
                    "route_index": r_idx,
                    "pos": pos,
                    "acceptance": float(distance),
                    "features": {k: float(v) for k, v in features.items()},
                    "solution": replace_route(current, r_idx, trial_route),
                }
            )
    if not rows:
        route = empty_route(spec, vehicle_id)
        route.insert(1, make_customer_stop(node_id, spec))
        opened = clone_solution(current)
        opened.routes.append(route)
        opened.vehicle_assignments.append(vehicle_id)
        rows.append(
            {
                "label": "new_route",
                "route_index": -1,
                "pos": 1,
                "acceptance": float("inf"),
                "features": {},
                "solution": opened,
            }
        )
    rows.sort(key=lambda item: (item["acceptance"], item["label"]))
    return rows


def _pick_alternatives(rows: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    """Classical = cheapest acceptance; add diverse non-identical alternatives."""
    if not rows:
        return []
    classical = rows[0]
    chosen = [classical]
    seen = {classical["label"]}
    # Farthest acceptance (often worse immediately).
    farthest = max(rows, key=lambda item: (item["acceptance"], item["label"]))
    if farthest["label"] not in seen:
        chosen.append(farthest)
        seen.add(farthest["label"])
    # Median acceptance.
    mid = rows[len(rows) // 2]
    if mid["label"] not in seen:
        chosen.append(mid)
        seen.add(mid["label"])
    # Best battery_margin if available.
    with_margin = [r for r in rows if "battery_margin" in r["features"]]
    if with_margin:
        best_margin = max(with_margin, key=lambda item: item["features"]["battery_margin"])
        if best_margin["label"] not in seen:
            chosen.append(best_margin)
            seen.add(best_margin["label"])
    # Random remaining.
    remaining = [r for r in rows if r["label"] not in seen]
    rng.shuffle(remaining)
    for row in remaining:
        if len(chosen) >= MAX_ALTERNATIVES + 1:
            break
        chosen.append(row)
        seen.add(row["label"])
    return chosen[: MAX_ALTERNATIVES + 1]


def _continue_from(
    spec: ProblemSpecV2,
    partial: SolutionV2,
    remaining: list[tuple[str, ...]],
    *,
    seed: int,
) -> tuple[SolutionV2, Any]:
    rng = random.Random(seed)
    repaired = repair_greedy(
        spec,
        partial,
        remaining,
        rng,
        policy=None,
        optimize_partial_charges=False,
        partition="development",
    )
    continued = alns_improve(
        spec,
        repaired,
        rng,
        time_limit_s=CONTINUATION_LIMIT_S,
        iterations=CONTINUATION_ITERS,
        policy=None,
        optimize_partial_charges=False,
        adaptive_destroy=True,
        heavy_local=False,
        partition="development",
    )
    return continued, evaluate(spec, continued)


def _audit_run(
    family: str,
    instance_id: str,
    spec: ProblemSpecV2,
    *,
    seed: int,
    time_limit_s: float,
    iterations: int,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    start = construct_greedy(spec, rng, policy=None)
    # Warm a short classical ALNS so checkpoints are mid-search, not empty.
    warmed = alns_improve(
        spec,
        start,
        rng,
        time_limit_s=min(2.0, time_limit_s),
        iterations=max(4, iterations // 3),
        policy=None,
        optimize_partial_charges=False,
        heavy_local=False,
        partition="development",
    )
    checkpoints: list[dict[str, Any]] = []
    for cp_idx in range(CHECKPOINTS_PER_RUN):
        cp_rng = random.Random(seed * 1009 + cp_idx * 17)
        n_units = max(1, sum(1 for n in spec.nodes if n.kind in {"customer", "pickup"}))
        k = max(2, min(4, n_units // 5 or 2))
        destroyed, removed = destroy_random(spec, warmed, cp_rng, k)
        if len(removed) < 2:
            continue
        # First unit is the decision under study; rest continue after the choice.
        focus = removed[0]
        if len(focus) != 1:
            continue  # skip PD pairs in this pilot
        node_id = focus[0]
        rows = _enumerate_insertions(spec, destroyed, node_id)
        if len(rows) < 2:
            continue
        alternatives = _pick_alternatives(rows, cp_rng)
        classical_label = alternatives[0]["label"]
        rollouts = []
        continuation_seed = seed * 10007 + cp_idx * 97
        for alt in alternatives:
            remaining = list(removed[1:])
            # Shuffle remaining with a fork of the same continuation seed for fairness.
            cont_rng_state = continuation_seed
            continued, report = _continue_from(
                spec,
                alt["solution"],
                remaining,
                seed=cont_rng_state,
            )
            rollouts.append(
                {
                    "label": alt["label"],
                    "is_classical": alt["label"] == classical_label,
                    "acceptance": alt["acceptance"],
                    "features": alt["features"],
                    "feasible": bool(report.feasible),
                    "objective_key": [float(v) for v in report.objective_key],
                    "vehicles": report.vehicles,
                    "distance": float(report.total_distance),
                }
            )
        classical_row = next(r for r in rollouts if r["is_classical"])
        better = []
        for row in rollouts:
            if row["is_classical"]:
                continue
            # Build minimal reports for is_better via objective_key/feasible fields.
            from evrptw_autolab.problem.v2.report import EvaluationReportV2

            alt_rep = EvaluationReportV2(
                feasible=row["feasible"],
                objective_key=tuple(row["objective_key"]),
                vehicles=row["vehicles"],
                total_distance=row["distance"],
            )
            class_rep = EvaluationReportV2(
                feasible=classical_row["feasible"],
                objective_key=tuple(classical_row["objective_key"]),
                vehicles=classical_row["vehicles"],
                total_distance=classical_row["distance"],
            )
            if is_better(alt_rep, class_rep):
                better.append(row["label"])
        checkpoints.append(
            {
                "checkpoint": cp_idx,
                "node_id": node_id,
                "n_feasible_insertions": len(rows),
                "n_rollouts": len(rollouts),
                "classical_label": classical_label,
                "classical_objective_key": classical_row["objective_key"],
                "classical_feasible": classical_row["feasible"],
                "improving_alternative_labels": better,
                "has_improvement_opportunity": bool(better),
                "rollouts": rollouts,
            }
        )
        # Advance warm incumbent on the classical choice only (no bias toward winners).
        if checkpoints[-1]["rollouts"]:
            warmed = alternatives[0]["solution"]
            warmed = repair_greedy(
                spec,
                warmed,
                list(removed[1:]),
                random.Random(continuation_seed),
                policy=None,
                optimize_partial_charges=False,
                partition="development",
            )
    return checkpoints


def main() -> None:
    started = time.perf_counter()
    rows = []
    for family, instance_id, path, loader, limit, iters in CASES:
        if not path.exists():
            rows.append({"family": family, "instance_id": instance_id, "status": "missing"})
            continue
        spec = loader(path)
        for seed in SEEDS:
            t0 = time.perf_counter()
            checkpoints = _audit_run(
                family,
                instance_id,
                spec,
                seed=seed,
                time_limit_s=limit,
                iterations=iters,
            )
            elapsed = time.perf_counter() - t0
            n_opp = sum(1 for c in checkpoints if c["has_improvement_opportunity"])
            rows.append(
                {
                    "family": family,
                    "instance_id": instance_id,
                    "seed": seed,
                    "status": "ok",
                    "runtime_s": round(elapsed, 3),
                    "checkpoints": checkpoints,
                    "n_checkpoints": len(checkpoints),
                    "n_with_opportunity": n_opp,
                }
            )
            print(
                family,
                instance_id,
                seed,
                f"cp={len(checkpoints)}",
                f"opp={n_opp}",
                f"{elapsed:.1f}s",
                flush=True,
            )
    ok = [r for r in rows if r.get("status") == "ok"]
    total_cp = sum(int(r["n_checkpoints"]) for r in ok)
    total_opp = sum(int(r["n_with_opportunity"]) for r in ok)
    # Compact training evidence for Experiment 2.
    evidence = []
    for row in ok:
        for cp in row["checkpoints"]:
            if not cp["has_improvement_opportunity"]:
                continue
            classical = next(r for r in cp["rollouts"] if r["is_classical"])
            best_alt = None
            for r in cp["rollouts"]:
                if r["label"] not in cp["improving_alternative_labels"]:
                    continue
                if best_alt is None or tuple(r["objective_key"]) < tuple(best_alt["objective_key"]):
                    best_alt = r
            if best_alt is None:
                continue
            evidence.append(
                {
                    "family": row["family"],
                    "instance_id": row["instance_id"],
                    "seed": row["seed"],
                    "node_id": cp["node_id"],
                    "classical_label": classical["label"],
                    "classical_features": classical["features"],
                    "classical_acceptance": classical["acceptance"],
                    "classical_objective_key": classical["objective_key"],
                    "better_label": best_alt["label"],
                    "better_features": best_alt["features"],
                    "better_acceptance": best_alt["acceptance"],
                    "better_objective_key": best_alt["objective_key"],
                }
            )
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": "cipher_headroom_audit_v1",
        "base_commit": "0344694",
        "seeds": list(SEEDS),
        "continuation_iters": CONTINUATION_ITERS,
        "continuation_limit_s": CONTINUATION_LIMIT_S,
        "max_alternatives": MAX_ALTERNATIVES,
        "selection_procedure": (
            "classical=min acceptance distance; alternatives=farthest, median, "
            "best battery_margin, random fills; equal continuation seed/budget"
        ),
        "rows": rows,
        "summary": {
            "runs": len(ok),
            "checkpoints": total_cp,
            "checkpoints_with_opportunity": total_opp,
            "opportunity_fraction": (None if total_cp == 0 else round(total_opp / total_cp, 4)),
            "evidence_examples": len(evidence),
            "wall_s": round(time.perf_counter() - started, 2),
        },
        "training_evidence": evidence[:40],
        "decision": (
            "continue_to_live_discovery"
            if total_opp > 0
            else "stop_repair_prompts_try_other_operator_family"
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", OUT, payload["summary"], payload["decision"], flush=True)


if __name__ == "__main__":
    main()
