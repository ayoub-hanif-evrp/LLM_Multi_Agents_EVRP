"""Phase 2 — classical component ablation C0–C5 on Schneider discovery instances."""

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
OUT = ROOT / "results" / "cipher" / "research" / "v2" / "classical_components.json"
RAW = ROOT / "dataset" / "schneider" / "raw_instances"

SEEDS = (7, 11, 22)
CASES = (
    ("c101C5", 8.0, 30),
    ("c103C5", 8.0, 30),
    ("r104C5", 8.0, 30),
    ("r105C5", 8.0, 30),
    ("c101_21", 45.0, 100),
)

ARMS = {
    "C0": {
        "repair_scoring_mode": "total_route_distance",
        "repair_algorithm": "greedy",
        "destroy_size_cap": 3,
        "route_elimination": False,
        "note": "Legacy B0",
    },
    "C1": {
        "repair_scoring_mode": "marginal_delta_distance",
        "repair_algorithm": "greedy",
        "destroy_size_cap": 3,
        "route_elimination": False,
        "note": "Corrected B1",
    },
    "C2": {
        "repair_scoring_mode": "marginal_delta_distance",
        "repair_algorithm": "regret2",
        "destroy_size_cap": 3,
        "route_elimination": False,
        "note": "C1 + regret-2",
    },
    "C3": {
        "repair_scoring_mode": "marginal_delta_distance",
        "repair_algorithm": "regret2",
        "destroy_size_cap": 8,
        "route_elimination": False,
        "note": "C2 + larger destroy",
    },
    "C4": {
        "repair_scoring_mode": "marginal_delta_distance",
        "repair_algorithm": "regret2",
        "destroy_size_cap": 8,
        "route_elimination": True,
        "note": "C3 + route elimination",
    },
}


def _git_meta() -> dict:
    def run(cmd: list[str]) -> str:
        try:
            return subprocess.check_output(cmd, cwd=ROOT, text=True).strip()
        except Exception:  # noqa: BLE001
            return "unknown"

    return {
        "commit": run(["git", "rev-parse", "HEAD"]),
        "dirty": bool(run(["git", "status", "--porcelain"])),
    }


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
                )
                wall = time.perf_counter() - t0
                report = evaluate(spec, sol)
                if arm == "C0":
                    baseline_cache[(instance_id, seed)] = report
                b0 = baseline_cache[(instance_id, seed)]
                outcome = "tie" if arm == "C0" else _outcome(b0, report)
                elim = int(sol.metadata.get("route_elimination_successes") or 0)
                rows.append(
                    {
                        "arm": arm,
                        "instance_id": instance_id,
                        "seed": seed,
                        "outcome_vs_c0": outcome,
                        "feasible": bool(report.feasible),
                        "vehicles": int(report.vehicles),
                        "total_distance": float(report.total_distance),
                        "objective_key": [float(v) for v in report.objective_key],
                        "wall_s": round(wall, 3),
                        "route_elimination_successes": elim,
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
        outcomes = [r["outcome_vs_c0"] for r in rows if r["arm"] == arm]
        by_arm[arm] = paired_gate(outcomes, policy_origin="classical")
        by_arm[arm]["mean_vehicles"] = sum(
            r["vehicles"] for r in rows if r["arm"] == arm
        ) / max(1, sum(1 for r in rows if r["arm"] == arm))
        by_arm[arm]["mean_wall_s"] = sum(r["wall_s"] for r in rows if r["arm"] == arm) / max(
            1, sum(1 for r in rows if r["arm"] == arm)
        )

    # Freeze strongest arm by lexicographic mean vehicles then distance on large instances.
    large_ids = {"c101_21"}
    best_arm = "C1"
    best_key = None
    for arm in ARMS:
        subset = [r for r in rows if r["arm"] == arm and r["instance_id"] in large_ids]
        if not subset:
            subset = [r for r in rows if r["arm"] == arm]
        key = (
            sum(r["vehicles"] for r in subset) / len(subset),
            sum(r["total_distance"] for r in subset) / len(subset),
        )
        if best_key is None or key < best_key:
            best_key = key
            best_arm = arm

    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": "cipher_classical_components_v1",
        "git": _git_meta(),
        "arms": ARMS,
        "seeds": list(SEEDS),
        "cases": [{"instance_id": c[0], "time_limit_s": c[1], "iters": c[2]} for c in CASES],
        "rows": rows,
        "summary_by_arm": by_arm,
        "frozen_classical_baseline": {
            "arm": best_arm,
            "config": ARMS[best_arm],
            "selection_rule": "lowest mean vehicles then distance on large (c101_21) then full panel",
            "mean_key": best_key,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", OUT, flush=True)
    print("frozen baseline:", best_arm, ARMS[best_arm], flush=True)


if __name__ == "__main__":
    main()
