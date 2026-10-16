"""Solver wall-clock budgets must not grossly overshoot."""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.problem.datasets.hiermann import load_hiermann
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2

ROOT = Path(__file__).resolve().parents[1]


def test_schneider_respects_short_deadline() -> None:
    spec = load_schneider_v2(ROOT / "dataset" / "schneider" / "raw_instances" / "c101C5.txt")
    limit = 1.0
    sol = solve_classical(spec, seed=7, time_limit_s=limit, alns_iterations=200)
    runtime = float(sol.metadata.get("runtime_s") or 0.0)
    # Cooperative + hard outer timeout: allow small grace, never 2x overshoot.
    assert runtime <= limit + 0.5, (runtime, sol.metadata)


def test_hiermann_hard_timeout_bounds_runtime() -> None:
    path = ROOT / "dataset" / "hiermann-et-al-2017-set-1" / "c101_21.txt"
    if not path.exists():
        return
    spec = load_hiermann(path)
    limit = 2.0
    sol = solve_classical(spec, seed=7, time_limit_s=limit, alns_iterations=40)
    runtime = float(sol.metadata.get("runtime_s") or 0.0)
    # Hard outer timeout allows grace = max(1.0, 0.15 * limit).
    grace = max(1.0, 0.15 * limit)
    assert runtime <= limit + grace + 0.25, (runtime, sol.metadata.get("hard_timeout"), sol.metadata)
    assert sol.metadata.get("hard_timeout") or runtime <= limit + 0.5
