"""Phase 1 — classical bottleneck diagnosis on Schneider discovery instances."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from evrptw_autolab.backbone.alns import RESEARCH_CLASSICAL_REPAIR_SCORING
from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.research.partitions import assert_allowed_for_development, write_default_exposure_registry

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "cipher" / "research" / "v2" / "classical_bottleneck.json"
RAW = ROOT / "dataset" / "schneider" / "raw_instances"

# Predeclared discovery-only panel (C1/R1). Includes 100-customer + small instances.
CASES = (
    ("c101C5", 10.0, 40),
    ("c103C5", 10.0, 40),
    ("r104C5", 10.0, 40),
    ("r105C5", 10.0, 40),
    ("c101_21", 30.0, 80),
    ("r101_21", 30.0, 80),
)
SEEDS = (7, 11, 22)
# Literature reference (Schneider et al. / community BKS tables). Compare only with matching contracts.
BKS = {
    "c101_21": {"vehicles": 11, "distance": 1046.83, "source": "E-VRPTW BKS table (Schneider 2014 lineage)"},
    "r101_21": {"vehicles": 20, "distance": 1699.44, "source": "E-VRPTW BKS table (Schneider 2014 lineage)"},
    "c101C5": {"vehicles": 2, "distance": 257.75, "source": "Schneider technical report / CPLEX"},
    "c103C5": {"vehicles": 1, "distance": 176.05, "source": "Schneider technical report / CPLEX"},
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
        "branch": run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
    }


def main() -> None:
    write_default_exposure_registry()
    assert_allowed_for_development([c[0] for c in CASES])
    rows = []
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
                repair_scoring_mode=RESEARCH_CLASSICAL_REPAIR_SCORING,
                stage_trace=True,
            )
            wall = time.perf_counter() - t0
            report = evaluate(spec, sol)
            stages = sol.metadata.get("stage_trace") or []
            ref = BKS.get(instance_id)
            rows.append(
                {
                    "instance_id": instance_id,
                    "seed": seed,
                    "time_limit_s": limit,
                    "alns_iterations": iters,
                    "wall_s": round(wall, 3),
                    "feasible": bool(report.feasible),
                    "vehicles": int(report.vehicles),
                    "total_distance": float(report.total_distance),
                    "objective_key": [float(v) for v in report.objective_key],
                    "n_customers": sum(1 for n in spec.nodes if n.kind == "customer"),
                    "stage_trace": stages,
                    "bks": ref,
                    "vehicle_gap_vs_bks": (
                        None if ref is None else int(report.vehicles) - int(ref["vehicles"])
                    ),
                }
            )
            print(
                instance_id,
                seed,
                f"veh={report.vehicles}",
                f"dist={report.total_distance:.1f}",
                f"wall={wall:.1f}s",
                f"stages={len(stages)}",
                flush=True,
            )

    # Diagnosis heuristics from stage traces on large instances.
    large = [r for r in rows if r["n_customers"] >= 100]
    construct_vehicles = []
    final_vehicles = []
    for row in large:
        stages = {s["stage"]: s for s in row["stage_trace"]}
        if "after_construct" in stages:
            construct_vehicles.append(stages["after_construct"]["vehicles"])
        final_vehicles.append(row["vehicles"])
    diagnosis = {
        "literature_gap": (
            "On c101_21, community BKS ~ 11 vehicles / 1046 distance; current short-budget "
            "B1 solutions use ~32-34 vehicles. Gap is large and not explained by scoring alone."
        ),
        "mean_construct_vehicles_large": (
            None if not construct_vehicles else sum(construct_vehicles) / len(construct_vehicles)
        ),
        "mean_final_vehicles_large": (
            None if not final_vehicles else sum(final_vehicles) / len(final_vehicles)
        ),
        "primary_bottleneck_hypothesis": (
            "Construction opens far too many routes; ALNS with destroy_cap=3 and weak "
            "consolidation fails to compress fleet toward BKS. Route elimination and larger "
            "neighborhoods are the priority before LLM insertion discovery."
        ),
    }

    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": "cipher_classical_bottleneck_v1",
        "git": _git_meta(),
        "repair_scoring_mode": RESEARCH_CLASSICAL_REPAIR_SCORING,
        "panel": [{"instance_id": c[0], "time_limit_s": c[1], "iters": c[2]} for c in CASES],
        "seeds": list(SEEDS),
        "rows": rows,
        "diagnosis": diagnosis,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", OUT, flush=True)
    print("diagnosis:", diagnosis["primary_bottleneck_hypothesis"], flush=True)


if __name__ == "__main__":
    main()
