"""Solver wall-clock budgets must not grossly overshoot."""
from __future__ import annotations

import time
from pathlib import Path

from evrptw_autolab.backbone.solver import ClassicalSolver
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.goeke import load_goeke
from evrptw_autolab.problem.datasets.hiermann import load_hiermann
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2

ROOT = Path(__file__).resolve().parents[1]


def test_schneider_respects_short_deadline() -> None:
    spec = load_schneider_v2(ROOT / "dataset" / "schneider" / "raw_instances" / "c101C5.txt")
    limit = 1.0
    started = time.monotonic()
    sol = ClassicalSolver(seed=7, time_limit_s=limit, alns_iterations=200).solve(spec)
    wall = time.monotonic() - started
    assert wall <= limit + 2.0, (wall, sol.metadata)


def test_hiermann_hard_timeout_bounds_runtime() -> None:
    path = ROOT / "dataset" / "hiermann-et-al-2017-set-1" / "c101_21.txt"
    if not path.exists():
        return
    spec = load_hiermann(path)
    limit = 2.0
    started = time.monotonic()
    sol = ClassicalSolver(seed=7, time_limit_s=limit, alns_iterations=40).solve(spec)
    wall = time.monotonic() - started
    assert wall <= limit + 2.0, (wall, sol.metadata)
    assert sol.metadata.get("terminated") or wall <= limit + 0.5


def test_sleeping_worker_is_terminated() -> None:
    spec = load_schneider_v2(ROOT / "dataset" / "schneider" / "raw_instances" / "c101C5.txt")
    started = time.monotonic()
    sol = ClassicalSolver(seed=1, time_limit_s=0.8, debug_sleep_s=30.0, alns_iterations=1).solve(spec)
    wall = time.monotonic() - started
    assert wall < 5.0, wall
    assert sol.metadata.get("terminated") is True
    assert sol.routes


def test_goeke_objective_label_matches_lexicographic_key() -> None:
    from evrptw_autolab.backbone.util import empty_route
    from evrptw_autolab.problem.v2.types import SolutionV2

    spec = load_goeke(ROOT / "dataset" / "goeke-2018" / "c101C6.txt")
    assert spec.objective == "minimize_vehicles_then_distance"
    vid = spec.vehicle_types[0].type_id
    sol = SolutionV2(routes=[empty_route(spec, vid)], vehicle_assignments=[vid])
    report = evaluate(spec, sol)
    assert len(report.objective_key) == 2
    assert report.objective_components["vehicles"] == report.objective_key[0]
    assert report.objective_components["distance"] == report.objective_key[1]
