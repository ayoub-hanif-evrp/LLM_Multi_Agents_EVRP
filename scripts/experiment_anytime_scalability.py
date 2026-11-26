"""Anytime scalability on Schneider discovery instances (wall-clock budgets)."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.research.partitions import assert_allowed_for_development

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "cipher" / "research" / "v2" / "anytime_scalability.json"
RAW = ROOT / "dataset" / "schneider" / "raw_instances"

# Predeclared discovery panel + seeds.
INSTANCES = ("c101C5", "r105C5", "c101_21", "r101_21")
SEEDS = (7, 11, 22, 31, 43)
BUDGETS_S = (10.0, 30.0, 60.0)
# Limited 300s subset (expensive): one large clustered + one large random, two seeds.
LONG_CASES = (("c101_21", 7), ("c101_21", 11), ("r101_21", 7))
LONG_BUDGET_S = 300.0

# Frozen from classical_components_v2: LOO_small_destroy beat C4/C5 on mean c101_21 fleet.
CFG = {
    "repair_scoring_mode": "marginal_delta_distance",
    "repair_algorithm": "regret2",
    "destroy_size_cap": 3,
    "route_elimination": True,
    "use_related_destroy": False,
}


def _git_meta() -> dict:
    def run(cmd: list[str]) -> str:
        try:
            return subprocess.check_output(cmd, cwd=ROOT, text=True).strip()
        except Exception:  # noqa: BLE001
            return "unknown"

    return {"commit": run(["git", "rev-parse", "HEAD"]), "dirty": bool(run(["git", "status", "--porcelain"]))}


def _run_one(instance_id: str, seed: int, limit: float) -> dict:
    path = RAW / f"{instance_id}.txt"
    spec = load_schneider_v2(path)
    iters = max(40, int(limit * 3))
    t0 = time.perf_counter()
    sol = solve_classical(
        spec,
        seed=seed,
        time_limit_s=limit,
        alns_iterations=iters,
        hard_timeout=False,
        experiment_partition="development",
        stage_trace=True,
        **CFG,
    )
    wall = time.perf_counter() - t0
    report = evaluate(spec, sol)
    return {
        "instance_id": instance_id,
        "seed": seed,
        "configured_time_limit_s": limit,
        "alns_iterations_configured": iters,
        "wall_s": round(wall, 3),
        "feasible": bool(report.feasible),
        "vehicles": int(report.vehicles),
        "total_distance": float(report.total_distance),
        "objective_key": [float(v) for v in report.objective_key],
        "stage_trace": sol.metadata.get("stage_trace") or [],
        "route_elimination_successes": int(sol.metadata.get("route_elimination_successes") or 0),
        "alns_iterations_completed": sol.metadata.get("alns_iterations"),
    }


def main() -> None:
    assert_allowed_for_development(list(INSTANCES))
    rows = []
    for instance_id in INSTANCES:
        if not (RAW / f"{instance_id}.txt").exists():
            continue
        for seed in SEEDS:
            for budget in BUDGETS_S:
                row = _run_one(instance_id, seed, budget)
                rows.append(row)
                print(
                    instance_id,
                    seed,
                    f"t={budget}",
                    f"veh={row['vehicles']}",
                    f"dist={row['total_distance']:.1f}",
                    f"wall={row['wall_s']:.1f}",
                    flush=True,
                )

    long_rows = []
    for instance_id, seed in LONG_CASES:
        if not (RAW / f"{instance_id}.txt").exists():
            continue
        row = _run_one(instance_id, seed, LONG_BUDGET_S)
        long_rows.append(row)
        print(
            "LONG",
            instance_id,
            seed,
            f"veh={row['vehicles']}",
            f"dist={row['total_distance']:.1f}",
            f"wall={row['wall_s']:.1f}",
            flush=True,
        )

    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": "cipher_anytime_scalability_v1",
        "git": _git_meta(),
        "config": CFG,
        "instances": list(INSTANCES),
        "seeds": list(SEEDS),
        "budgets_s": list(BUDGETS_S),
        "long_budget_s": LONG_BUDGET_S,
        "long_cases": [{"instance_id": i, "seed": s} for i, s in LONG_CASES],
        "rows": rows,
        "long_rows": long_rows,
        "bks_reference": {
            "c101_21": {"vehicles": 11, "distance": 1046.83},
            "r101_21": {"vehicles": 20, "distance": 1699.44},
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
