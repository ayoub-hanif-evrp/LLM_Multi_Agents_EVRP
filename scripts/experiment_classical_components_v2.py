"""C4/C5 + leave-one-out classical ablation (versioned; does not overwrite classical_components.json)."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate, is_better
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.research.gates import paired_gate
from evrptw_autolab.research.partitions import assert_allowed_for_development

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "cipher" / "research" / "v2" / "classical_components_v2.json"
RAW = ROOT / "dataset" / "schneider" / "raw_instances"

SEEDS = (7, 11, 22)
CASES = (
    ("c101C5", 8.0, 30),
    ("c103C5", 8.0, 30),
    ("r104C5", 8.0, 30),
    ("r105C5", 8.0, 30),
    ("c101_21", 45.0, 100),
)

# C4 is the previously frozen baseline. C5 adds related destroy.
# Leave-one-out arms remove one C4 ingredient.
ARMS = {
    "C4": {
        "repair_scoring_mode": "marginal_delta_distance",
        "repair_algorithm": "regret2",
        "destroy_size_cap": 8,
        "route_elimination": True,
        "use_related_destroy": False,
        "note": "Frozen baseline from v1",
    },
    "C5": {
        "repair_scoring_mode": "marginal_delta_distance",
        "repair_algorithm": "regret2",
        "destroy_size_cap": 8,
        "route_elimination": True,
        "use_related_destroy": True,
        "note": "C4 + Shaw-style related destroy",
    },
    "LOO_no_regret": {
        "repair_scoring_mode": "marginal_delta_distance",
        "repair_algorithm": "greedy",
        "destroy_size_cap": 8,
        "route_elimination": True,
        "use_related_destroy": False,
        "note": "Leave-one-out: drop regret-2",
    },
    "LOO_no_elim": {
        "repair_scoring_mode": "marginal_delta_distance",
        "repair_algorithm": "regret2",
        "destroy_size_cap": 8,
        "route_elimination": False,
        "use_related_destroy": False,
        "note": "Leave-one-out: drop route elimination",
    },
    "LOO_small_destroy": {
        "repair_scoring_mode": "marginal_delta_distance",
        "repair_algorithm": "regret2",
        "destroy_size_cap": 3,
        "route_elimination": True,
        "use_related_destroy": False,
        "note": "Leave-one-out: destroy_cap=3",
    },
}


def _git_meta() -> dict:
    def run(cmd: list[str]) -> str:
        try:
            return subprocess.check_output(cmd, cwd=ROOT, text=True).strip()
        except Exception:  # noqa: BLE001
            return "unknown"

    return {"commit": run(["git", "rev-parse", "HEAD"]), "dirty": bool(run(["git", "status", "--porcelain"]))}


def _outcome(baseline, candidate) -> str:
    if baseline.feasible and not candidate.feasible:
        return "feasibility_regression"
    if is_better(candidate, baseline):
        return "improved"
    if is_better(baseline, candidate):
        return "objective_regression"
    return "tie"


def main() -> None:
    assert_allowed_for_development([c[0] for c in CASES])
    baseline_cache: dict[tuple[str, int], object] = {}
    rows = []
    for arm, cfg in ARMS.items():
        for instance_id, limit, iters in CASES:
            path = RAW / f"{instance_id}.txt"
            if not path.exists():
                continue
            spec = load_schneider_v2(path)
            for seed in SEEDS:
                t0 = time.perf_counter()
                sol = solve_classical(
                    spec,
                    seed=seed,
                    time_limit_s=limit,
                    alns_iterations=iters,
                    hard_timeout=False,
                    experiment_partition="development",
                    repair_scoring_mode=cfg["repair_scoring_mode"],
                    repair_algorithm=cfg["repair_algorithm"],
                    destroy_size_cap=cfg["destroy_size_cap"],
                    route_elimination=cfg["route_elimination"],
                    use_related_destroy=cfg["use_related_destroy"],
                )
                wall = time.perf_counter() - t0
                report = evaluate(spec, sol)
                if arm == "C4":
                    baseline_cache[(instance_id, seed)] = report
                b4 = baseline_cache[(instance_id, seed)]
                outcome = "tie" if arm == "C4" else _outcome(b4, report)
                rows.append(
                    {
                        "arm": arm,
                        "instance_id": instance_id,
                        "seed": seed,
                        "outcome_vs_c4": outcome,
                        "feasible": bool(report.feasible),
                        "vehicles": int(report.vehicles),
                        "total_distance": float(report.total_distance),
                        "objective_key": [float(v) for v in report.objective_key],
                        "wall_s": round(wall, 3),
                        "route_elimination_successes": int(
                            sol.metadata.get("route_elimination_successes") or 0
                        ),
                        "config": cfg,
                    }
                )
                print(
                    arm,
                    instance_id,
                    seed,
                    outcome,
                    f"veh={report.vehicles}",
                    f"dist={report.total_distance:.1f}",
                    f"wall={wall:.1f}s",
                    flush=True,
                )

    by_arm = {}
    for arm in ARMS:
        outcomes = [r["outcome_vs_c4"] for r in rows if r["arm"] == arm]
        by_arm[arm] = paired_gate(outcomes, policy_origin="classical")
        subset = [r for r in rows if r["arm"] == arm]
        by_arm[arm]["mean_vehicles"] = sum(r["vehicles"] for r in subset) / len(subset)
        by_arm[arm]["mean_wall_s"] = sum(r["wall_s"] for r in subset) / len(subset)
        large = [r for r in subset if r["instance_id"] == "c101_21"]
        by_arm[arm]["c101_21_vehicles"] = [r["vehicles"] for r in large]

    # Prefer lower mean vehicles on c101_21, then panel mean vehicles, then distance.
    best_arm = "C4"
    best_key = None
    for arm in ARMS:
        large = [r for r in rows if r["arm"] == arm and r["instance_id"] == "c101_21"]
        panel = [r for r in rows if r["arm"] == arm]
        key = (
            sum(r["vehicles"] for r in large) / len(large),
            sum(r["vehicles"] for r in panel) / len(panel),
            sum(r["total_distance"] for r in large) / len(large),
        )
        if best_key is None or key < best_key:
            best_key = key
            best_arm = arm

    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": "cipher_classical_components_v2",
        "git": _git_meta(),
        "arms": ARMS,
        "seeds": list(SEEDS),
        "cases": [{"instance_id": c[0], "time_limit_s": c[1], "iters": c[2]} for c in CASES],
        "rows": rows,
        "summary_by_arm": by_arm,
        "frozen_classical_baseline": {
            "arm": best_arm,
            "config": ARMS[best_arm],
            "selection_rule": "lowest mean c101_21 vehicles, then panel vehicles, then c101_21 distance",
            "mean_key": best_key,
            "previous_frozen": "C4",
        },
        "note": (
            "C6 charging-aware search not ablated on Schneider full-recharge contract "
            "(partial charging in search is out of family contract)."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", OUT, flush=True)
    print("frozen baseline:", best_arm, ARMS[best_arm], flush=True)


if __name__ == "__main__":
    main()
