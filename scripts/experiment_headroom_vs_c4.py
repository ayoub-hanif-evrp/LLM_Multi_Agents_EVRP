"""Residual insertion headroom against frozen classical C4/C5 configuration."""

from __future__ import annotations

import json
import random
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from evrptw_autolab.backbone.alns import alns_improve, classical_repair_rank_score
from evrptw_autolab.backbone.construct import construct_greedy
from evrptw_autolab.backbone.decision_features import insertion_delta_distance
from evrptw_autolab.backbone.energy_repair import repair_energy
from evrptw_autolab.backbone.route_screen import replace_route, screen_repair_route
from evrptw_autolab.backbone.util import (
    clone_solution,
    evaluate,
    is_better,
    make_customer_stop,
    vehicle_for_route,
)
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.research.partitions import assert_allowed_for_development

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "cipher" / "research" / "v2" / "headroom_vs_c4.json"
RAW = ROOT / "dataset" / "schneider" / "raw_instances"

# Discovery-only; expanded slightly vs B1 pilot.
CASE_LIST = [
    ("c101C5", 7),
    ("c101C5", 11),
    ("c103C5", 11),
    ("r104C5", 22),
    ("r105C5", 7),
    ("r105C5", 11),
    ("c101_21", 7),
    ("c101_21", 11),
]

# Matches frozen baseline from classical_components_v2 (LOO_small_destroy).
CFG = {
    "repair_scoring_mode": "marginal_delta_distance",
    "repair_algorithm": "regret2",
    "destroy_size_cap": 3,
    "use_related_destroy": False,
}
CONTINUATION_ITERS = 16


def _git_meta() -> dict:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    except Exception:  # noqa: BLE001
        commit, dirty = "unknown", True
    return {"commit": commit, "dirty": dirty}


def _candidates(spec, current, node_id: str) -> list[dict]:
    rows = []
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
            delta = insertion_delta_distance(spec, route, pos, node_id)
            customers = sum(1 for stop in route if stop.event != "depot")
            score = classical_repair_rank_score(
                CFG["repair_scoring_mode"],
                total_route_distance=float(distance),
                delta_distance=float(delta),
                route_customer_count=float(customers),
            )
            rows.append(
                {
                    "label": f"{r_idx}:{pos}",
                    "score": score,
                    "solution": replace_route(current, r_idx, trial_route),
                }
            )
    rows.sort(key=lambda item: (item["score"], item["label"]))
    return rows


def _continue(spec, solution, seed: int):
    rng = random.Random(seed)
    return alns_improve(
        spec,
        solution,
        rng,
        time_limit_s=12.0,
        iterations=CONTINUATION_ITERS,
        policy=None,
        optimize_partial_charges=True,
        repair_scoring_mode=CFG["repair_scoring_mode"],
        repair_algorithm=CFG["repair_algorithm"],
        destroy_size_cap=CFG["destroy_size_cap"],
        use_related_destroy=CFG["use_related_destroy"],
    )


def main() -> None:
    assert_allowed_for_development(sorted({c[0] for c in CASE_LIST}))
    checkpoints = []
    improvable = 0
    audited = 0
    for instance_id, seed in CASE_LIST:
        path = RAW / f"{instance_id}.txt"
        if not path.exists():
            continue
        spec = load_schneider_v2(path)
        rng = random.Random(seed)
        sol = construct_greedy(spec, rng, policy=None)
        sol = repair_energy(spec, sol, policy=None)
        if not sol.routes:
            continue
        r_idx = max(range(len(sol.routes)), key=lambda i: len(sol.routes[i]))
        custs = [s.node_id for s in sol.routes[r_idx] if s.event != "depot"]
        if not custs:
            continue
        node_id = custs[len(custs) // 2]
        destroyed = clone_solution(sol)
        destroyed.routes[r_idx] = [
            s for s in destroyed.routes[r_idx] if s.node_id != node_id or s.event == "depot"
        ]
        rows = _candidates(spec, destroyed, node_id)
        if len(rows) < 2:
            continue
        audited += 1
        classical = rows[0]
        alts = []
        for alt in (rows[0], rows[len(rows) // 2], rows[-1]):
            if alt["label"] not in {a["label"] for a in alts}:
                alts.append(alt)
        cont_seed = seed + 5000
        class_final = _continue(spec, classical["solution"], cont_seed)
        class_rep = evaluate(spec, class_final)
        better = False
        details = []
        for alt in alts[1:]:
            alt_final = _continue(spec, alt["solution"], cont_seed)
            alt_rep = evaluate(spec, alt_final)
            win = is_better(alt_rep, class_rep)
            better = better or win
            details.append(
                {
                    "label": alt["label"],
                    "improved": win,
                    "classical_objective": [float(v) for v in class_rep.objective_key],
                    "alt_objective": [float(v) for v in alt_rep.objective_key],
                }
            )
        if better:
            improvable += 1
        checkpoints.append(
            {
                "instance_id": instance_id,
                "seed": seed,
                "node_id": node_id,
                "n_candidates": len(rows),
                "classical_label": classical["label"],
                "improvable": better,
                "details": details,
            }
        )
        print(instance_id, seed, "improvable" if better else "no", flush=True)

    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": "cipher_headroom_vs_c4_v1",
        "git": _git_meta(),
        "baseline_config": CFG,
        "audited_checkpoints": audited,
        "improvable_checkpoints": improvable,
        "opportunity_fraction": (improvable / audited) if audited else None,
        "decision_category": "insertion_position_selection",
        "note": (
            "Continuation uses C4/C5 classical ALNS settings (regret2 + related destroy). "
            "Pilot scale; route-elimination headroom not covered here."
        ),
        "checkpoints": checkpoints,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", OUT, f"{improvable}/{audited}", flush=True)


if __name__ == "__main__":
    main()
