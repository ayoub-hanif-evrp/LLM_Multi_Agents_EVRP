"""P1.5 runtime-safe synthesis tests (no LLM required)."""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.build.p1_minimal import _read_solver, _write_solver
from evrptw_autolab.build.runtime_integrity import (
    find_hardcoded_node_ids,
    try_commit_runtime_safe,
    validate_candidate,
)
from evrptw_autolab.problem.micro import micro_g1_one_customer, micro_g2_needs_charge

VALID = '''
from evrptw_autolab.problem.physics import propagate_route

def solve(instance, seed: int, time_limit_s: float):
    depot = instance.depot_id
    routes = [[depot, cid, depot] for cid in instance.customer_ids]
    return {"routes": routes, "metadata": {"seed": seed}}
'''.strip()

NAMEERROR = '''
def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    depot = instance.depot_id
    routes = [[depot, cid, depot] for cid in instance.customer_ids]
    return {"routes": routes, "metadata": {"seed": seed}}
'''.strip()


def test_nameerror_cannot_overwrite_runnable(tmp_path: Path) -> None:
    solver_dir = tmp_path / "current"
    _write_solver(solver_dir, VALID)
    before = _read_solver(solver_dir)
    probe = micro_g1_one_customer()
    result = try_commit_runtime_safe(
        solver_dir,
        NAMEERROR,
        role="charging",
        probe=probe,
        agent=None,
        gate="G2",
        max_mechanical_repairs=2,
    )
    assert result.committed is False
    assert result.failure_class == "RUNTIME"
    assert "NameError" in result.reason or "random" in result.reason
    assert _read_solver(solver_dir) == before
    assert result.coding_failure is True


def test_hardcoded_s0_rejected() -> None:
    probe = micro_g2_needs_charge()
    # micro_g2 uses station ids — pick a real one
    sid = probe.station_ids[0]
    src = f'''
def solve(instance, seed: int, time_limit_s: float):
    depot = instance.depot_id
    routes = [[depot, "{sid}", cid, depot] for cid in instance.customer_ids]
    return {{"routes": routes, "metadata": {{"seed": seed}}}}
'''.strip()
    found = find_hardcoded_node_ids(src, probe)
    assert sid in found
    last = validate_candidate(src, probe=probe)
    assert last.ok is False
    assert last.failure_class == "GENERALITY"
    assert "HARDCODED_INSTANCE_IDENTIFIER" in last.reason


def test_generic_strings_not_falsely_rejected() -> None:
    probe = micro_g1_one_customer()
    src = '''
def solve(instance, seed: int, time_limit_s: float):
    meta = {"seed": seed, "note": "routes", "status": "OK"}
    depot = instance.depot_id
    routes = [[depot, cid, depot] for cid in instance.customer_ids]
    return {"routes": routes, "metadata": meta}
'''.strip()
    assert find_hardcoded_node_ids(src, probe) == []
    last = validate_candidate(src, probe=probe)
    assert last.ok is True


def test_valid_runtime_code_commits(tmp_path: Path) -> None:
    solver_dir = tmp_path / "current"
    probe = micro_g1_one_customer()
    result = try_commit_runtime_safe(
        solver_dir,
        VALID,
        role="routing",
        probe=probe,
        agent=None,
        gate="G1",
        max_mechanical_repairs=0,
    )
    assert result.committed is True
    assert "def solve" in _read_solver(solver_dir)


def test_mechanical_repair_same_role_max_two(tmp_path: Path) -> None:
    solver_dir = tmp_path / "current"
    _write_solver(solver_dir, VALID)
    probe = micro_g1_one_customer()
    calls: list[str] = []

    class FakeAgent:
        role = "charging"
        last_raw = ""

    def repair_ask(agent, *, current, gate, instruction):
        calls.append(instruction)
        # Keep returning NameError code
        return NAMEERROR

    result = try_commit_runtime_safe(
        solver_dir,
        NAMEERROR,
        role="charging",
        probe=probe,
        agent=FakeAgent(),
        gate="G2",
        ask_repair_fn=repair_ask,
        max_mechanical_repairs=2,
    )
    assert result.committed is False
    assert result.mechanical_repairs == 2
    assert len(calls) == 2
    assert all("NameError" in c or "RUNTIME" in c or "random" in c for c in calls)
    assert result.coding_failure is True
    assert "architect" not in "".join(calls).lower()
    assert "critic" not in "".join(calls).lower()


def test_station_via_instance_allowed() -> None:
    probe = micro_g2_needs_charge()
    src = '''
from evrptw_autolab.problem.physics import propagate_route

def solve(instance, seed: int, time_limit_s: float):
    depot = instance.depot_id
    routes = []
    for cid in instance.customer_ids:
        route = [depot, cid, depot]
        states = propagate_route(instance, route)
        if any(s.battery_arrival < 0 for s in states) and instance.station_ids:
            sid = instance.station_ids[0]
            route = [depot, sid, cid, depot]
        routes.append(route)
    return {"routes": routes, "metadata": {"seed": seed}}
'''.strip()
    assert find_hardcoded_node_ids(src, probe) == []
    last = validate_candidate(src, probe=probe)
    assert last.ok is True  # may be infeasible but must be runtime-ok
