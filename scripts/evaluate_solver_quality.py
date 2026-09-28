"""Evaluate a generated solver on all 36 small Schneider instances (and optionally the 56 large).

Usage:
    python scripts/evaluate_solver_quality.py path/to/solver_dir
    python scripts/evaluate_solver_quality.py path/to/solver_dir --scale large
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from evrptw_autolab.evaluation.fidelity import load_all, partition_of, small_instances, split_instances
from evrptw_autolab.evaluation.literature import SCHNEIDER_2014_SMALL_CPLEX
from evrptw_autolab.sandbox.limits import RunLimits
from evrptw_autolab.sandbox.runner import run_solver

ROOT = Path(__file__).resolve().parents[1]


def _gap(value: float, ref: float) -> float | None:
    if ref == 0:
        return None
    return (value - ref) / ref


def evaluate_small(solver_dir: Path, *, wall_clock_s: float) -> list[dict]:
    instances = small_instances(load_all())
    if len(instances) != 36:
        raise RuntimeError(f"expected 36 small instances, found {len(instances)}")
    limits = RunLimits(wall_clock_s=wall_clock_s)
    rows: list[dict] = []
    for instance in instances:
        report = run_solver(solver_dir, instance, seed=0, limits=limits)
        ref = SCHNEIDER_2014_SMALL_CPLEX.get(instance.instance_id)
        fleet_gap = None
        distance_gap = None
        exact_fleet = False
        if ref is not None:
            fleet_gap = report.vehicles - ref[0] if report.feasible else None
            exact_fleet = bool(report.feasible and report.vehicles == ref[0])
            if report.feasible and report.vehicles == ref[0]:
                distance_gap = _gap(report.total_distance, ref[1])
        rows.append(
            {
                "instance_id": instance.instance_id,
                "family": instance.metadata.get("family"),
                "partition": partition_of(instance),
                "n_customers": len(instance.customer_ids),
                "feasible": report.feasible,
                "vehicles": report.vehicles,
                "distance": round(report.total_distance, 4),
                "cplex_m": ref[0] if ref else "",
                "cplex_f": ref[1] if ref else "",
                "fleet_gap": fleet_gap if fleet_gap is not None else "",
                "distance_gap_equal_fleet": round(distance_gap, 4) if distance_gap is not None else "",
                "exact_fleet": exact_fleet,
                "runtime_s": round(report.runtime_s, 3),
                "crashed": report.crashed,
                "first_fault": (report.first_fault or {}).get("family"),
            }
        )
    return rows


def evaluate_large(solver_dir: Path, *, wall_clock_s: float) -> list[dict]:
    large = [i for i in load_all() if i.metadata.get("scale") == "large"]
    if len(large) != 56:
        raise RuntimeError(f"expected 56 large instances, found {len(large)}")
    limits = RunLimits(wall_clock_s=wall_clock_s)
    rows: list[dict] = []
    for instance in large:
        report = run_solver(solver_dir, instance, seed=0, limits=limits)
        rows.append(
            {
                "instance_id": instance.instance_id,
                "family": instance.metadata.get("family"),
                "partition": partition_of(instance),
                "n_customers": len(instance.customer_ids),
                "feasible": report.feasible,
                "vehicles": report.vehicles,
                "distance": round(report.total_distance, 4),
                "runtime_s": round(report.runtime_s, 3),
                "crashed": report.crashed,
                "first_fault": (report.first_fault or {}).get("family"),
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("solver_dir", type=Path)
    parser.add_argument("--scale", choices=["small", "large"], default="small")
    parser.add_argument("--wall-clock-s", type=float, default=20.0)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    solver_dir = args.solver_dir
    if not solver_dir.is_absolute():
        solver_dir = ROOT / solver_dir
    if args.scale == "small":
        rows = evaluate_small(solver_dir, wall_clock_s=args.wall_clock_s)
        default_name = "solver_quality_small.csv"
    else:
        rows = evaluate_large(solver_dir, wall_clock_s=args.wall_clock_s)
        default_name = "solver_quality_large.csv"
    out = args.output or (ROOT / "results" / "md" / "tables" / default_name)
    _write_csv(out, rows)
    summary = {
        "n": len(rows),
        "feasible": sum(1 for r in rows if r["feasible"]),
        "crashes": sum(1 for r in rows if r["crashed"]),
        "output": str(out),
    }
    if args.scale == "small":
        summary["exact_fleet_matches"] = sum(1 for r in rows if r.get("exact_fleet"))
        by_part = {}
        for row in rows:
            by_part.setdefault(row["partition"], []).append(row)
        summary["feasible_by_partition"] = {
            part: sum(1 for r in part_rows if r["feasible"]) for part, part_rows in by_part.items()
        }
        split = split_instances(load_all())
        summary["n_small_discovery"] = len(small_instances(split["discovery"]))
        summary["n_small_confirmation"] = len(small_instances(split["confirmation"]))
        summary["n_small_heldout"] = len(small_instances(split["heldout"]))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
