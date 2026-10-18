"""Hiermann must publish a covered incumbent inside the development budget."""
from __future__ import annotations

import random
import time
from pathlib import Path

from evrptw_autolab.backbone.construct import construct_greedy
from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.hiermann import load_hiermann

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = ROOT / "dataset" / "hiermann-et-al-2017-set-1" / "c101_21.txt"


def test_heterogeneous_construction_covers_c101_within_seconds() -> None:
    spec = load_hiermann(INSTANCE)
    started = time.perf_counter()
    solution = construct_greedy(spec, random.Random(7))
    elapsed = time.perf_counter() - started
    report = evaluate(spec, solution)
    assert elapsed < 5.0, elapsed
    assert report.feasible, report.first_fault
    assert solution.metadata["construction"] == "heterogeneous_route_local"
    served = {stop.node_id for route in solution.routes for stop in route}
    customers = [node.id for node in spec.nodes if node.kind == "customer"]
    assert set(customers) <= served
    assert report.objective is not None
    assert report.objective > 153.0
    assert len(report.objective_key) == 1
    components = report.objective_components
    assert abs(components["total_cost"] - report.objective) < 1e-6


def test_c101_gate_budget_returns_a_compliant_feasible_incumbent() -> None:
    spec = load_hiermann(INSTANCE)
    solution = solve_classical(spec, seed=7, time_limit_s=15.0, alns_iterations=40)
    report = evaluate(spec, solution)
    assert report.feasible, report.first_fault
    assert solution.metadata["solution_feasible"] is True
    assert solution.metadata["completed_within_budget"] is True
    assert solution.metadata["time_to_first_feasible_s"] is not None
    assert float(solution.metadata["time_to_first_feasible_s"]) < 15.0
    assert report.objective is not None and report.objective > 153.0
