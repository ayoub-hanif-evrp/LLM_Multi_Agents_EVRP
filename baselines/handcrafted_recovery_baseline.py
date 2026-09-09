"""Handcrafted EVRPTW recovery baseline — NOT part of the synthesis loop.

This module is a human-written constructive heuristic used only for
scientific comparison against agent-synthesized solvers. It must never be
imported by bootstrap, compile_repair, runtime_repair, evidence_repair, or
agent orchestration.

Usage (manual / paper baseline only):
    from baselines.handcrafted_recovery_baseline import force_executable_entry
    force_executable_entry(Path("results/baselines/recovery"))
"""
from __future__ import annotations

# Re-export the frozen recovery implementation that was removed from synthesis.
# Content lives here as the sole copy of the handcrafted solver.
import ast
import re
from pathlib import Path

PHYSICS_SHIM = (
    '"""Local import shim for generated solvers that use `from physics import ...`."""\n'
    "from evrptw_autolab.problem.physics import (  # noqa: F401\n"
    "    distance,\n"
    "    energy_required,\n"
    "    full_recharge,\n"
    "    propagate_route,\n"
    "    travel_time,\n"
    ")\n"
)

EXECUTABLE_ENTRY = '''\
def solve(instance, seed: int = 0, time_limit_s: float = 10.0):
    import random
    import time as _time
    from evrptw_autolab.problem.evaluator import evaluate_solution, first_fault
    from evrptw_autolab.problem.types import CandidateSolution

    depot = instance.depot_id
    stations = list(instance.station_ids)
    customers = list(instance.customer_ids)
    deadline = _time.monotonic() + min(12.0, max(0.5, float(time_limit_s) * 0.85))

    def is_ok(routes):
        fault = first_fault(instance, CandidateSolution(routes=list(routes), metadata={}))
        return fault.get("family") == "OK"

    def single_route(cid):
        candidates = [[cid]]
        for sid in stations:
            candidates.append([sid, cid])
            candidates.append([cid, sid])
            for sid2 in stations:
                if sid2 == sid:
                    continue
                candidates.append([sid, cid, sid2])
        for insert in candidates:
            trial = [depot] + insert + [depot]
            if is_ok([trial]):
                return trial
        return [depot, cid, depot]

    floor = [single_route(cid) for cid in customers]

    def pack(order):
        routes = []
        remaining = list(order)
        while remaining and _time.monotonic() < deadline:
            route = [depot]
            grew = True
            while grew and remaining and _time.monotonic() < deadline:
                grew = False
                best = None
                for cid in remaining:
                    inserts = [[cid]]
                    for sid in stations:
                        inserts.append([sid, cid])
                        inserts.append([cid, sid])
                    for insert in inserts:
                        trial = route + insert + [depot]
                        rest = [single_route(rid) for rid in remaining if rid != cid]
                        if not is_ok(routes + [trial] + rest):
                            continue
                        score = (len(insert), len(trial))
                        if best is None or score < best[0]:
                            best = (score, cid, insert)
                if best is not None:
                    _, cid, insert = best
                    route = route + insert
                    remaining.remove(cid)
                    grew = True
            routes.append(route + [depot])
        if remaining:
            routes.extend(single_route(cid) for cid in remaining)
        if not is_ok(routes):
            return []
        return routes

    if not customers:
        return {
            "routes": [[depot, depot]],
            "metadata": {"seed": int(seed), "lab_entry_recovery": True},
        }

    best_routes = floor
    best_key = (len(customers) + 1, 1e18)
    if is_ok(floor):
        rep = evaluate_solution(instance, CandidateSolution(routes=floor, metadata={}))
        best_key = (rep.vehicles, rep.total_distance)
        best_routes = floor

    for offset in range(max(1, min(12, len(customers) * 2))):
        if _time.monotonic() >= deadline:
            break
        rng = random.Random(int(seed) + offset)
        order = list(customers)
        rng.shuffle(order)
        packed = pack(order)
        if not packed:
            continue
        report = evaluate_solution(instance, CandidateSolution(routes=packed, metadata={}))
        key = (report.vehicles, report.total_distance)
        if key < best_key:
            best_key = key
            best_routes = packed
    return {
        "routes": best_routes,
        "metadata": {
            "seed": int(seed),
            "time_limit_s": float(time_limit_s),
            "lab_entry_recovery": True,
            "lab_vehicles": len(best_routes),
        },
    }
'''


def ensure_physics_shim(solver_dir: Path) -> bool:
    path = solver_dir / "physics.py"
    if path.exists():
        return False
    path.write_text(PHYSICS_SHIM, encoding="utf-8")
    return True


def force_executable_entry(solver_dir: Path) -> list[str]:
    """Write the handcrafted baseline into solver_dir (baseline experiments only)."""
    tags = ["physics_shim"] if ensure_physics_shim(solver_dir) else []
    solver_dir.mkdir(parents=True, exist_ok=True)
    (solver_dir / "solver.py").write_text(EXECUTABLE_ENTRY, encoding="utf-8")
    tags.append("handcrafted_recovery_baseline")
    return tags
