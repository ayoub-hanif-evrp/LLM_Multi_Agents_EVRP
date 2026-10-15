"""Safe subprocess execution boundary (Milestone 1)."""
from __future__ import annotations

from evrptw_autolab.sandbox.safe_exec import run_hanging_probe, run_python_source
from evrptw_autolab.structured.codegen import unit_test_functions
from evrptw_autolab.structured.signatures import assemble_solver_source

GOOD_CONSTRUCT = '''\
def construct(instance, rng):
    depot = instance.depot_id
    return [[depot, cid, depot] for cid in instance.customer_ids]
'''
GOOD_REPAIR = '''\
def repair(instance, routes, rng):
    return [list(r) for r in routes]
'''
GOOD_IMPROVE = '''\
def improve(instance, routes, rng):
    return [list(r) for r in routes]
'''
GOOD_SOLVE = '''\
def solve(instance, seed: int, time_limit_s: float):
    import random
    rng = random.Random(int(seed))
    routes = construct(instance, rng)
    routes = repair(instance, routes, rng)
    routes = improve(instance, routes, rng)
    return {"routes": routes, "metadata": {}}
'''


def test_unit_test_functions_subprocess_ok() -> None:
    source = assemble_solver_source(None, GOOD_CONSTRUCT, GOOD_REPAIR, GOOD_IMPROVE, GOOD_SOLVE)
    result = unit_test_functions(source, wall_clock_s=15.0)
    assert result["syntax_ok"] is True
    assert result["ok"] is True
    assert result["construct_ok"] and result["repair_ok"] and result["improve_ok"] and result["solve_ok"]


def test_unit_test_functions_crash_reported() -> None:
    bad_construct = '''\
def construct(instance, rng):
    raise RuntimeError("boom")
'''
    source = assemble_solver_source(None, bad_construct, GOOD_REPAIR, GOOD_IMPROVE, GOOD_SOLVE)
    result = unit_test_functions(source, wall_clock_s=15.0)
    assert result["ok"] is False
    assert "boom" in str(result.get("detail") or "")


def test_hanging_generated_code_times_out() -> None:
    result = run_hanging_probe(wall_clock_s=1.0)
    assert result.timed_out is True
    assert result.ok is False


def test_forbidden_import_blocked_before_exec() -> None:
    source = "import socket\ndef foo():\n    return 1\n"
    result = run_python_source(source, wall_clock_s=2.0, driver_source="print('{\"ok\": true}')\n")
    assert result.ok is False
    assert result.scan_errors
    assert any("forbidden_import" in e for e in result.scan_errors)
