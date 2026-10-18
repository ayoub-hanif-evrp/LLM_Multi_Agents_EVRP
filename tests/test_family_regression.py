"""One short solve per family. Feasibility is required only where the budget is known to reach it."""
from __future__ import annotations

from pathlib import Path

import pytest

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.bezzi import load_bezzi
from evrptw_autolab.problem.datasets.goeke import load_goeke
from evrptw_autolab.problem.datasets.hiermann import load_hiermann
from evrptw_autolab.problem.datasets.montoya import load_montoya
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.problem.micro import micro_g1_one_customer

ROOT = Path(__file__).resolve().parents[1]

# key_length is the native objective tuple. require_feasible is only set when
# this short budget is already known to return a feasible incumbent.
CASES = [
    ("schneider", 2, True, 2.0, 20),
    ("montoya", 1, False, 4.0, 20),
    ("bezzi", 1, False, 4.0, 20),
    ("goeke", 2, False, 4.0, 20),
    ("hiermann", 1, False, 2.0, 8),
]


def _load(family: str):
    if family == "schneider":
        return load_schneider_v2(micro_g1_one_customer().metadata["source_path"])
    if family == "montoya":
        return load_montoya(ROOT / "dataset" / "montoya-et-al-2017" / "tc0c10s2cf1.xml")
    if family == "bezzi":
        return load_bezzi(ROOT / "dataset" / "Bezzi & Ceselli EVRP-MRT" / "Dataset_A" / "Instances" / "C101-5.xml")
    if family == "goeke":
        return load_goeke(ROOT / "dataset" / "goeke-2018" / "c101C6.txt")
    if family == "hiermann":
        return load_hiermann(ROOT / "dataset" / "hiermann-et-al-2017-set-1" / "c101_21.txt")
    raise AssertionError(family)


@pytest.mark.parametrize(("family", "key_length", "require_feasible", "limit", "iterations"), CASES)
def test_family_solver_contract(family: str, key_length: int, require_feasible: bool, limit: float, iterations: int) -> None:
    spec = _load(family)
    solution = solve_classical(spec, seed=7, time_limit_s=limit, alns_iterations=iterations)
    report = evaluate(spec, solution)
    assert solution.metadata.get("solution_feasible") == report.feasible
    assert isinstance(solution.metadata.get("completed_within_budget"), bool)
    assert len(report.objective_key) == key_length
    if report.feasible:
        served = {stop.node_id for route in solution.routes for stop in route}
        for node in spec.nodes:
            if node.kind in {"customer", "pickup", "delivery"}:
                assert node.id in served
        assert report.first_fault is None or report.first_fault.family == "OK"
    else:
        assert report.first_fault is not None
        assert report.first_fault.family != "OK"
    if require_feasible:
        assert report.feasible, report.first_fault
    if family == "goeke":
        for route in solution.routes:
            ids = [stop.node_id for stop in route]
            for req in spec.requests:
                if req.pickup_id in ids and req.delivery_id in ids:
                    assert ids.index(req.pickup_id) < ids.index(req.delivery_id)
